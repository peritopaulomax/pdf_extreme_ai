"""Chat RAG/free com paridade ao fluxo em app.py (sem Streamlit)."""

from __future__ import annotations

import logging
import os
import queue
import re
import threading
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterator

from core.bootstrap import bootstrap_legacy
from services.sse import format_sse
from services.stack_manager import build_chat_engines, get_cached_stack

logger = logging.getLogger(__name__)

_STREAM_IDLE_TIMEOUT_S = 90.0
_STREAM_START_TIMEOUT_S = 120.0
_REPEAT_QUESTION_PREFIX_RE = re.compile(
    r"^(?:você|voce)\s*\n+",
    re.IGNORECASE,
)
_STREAM_START_LABELS = {
    "chat_stream_start",
    "fallback_stream_start",
    "retry_stream_start",
}
_model_generation_registry_lock = threading.Lock()
_model_generation_context = threading.local()


@dataclass
class _ModelGenerationState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    active: int = 0
    waiting: int = 0


@dataclass
class _ModelGenerationLease:
    key: str
    state: _ModelGenerationState


_model_generation_states: dict[str, _ModelGenerationState] = {}


@dataclass
class StreamStats:
    content_chars: int = 0
    thinking_updates: int = 0
    recovery_attempts: int = 0
    skip_condense: bool = False
    repeat_question: bool = False
    history_messages: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "content_chars": self.content_chars,
            "thinking_updates": self.thinking_updates,
            "recovery_attempts": self.recovery_attempts,
            "skip_condense": self.skip_condense,
            "repeat_question": self.repeat_question,
            "history_messages": self.history_messages,
        }


def _model_generation_key(model_name: str | None) -> str:
    return (model_name or "default").strip() or "default"


def _get_model_generation_state(model_name: str | None) -> tuple[str, _ModelGenerationState]:
    key = _model_generation_key(model_name)
    with _model_generation_registry_lock:
        state = _model_generation_states.get(key)
        if state is None:
            state = _ModelGenerationState()
            _model_generation_states[key] = state
        return key, state


def _model_generation_is_busy(model_name: str | None) -> bool:
    _key, state = _get_model_generation_state(model_name)
    with _model_generation_registry_lock:
        return state.active > 0 or state.lock.locked()


def _model_generation_has_contention(model_name: str | None) -> bool:
    _key, state = _get_model_generation_state(model_name)
    with _model_generation_registry_lock:
        return state.active > 0 or state.waiting > 0 or state.lock.locked()


def _acquire_model_generation_slot(model_name: str | None) -> _ModelGenerationLease:
    key, state = _get_model_generation_state(model_name)
    with _model_generation_registry_lock:
        state.waiting += 1
    state.lock.acquire()
    with _model_generation_registry_lock:
        state.waiting = max(0, state.waiting - 1)
        state.active += 1
    return _ModelGenerationLease(key=key, state=state)


def _release_model_generation_slot(lease: _ModelGenerationLease | None) -> None:
    if lease is None:
        return
    with _model_generation_registry_lock:
        lease.state.active = max(0, lease.state.active - 1)
    lease.state.lock.release()


def _current_generation_model() -> str | None:
    return getattr(_model_generation_context, "model_name", None)


class _LockedStreamResponse:
    def __init__(self, inner: Any, lease: _ModelGenerationLease):
        self._inner = inner
        self._lease = lease
        self._released = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _release_once(self) -> None:
        if self._released:
            return
        self._released = True
        _release_model_generation_slot(self._lease)

    @property
    def response_gen(self):
        gen = getattr(self._inner, "response_gen", None)
        if gen is None:
            self._release_once()
            return None

        def _wrapped():
            try:
                yield from gen
            finally:
                self._release_once()

        return _wrapped()


def chat_async_turns_enabled() -> bool:
    return os.environ.get("CHAT_ASYNC_TURNS", "").lower() in ("1", "true", "yes")


def _reranker_runtime_error(msg: str) -> bool:
    m = msg.lower()
    return "rerank" in m or "cross-encoder" in m or "sentence_transformer" in m


def _extract_thinking(candidate) -> str | None:
    if candidate is None:
        return None
    keys = ("thinking", "reasoning", "reasoning_content", "chain_of_thought")
    if isinstance(candidate, dict):
        for key in keys:
            val = candidate.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    for key in keys:
        val = getattr(candidate, key, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    additional = getattr(candidate, "additional_kwargs", None)
    if isinstance(additional, dict):
        for key in keys:
            val = additional.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _normalize_user_prompt(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = _REPEAT_QUESTION_PREFIX_RE.sub("", cleaned).strip()
    return cleaned


def _is_repeat_question(prior_messages: list[dict], prompt: str) -> bool:
    normalized = _normalize_user_prompt(prompt).casefold()
    if not normalized:
        return False
    for msg in reversed(prior_messages):
        if str(msg.get("role", "")).strip().lower() != "user":
            continue
        prior = _normalize_user_prompt(str(msg.get("content", ""))).casefold()
        if prior == normalized:
            return True
    return False


@contextmanager
def _thinking_disabled(capture_llm):
    inner = getattr(capture_llm, "llm", None)
    if inner is None:
        yield
        return
    old = getattr(inner, "thinking", None)
    inner.thinking = False
    try:
        yield
    finally:
        inner.thinking = old


def _empty_response_message(
    *,
    stats: StreamStats,
    thinking_text: str | None,
    diagnostics: Any,
) -> str:
    parts = [
        "O modelo concluiu sem gerar texto de resposta.",
    ]
    if stats.thinking_updates and stats.content_chars == 0:
        parts.append(
            "Houve raciocinio interno (thinking), mas nenhum token de conteudo."
        )
    if stats.recovery_attempts:
        parts.append(f"Tentativas de recuperacao: {stats.recovery_attempts}.")
    if stats.repeat_question:
        parts.append("Pergunta repetida no historico.")
    if diagnostics is not None:
        parts.append(
            "Retrieval: "
            f"profile={getattr(getattr(diagnostics, 'plan', None), 'profile', '-')}, "
            f"fused={getattr(diagnostics, 'fused_count', '-')}"
        )
    parts.append(f"Diag: {stats.as_dict()}")
    return " ".join(parts)


def _stream_tokens(
    token_gen,
    capture_llm,
    stats: StreamStats | None = None,
) -> Iterator[tuple[str, str | None]]:
    """Yield (token_piece, thinking_snapshot)."""
    bootstrap_legacy()
    from llm_thinking import get_captured_thinking, get_live_thinking

    assistant_text = ""
    thinking_text = None
    for token in token_gen:
        live = get_live_thinking(capture_llm)
        if live:
            thinking_text = live
            if stats is not None:
                stats.thinking_updates += 1
            yield ("", thinking_text)
        piece = token if isinstance(token, str) else str(token or "")
        if piece:
            assistant_text += piece
            if stats is not None:
                stats.content_chars += len(piece)
            yield (piece, thinking_text)
    final_thinking = get_captured_thinking(capture_llm) or thinking_text
    yield ("", final_thinking if final_thinking else None)


def _stream_tokens_with_idle_timeout(
    token_gen,
    capture_llm,
    *,
    idle_timeout_s: float,
    stats: StreamStats | None = None,
) -> Iterator[tuple[str, str | None]]:
    """Consume token stream with idle watchdog to avoid indefinite hangs."""
    q: queue.Queue[tuple[str, str | None] | object] = queue.Queue()
    done = object()
    failure: list[BaseException] = []

    def _worker() -> None:
        try:
            for item in _stream_tokens(token_gen, capture_llm, stats=stats):
                q.put(item)
        except BaseException as exc:  # noqa: BLE001
            failure.append(exc)
        finally:
            q.put(done)

    t = threading.Thread(target=_worker, name="chat-stream-worker", daemon=True)
    t.start()

    while True:
        try:
            item = q.get(timeout=max(1.0, float(idle_timeout_s)))
        except queue.Empty as exc:
            raise TimeoutError(
                f"Sem tokens por {idle_timeout_s:.0f}s; stream interrompido."
            ) from exc
        if item is done:
            if failure:
                raise failure[0]
            break
        yield item  # type: ignore[misc]


def _call_with_timeout(fn, *, timeout_s: float, label: str):
    """Run blocking call in background thread with timeout."""
    lease: _ModelGenerationLease | None = None
    if label in _STREAM_START_LABELS:
        lease = _acquire_model_generation_slot(_current_generation_model())

    q: queue.Queue[object] = queue.Queue()
    done = object()

    def _worker() -> None:
        try:
            q.put(fn())
        except BaseException as exc:  # noqa: BLE001
            q.put(exc)
        finally:
            q.put(done)

    t = threading.Thread(target=_worker, name=f"{label}-worker", daemon=True)
    t.start()

    try:
        item = q.get(timeout=max(1.0, float(timeout_s)))
    except queue.Empty as exc:
        _release_model_generation_slot(lease)
        raise TimeoutError(
            f"Timeout ao iniciar {label} ({timeout_s:.0f}s)."
        ) from exc

    if isinstance(item, BaseException):
        _release_model_generation_slot(lease)
        raise item
    if lease is not None:
        if getattr(item, "response_gen", None) is not None:
            return _LockedStreamResponse(item, lease)
        _release_model_generation_slot(lease)
    return item


def _resolve_forced_profile(profile: str | None) -> str | None:
    if not profile or profile.strip().lower() in ("automatico", "auto", ""):
        return None
    return profile.strip().lower()


def _title_from_first_user_message(text: str, max_len: int = 48) -> str:
    line = (text or "").strip().split("\n", 1)[0]
    if len(line) <= max_len:
        return line or "Nova conversa"
    return line[: max_len - 1].rstrip() + "…"


def _sync_chat_reply(
    chat_engine,
    prompt: str,
    capture_llm,
    *,
    disable_thinking: bool = False,
) -> tuple[str, str | None]:
    bootstrap_legacy()
    from chat_response_utils import coalesce_assistant_reply
    from llm_thinking import clear_captured_thinking, get_captured_thinking

    clear_captured_thinking(capture_llm)
    ctx = _thinking_disabled(capture_llm) if disable_thinking else nullcontext()
    with ctx:
        lease = _acquire_model_generation_slot(_current_generation_model())
        try:
            fb = chat_engine.chat(prompt)
        finally:
            _release_model_generation_slot(lease)
    text = coalesce_assistant_reply(
        str(getattr(fb, "response", fb) or ""),
        fb,
        chat_engine,
        wait_history=False,
    )
    thinking = get_captured_thinking(capture_llm) or _extract_thinking(fb)
    return text, thinking


def _retry_status_message(issues: list[str]) -> str:
    if not issues:
        return "Validacao automatica: repetindo em modo mais profundo..."
    joined = "; ".join(issues[:3])
    if len(issues) > 3:
        joined += f" (+{len(issues) - 3} mais)"
    return f"Validacao: {joined}. Repetindo em modo mais profundo..."


_LITERAL_COUNT_ONLY_ISSUE = "Consulta literal exaustiva sem total de ocorrencias no texto."


def _has_page_citation(text: str) -> bool:
    lowered = (text or "").lower()
    return "[" in text and "]" in text and ("pag" in lowered or "fls" in lowered)


def _should_skip_retry_for_cosmetic_validation(validation, assistant_text: str) -> bool:
    """Nao prender o prompt para retry quando a resposta ja esta util e citada."""
    if not getattr(validation, "should_retry", False):
        return False
    if not assistant_text.strip() or not _has_page_citation(assistant_text):
        return False
    issues = list(getattr(validation, "issues", None) or [])
    return bool(issues) and all(issue == _LITERAL_COUNT_ONLY_ISSUE for issue in issues)


def _recover_empty_content(
    chat_engine,
    prompt: str,
    capture_llm,
    stats: StreamStats,
) -> tuple[str, str | None]:
    stats.recovery_attempts += 1
    logger.warning(
        "chat empty content recovery attempt=%s prompt_len=%s content_chars=%s thinking_updates=%s",
        stats.recovery_attempts,
        len(prompt),
        stats.content_chars,
        stats.thinking_updates,
    )
    return _sync_chat_reply(
        chat_engine,
        prompt,
        capture_llm,
        disable_thinking=True,
    )


def run_chat_turn(
    *,
    project_id: str,
    conversation_id: str | None,
    message: str,
    model: str,
    workspace: str,
    profile: str | None = None,
    audit_mode: bool = False,
    use_project_memory: bool = True,
    session_rules: str = "",
    create_conversation: bool = False,
    turn_id: str | None = None,
) -> Iterator[str]:
    """Generator de linhas SSE para um turno de chat."""
    bootstrap_legacy()
    import conversation_store as conv_store
    from analytical_synthesis import run_analytical_synthesis, should_run_analytical_synthesis
    from case_memory import enrich_project_memory
    import project_memory as project_memory_store
    from app_workspace import chat_mode_for_workspace, should_run_audit_synthesis
    from audit_synthesis import run_audit_synthesis
    from answer_validator import build_retry_prompt, validate_answer
    from chat_memory import rehydrate_memory_from_messages, sync_memory_with_session
    from chat_response_utils import coalesce_assistant_reply, is_empty_llm_output
    from exhaustive_retrieval import format_audit_context, search_exhaustive
    from llama_index.core.memory import Memory
    from llama_index.core.schema import QueryBundle
    from llm_thinking import clear_captured_thinking, get_captured_thinking
    from query_expansion import expand_query
    from query_planner import plan_query
    from retrieved_chunks_ui import nodes_to_serializable
    from retrieval_pipeline import HybridRetriever
    from runtime_config import configure_runtime_env

    prompt = _normalize_user_prompt(message or "")
    if not prompt:
        yield format_sse("error", {"message": "Mensagem vazia."})
        return

    settings = configure_runtime_env()
    forced_profile = _resolve_forced_profile(profile)
    chat_mode = chat_mode_for_workspace("rag" if workspace == "rag" else "free")
    model_name = (model or settings.llm_default_model).strip()
    _model_generation_context.model_name = model_name

    stack = get_cached_stack(
        model_name,
        forced_profile,
        project_id,
        chat_mode,
        workspace,
    )
    runtime_settings = stack.settings

    rec = None
    if conversation_id:
        rec = conv_store.load(project_id, conversation_id)
    if rec is None:
        rec = conv_store.create(
            project_id,
            title="Nova conversa",
            model_name=model_name,
        )
    elif create_conversation and not rec.messages:
        pass

    messages = list(rec.messages or [])
    if turn_id:
        prior_messages = [m for m in messages if m.get("turn_id") != turn_id]
    else:
        prior_messages = list(messages)
    repeat_question = _is_repeat_question(prior_messages, prompt)
    stream_stats = StreamStats(
        repeat_question=repeat_question,
        history_messages=len(prior_messages),
    )

    memory = Memory.from_defaults(token_limit=runtime_settings.chat_memory_token_limit)
    summarize_llm = getattr(getattr(stack, "capture_llm", None), "llm", None)
    if prior_messages:
        rehydrate_memory_from_messages(
            memory,
            prior_messages,
            settings=runtime_settings,
            llm=summarize_llm,
        )
    else:
        sync_memory_with_session(
            memory,
            prior_messages,
            settings=runtime_settings,
            llm=summarize_llm,
        )

    pm = ""
    if use_project_memory and project_id:
        pm = enrich_project_memory(
            project_id,
            project_memory_store.load(project_id),
        )
    if isinstance(stack.hybrid_retriever, HybridRetriever):
        stack.hybrid_retriever.project_memory = pm

    rules = (session_rules or "").strip()
    if workspace == "free":
        chat_engine, _fallback_unused = build_chat_engines(
            stack, rules, memory, project_memory=pm, workspace="free"
        )
        fallback_chat_engine = None
    else:
        chat_engine, fallback_chat_engine = build_chat_engines(
            stack, rules, memory, project_memory=pm, workspace="rag"
        )

    if repeat_question and hasattr(chat_engine, "_skip_condense"):
        chat_engine._skip_condense = True
        stream_stats.skip_condense = True
        yield format_sse(
            "status",
            {"message": "Pergunta repetida: pulando condensacao do historico..."},
        )

    hybrid_retriever = stack.hybrid_retriever
    yield format_sse("status", {"message": "Recuperando contexto e preparando resposta..."})

    assistant_text = ""
    thinking_text = None
    used_fallback = False
    stream_interrupted = False
    interruption_reason: str | None = None
    stream_error_message: str | None = None
    telemetry = None
    retrieved_chunks: list[dict] = []
    effective_prompt = prompt
    use_audit_synthesis = False
    use_analytical_synthesis = False

    clear_captured_thinking(stack.capture_llm)

    try:
        if workspace == "rag" and isinstance(hybrid_retriever, HybridRetriever):
            plan_pre = plan_query(
                effective_prompt, runtime_settings, forced_profile=forced_profile
            )
            run_audit = should_run_audit_synthesis(
                effective_prompt,
                runtime_settings,
                forced_profile=forced_profile,
                audit_mode_ui=audit_mode,
            )
            run_analytical = (
                not run_audit
                and should_run_analytical_synthesis(
                    effective_prompt,
                    plan_pre,
                    enabled=runtime_settings.analytical_map_reduce_enabled,
                )
            )

            if run_audit:
                expanded = expand_query(
                    effective_prompt,
                    project_memory=hybrid_retriever.project_memory,
                    intent="auditoria_exaustiva",
                )
                _, audit_pages = search_exhaustive(
                    hybrid_retriever.lexical_index,
                    expanded,
                    batch_size=runtime_settings.exhaustive_batch_size,
                    max_total=runtime_settings.exhaustive_max_hits,
                    page_filter=plan_pre.requested_page,
                    page_range=plan_pre.requested_page_range,
                    source_hint=plan_pre.requested_source_hint,
                )
                if len(audit_pages) >= runtime_settings.audit_map_reduce_threshold:
                    use_audit_synthesis = True
                    yield format_sse(
                        "status",
                        {
                            "message": f"Modo auditoria: {len(audit_pages)} paginas, sintese em lotes..."
                        },
                    )

                    def _audit_progress(i: int, total: int, phase: str) -> None:
                        pass

                    if _model_generation_is_busy(model_name):
                        yield format_sse(
                            "status",
                            {
                                "message": (
                                    f"Modelo {model_name} ocupado; pergunta na fila "
                                    "aguardando a geracao anterior terminar..."
                                )
                            },
                        )
                    lease = _acquire_model_generation_slot(model_name)
                    try:
                        assistant_text = run_audit_synthesis(
                            stack.capture_llm.llm,
                            effective_prompt,
                            audit_pages,
                            pages_per_batch=runtime_settings.audit_pages_per_batch,
                            progress_callback=_audit_progress,
                        )
                    finally:
                        _release_model_generation_slot(lease)
                    if assistant_text:
                        yield format_sse("token", {"text": assistant_text})
                    hybrid_retriever.retrieve(QueryBundle(query_str=expanded))
                elif audit_pages:
                    effective_prompt = (
                        f"{effective_prompt}\n\n[Contexto varredura lexical]\n"
                        f"{format_audit_context(audit_pages)}"
                    )

            elif run_analytical:
                prior_profile = getattr(hybrid_retriever, "forced_profile", None)
                if forced_profile is None and plan_pre.profile != "pericial":
                    hybrid_retriever.forced_profile = "pericial"
                fused_nodes = hybrid_retriever.retrieve(QueryBundle(query_str=effective_prompt))
                if prior_profile is not None:
                    hybrid_retriever.forced_profile = prior_profile
                elif forced_profile is None:
                    hybrid_retriever.forced_profile = None

                if len(fused_nodes) >= runtime_settings.analytical_map_reduce_min_chunks:
                    use_analytical_synthesis = True
                    yield format_sse(
                        "status",
                        {
                            "message": (
                                f"Modo analitico: {len(fused_nodes)} trechos, "
                                "sintese em lotes..."
                            )
                        },
                    )
                    lease = _acquire_model_generation_slot(model_name)
                    try:
                        assistant_text = run_analytical_synthesis(
                            stack.capture_llm.llm,
                            effective_prompt,
                            fused_nodes,
                            chunks_per_batch=runtime_settings.analytical_chunks_per_batch,
                            max_batches=runtime_settings.analytical_max_batches,
                        )
                    finally:
                        _release_model_generation_slot(lease)
                    if assistant_text:
                        yield format_sse("token", {"text": assistant_text})
                    retrieved_chunks = nodes_to_serializable(fused_nodes)

        if not use_audit_synthesis and not use_analytical_synthesis:
            start_timeout_s = float(
                getattr(runtime_settings, "chat_stream_start_timeout_s", _STREAM_START_TIMEOUT_S)
            )
            queued_for_initial = _model_generation_is_busy(model_name)
            if queued_for_initial:
                yield format_sse(
                    "status",
                    {
                        "message": (
                            f"Modelo {model_name} ocupado; pergunta na fila "
                            "aguardando a geracao anterior terminar..."
                        )
                    },
                )
            stream_resp = _call_with_timeout(
                lambda: chat_engine.stream_chat(effective_prompt),
                timeout_s=start_timeout_s,
                label="chat_stream_start",
            )
            if queued_for_initial:
                yield format_sse(
                    "status",
                    {"message": "Modelo liberado; iniciando resposta..."},
                )
            gen = getattr(stream_resp, "response_gen", None)
            if gen is not None:
                idle_timeout_s = float(
                    getattr(runtime_settings, "chat_stream_idle_timeout_s", _STREAM_IDLE_TIMEOUT_S)
                )
                for piece, think_snap in _stream_tokens_with_idle_timeout(
                    gen,
                    stack.capture_llm,
                    idle_timeout_s=idle_timeout_s,
                    stats=stream_stats,
                ):
                    if think_snap:
                        thinking_text = think_snap
                        yield format_sse("thinking", {"text": think_snap})
                    if piece:
                        assistant_text += piece
                        yield format_sse("token", {"text": piece})
                assistant_text = coalesce_assistant_reply(
                    assistant_text,
                    stream_resp,
                    chat_engine,
                )
                if is_empty_llm_output(assistant_text):
                    recovered, recovered_thinking = _sync_chat_reply(
                        chat_engine,
                        effective_prompt,
                        stack.capture_llm,
                    )
                    if not is_empty_llm_output(recovered):
                        assistant_text = recovered
                        if recovered_thinking:
                            thinking_text = recovered_thinking
                        yield format_sse("token", {"text": assistant_text})
                    elif stream_stats.thinking_updates > 0:
                        yield format_sse(
                            "status",
                            {
                                "message": (
                                    "Modelo retornou apenas raciocinio; "
                                    "repetindo geracao sem thinking..."
                                )
                            },
                        )
                        recovered, recovered_thinking = _recover_empty_content(
                            chat_engine,
                            effective_prompt,
                            stack.capture_llm,
                            stream_stats,
                        )
                        if not is_empty_llm_output(recovered):
                            assistant_text = recovered
                            if recovered_thinking:
                                thinking_text = recovered_thinking
                            yield format_sse("token", {"text": assistant_text})
            else:
                assistant_text = coalesce_assistant_reply(
                    getattr(stream_resp, "response", "") or "",
                    stream_resp,
                    chat_engine,
                )
                if assistant_text:
                    yield format_sse("token", {"text": assistant_text})
                thinking_text = get_captured_thinking(stack.capture_llm) or _extract_thinking(
                    stream_resp
                )
                if thinking_text:
                    yield format_sse("thinking", {"text": thinking_text})

            thinking_text = (
                thinking_text
                or get_captured_thinking(stack.capture_llm)
                or _extract_thinking(stream_resp)
            )
            if is_empty_llm_output(assistant_text):
                recovered, recovered_thinking = _sync_chat_reply(
                    chat_engine,
                    effective_prompt,
                    stack.capture_llm,
                )
                if not is_empty_llm_output(recovered):
                    assistant_text = recovered
                    if recovered_thinking:
                        thinking_text = recovered_thinking
                    yield format_sse("token", {"text": assistant_text})
                elif stream_stats.thinking_updates > 0 or (
                    thinking_text and not assistant_text
                ):
                    yield format_sse(
                        "status",
                        {
                            "message": (
                                "Modelo retornou apenas raciocinio; "
                                "repetindo geracao sem thinking..."
                            )
                        },
                    )
                    recovered, recovered_thinking = _recover_empty_content(
                        chat_engine,
                        effective_prompt,
                        stack.capture_llm,
                        stream_stats,
                    )
                    if not is_empty_llm_output(recovered):
                        assistant_text = recovered
                        if recovered_thinking:
                            thinking_text = recovered_thinking
                        yield format_sse("token", {"text": assistant_text})

    except Exception as exc:
        msg = str(exc).lower()
        if workspace == "rag" and fallback_chat_engine and _reranker_runtime_error(msg):
            used_fallback = True
            yield format_sse("status", {"message": "Reranker falhou; respondendo sem reranker."})
            try:
                clear_captured_thinking(stack.capture_llm)
                start_timeout_s = float(
                    getattr(runtime_settings, "chat_stream_start_timeout_s", _STREAM_START_TIMEOUT_S)
                )
                queued_for_fallback = _model_generation_is_busy(model_name)
                if queued_for_fallback:
                    yield format_sse(
                        "status",
                        {
                            "message": (
                                f"Modelo {model_name} ocupado; fallback na fila "
                                "aguardando a geracao anterior terminar..."
                            )
                        },
                    )
                stream_fb = _call_with_timeout(
                    lambda: fallback_chat_engine.stream_chat(prompt),
                    timeout_s=start_timeout_s,
                    label="fallback_stream_start",
                )
                if queued_for_fallback:
                    yield format_sse(
                        "status",
                        {"message": "Modelo liberado; iniciando fallback..."},
                    )
                gen_fb = getattr(stream_fb, "response_gen", None)
                assistant_text = ""
                if gen_fb is not None:
                    idle_timeout_s = float(
                        getattr(runtime_settings, "chat_stream_idle_timeout_s", _STREAM_IDLE_TIMEOUT_S)
                    )
                    for piece, think_snap in _stream_tokens_with_idle_timeout(
                        gen_fb,
                        stack.capture_llm,
                        idle_timeout_s=idle_timeout_s,
                        stats=stream_stats,
                    ):
                        if think_snap:
                            thinking_text = think_snap
                            yield format_sse("thinking", {"text": think_snap})
                        if piece:
                            assistant_text += piece
                            yield format_sse("token", {"text": piece})
                    if not assistant_text:
                        assistant_text = (
                            getattr(stream_fb, "response", None)
                            or getattr(stream_fb, "unformatted_response", None)
                            or ""
                        )
                else:
                    assistant_text = getattr(stream_fb, "response", "") or ""
                    if assistant_text:
                        yield format_sse("token", {"text": assistant_text})
                    thinking_text = get_captured_thinking(
                        stack.capture_llm
                    ) or _extract_thinking(stream_fb)
            except Exception as exc_fb:
                stream_error_message = f"Falha no fallback: {exc_fb}"
                stream_interrupted = True
                interruption_reason = stream_error_message
        else:
            stream_error_message = str(exc)
            stream_interrupted = True
            interruption_reason = stream_error_message

    diagnostics = getattr(hybrid_retriever, "last_diagnostics", None)
    if workspace == "free":
        validation_level = "none"
    elif stack.chat_mode == "general":
        validation_level = "none"
    else:
        validation_level = "light"
        if diagnostics:
            validation_level = runtime_settings.retrieval_profiles[
                diagnostics.plan.profile
            ].validation_level

    if turn_id and assistant_text.strip():
        yield format_sse("status", {"message": "Validando resposta e finalizando..."})
    validation = validate_answer(
        assistant_text, diagnostics, validation_level, user_query=prompt
    )
    if stream_interrupted:
        interruption_issue = (
            "Resposta interrompida durante stream. Revise e, se necessario, repita a pergunta."
        )
        if interruption_issue not in validation.issues:
            validation.issues.append(interruption_issue)
    low_cov_fused_threshold = getattr(runtime_settings, "low_cov_fused_threshold", 0)
    auto_retry_on_low_coverage = getattr(runtime_settings, "auto_retry_on_low_coverage", False)
    low_coverage_runtime = (
        workspace == "rag"
        and diagnostics is not None
        and low_cov_fused_threshold > 0
        and diagnostics.plan.intent in ("analitico", "padrao", "historico_documental", "tese_acusacao_defesa")
        and diagnostics.fused_count < low_cov_fused_threshold
    )
    if low_coverage_runtime:
        issue = (
            f"Cobertura baixa no retrieval real (fused={diagnostics.fused_count}, "
            f"limiar={low_cov_fused_threshold})."
        )
        if issue not in validation.issues:
            validation.issues.append(issue)
        if auto_retry_on_low_coverage:
            validation.should_retry = True
            validation.retry_hint = validation.retry_hint or (
                "Amplie a cobertura com foco nos documentos correlatos e cite paginas antes de "
                "afirmar ausencia de mencao."
            )
    if _should_skip_retry_for_cosmetic_validation(validation, assistant_text):
        validation.should_retry = False
        validation.retry_hint = None
    if (
        validation.should_retry
        and workspace == "rag"
        and fallback_chat_engine
        and _model_generation_has_contention(model_name)
    ):
        retry_deferred_message = (
            "Retry automatico adiado porque outro turno aguarda o modelo; "
            "resposta inicial preservada."
        )
        stream_interrupted = True
        interruption_reason = retry_deferred_message
        validation.should_retry = False
        if retry_deferred_message not in validation.issues:
            validation.issues.append(retry_deferred_message)

    if (
        validation.should_retry
        and workspace == "rag"
        and fallback_chat_engine
    ):
        pre_retry_issues = list(validation.issues)
        pre_retry_text = assistant_text if not is_empty_llm_output(assistant_text) else ""
        pre_retry_thinking = thinking_text
        retry_failed_message: str | None = None
        yield format_sse(
            "status",
            {
                "message": _retry_status_message(pre_retry_issues),
                "reset_stream": True,
            },
        )
        retry_prompt = build_retry_prompt(prompt, validation)
        clear_captured_thinking(stack.capture_llm)
        prior_forced_profile = getattr(hybrid_retriever, "forced_profile", None)
        if isinstance(hybrid_retriever, HybridRetriever):
            hybrid_retriever.forced_profile = "pericial"
        retry_resp = None
        try:
            start_timeout_s = float(
                getattr(runtime_settings, "chat_stream_start_timeout_s", _STREAM_START_TIMEOUT_S)
            )
            queued_for_retry = _model_generation_is_busy(model_name)
            if queued_for_retry:
                yield format_sse(
                    "status",
                    {
                        "message": (
                            f"Modelo {model_name} ocupado; retry na fila "
                            "aguardando a geracao anterior terminar..."
                        )
                    },
                )
            retry_resp = _call_with_timeout(
                lambda: fallback_chat_engine.stream_chat(retry_prompt),
                timeout_s=start_timeout_s,
                label="retry_stream_start",
            )
            if queued_for_retry:
                yield format_sse(
                    "status",
                    {"message": "Modelo liberado; iniciando retry..."},
                )
            assistant_text = ""
            thinking_text = None
            gen_retry = getattr(retry_resp, "response_gen", None)
            if gen_retry is not None:
                idle_timeout_s = float(
                    getattr(runtime_settings, "chat_stream_idle_timeout_s", _STREAM_IDLE_TIMEOUT_S)
                )
                for piece, think_snap in _stream_tokens_with_idle_timeout(
                    gen_retry,
                    stack.capture_llm,
                    idle_timeout_s=idle_timeout_s,
                    stats=stream_stats,
                ):
                    if think_snap:
                        thinking_text = think_snap
                        yield format_sse("thinking", {"text": think_snap})
                    if piece:
                        assistant_text += piece
                        yield format_sse("token", {"text": piece})
                assistant_text = coalesce_assistant_reply(
                    assistant_text,
                    retry_resp,
                    fallback_chat_engine,
                )
            else:
                assistant_text = coalesce_assistant_reply(
                    getattr(retry_resp, "response", "") or "",
                    retry_resp,
                    fallback_chat_engine,
                )
                if assistant_text:
                    yield format_sse("token", {"text": assistant_text})
                thinking_text = get_captured_thinking(
                    stack.capture_llm
                ) or _extract_thinking(retry_resp)
                if thinking_text:
                    yield format_sse("thinking", {"text": thinking_text})
            if is_empty_llm_output(assistant_text):
                recovered, recovered_thinking = _sync_chat_reply(
                    fallback_chat_engine,
                    retry_prompt,
                    stack.capture_llm,
                )
                if not is_empty_llm_output(recovered):
                    assistant_text = recovered
                    if recovered_thinking:
                        thinking_text = recovered_thinking
                        yield format_sse("thinking", {"text": thinking_text})
                    yield format_sse("token", {"text": assistant_text})
                elif stream_stats.thinking_updates > 0 or (
                    thinking_text and not assistant_text
                ):
                    yield format_sse(
                        "status",
                        {
                            "message": (
                                "Modelo retornou apenas raciocinio no retry; "
                                "repetindo geracao sem thinking..."
                            )
                        },
                    )
                    recovered, recovered_thinking = _recover_empty_content(
                        fallback_chat_engine,
                        retry_prompt,
                        stack.capture_llm,
                        stream_stats,
                    )
                    if not is_empty_llm_output(recovered):
                        assistant_text = recovered
                        if recovered_thinking:
                            thinking_text = recovered_thinking
                            yield format_sse("thinking", {"text": thinking_text})
                        yield format_sse("token", {"text": assistant_text})
            if is_empty_llm_output(assistant_text) and not is_empty_llm_output(pre_retry_text):
                assistant_text = pre_retry_text
                thinking_text = pre_retry_thinking or thinking_text
            thinking_text = (
                thinking_text
                or get_captured_thinking(stack.capture_llm)
                or (_extract_thinking(retry_resp) if retry_resp is not None else None)
            )
        except Exception as exc_retry:
            retry_failed_message = f"Retry automatico falhou: {exc_retry}"
            stream_interrupted = True
            interruption_reason = retry_failed_message
            if not is_empty_llm_output(pre_retry_text):
                assistant_text = pre_retry_text
                thinking_text = pre_retry_thinking
            else:
                stream_error_message = retry_failed_message
        finally:
            if isinstance(hybrid_retriever, HybridRetriever):
                hybrid_retriever.forced_profile = prior_forced_profile
        used_fallback = True
        diagnostics = getattr(hybrid_retriever, "last_diagnostics", diagnostics)
        validation = validate_answer(
            assistant_text, diagnostics, validation_level, user_query=prompt
        )
        for issue in pre_retry_issues:
            if issue not in validation.issues:
                validation.issues.append(issue)
        if retry_failed_message and retry_failed_message not in validation.issues:
            validation.issues.append(retry_failed_message)

    if workspace == "free":
        telemetry = "modo=chat_livre"
    elif stack.chat_mode == "general":
        telemetry = "modo=geral"
    elif diagnostics:
        telemetry = (
            f"modo=rag | Estrategia: {diagnostics.plan.profile} ({diagnostics.plan.intent}) | "
            f"semantico={diagnostics.semantic_count} | "
            f"lexical={diagnostics.lexical_count} | "
            f"fused={diagnostics.fused_count} | "
            f"literal_hits={diagnostics.literal_count}"
        )
        if getattr(diagnostics, "multi_query_count", 1) > 1:
            telemetry += f" | multi_query={diagnostics.multi_query_count}"
        if getattr(diagnostics, "graph_expansion_count", 0):
            telemetry += f" | cross_doc={diagnostics.graph_expansion_count}"
        if getattr(diagnostics, "entity_boost_count", 0):
            telemetry += f" | entity_boost={diagnostics.entity_boost_count}"
        if getattr(diagnostics, "parent_context_count", 0):
            telemetry += f" | parent_context={diagnostics.parent_context_count}"
    if telemetry and used_fallback:
        telemetry += " | fallback=on"
    if telemetry and validation.issues:
        telemetry += " | validacao: " + "; ".join(validation.issues)
    if telemetry:
        telemetry += f" | gen={stream_stats.as_dict()}"

    if workspace == "rag" and isinstance(hybrid_retriever, HybridRetriever):
        retrieved_chunks = nodes_to_serializable(hybrid_retriever.last_retrieved_nodes)

    if not turn_id:
        messages = list(prior_messages)
        if not is_empty_llm_output(assistant_text):
            messages.append({"role": "user", "content": prompt})
            payload = {"role": "assistant", "content": assistant_text}
            if thinking_text:
                payload["thinking"] = thinking_text
            if telemetry:
                payload["telemetry"] = telemetry
            if retrieved_chunks:
                payload["retrieved_chunks"] = retrieved_chunks
            if validation.issues:
                payload["validation_issues"] = validation.issues
            messages.append(payload)
        elif not stream_error_message:
            stream_error_message = _empty_response_message(
                stats=stream_stats,
                thinking_text=thinking_text,
                diagnostics=diagnostics,
            )
            logger.error(
                "chat empty assistant response project=%s conversation=%s diag=%s thinking_len=%s",
                project_id,
                rec.conversation_id,
                stream_stats.as_dict(),
                len(thinking_text or ""),
            )

        rec.messages = messages
        rec.model_name = model_name or rec.model_name
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if len(user_msgs) == 1 and rec.title.strip() in ("Nova conversa", ""):
            rec.title = _title_from_first_user_message(str(user_msgs[0].get("content", "")))
        conv_store.save(project_id, rec)
    else:
        if not stream_error_message and is_empty_llm_output(assistant_text):
            stream_error_message = _empty_response_message(
                stats=stream_stats,
                thinking_text=thinking_text,
                diagnostics=diagnostics,
            )
        rec_fresh = conv_store.load(project_id, rec.conversation_id)
        if rec_fresh is not None:
            user_msgs = [m for m in rec_fresh.messages if m.get("role") == "user"]
            if len(user_msgs) == 1 and rec_fresh.title.strip() in ("Nova conversa", ""):
                rec_fresh.title = _title_from_first_user_message(
                    str(user_msgs[0].get("content", ""))
                )
                conv_store.save(project_id, rec_fresh)

    if stream_error_message and is_empty_llm_output(assistant_text):
        yield format_sse(
            "error",
            {
                "message": stream_error_message,
                "generation_diag": stream_stats.as_dict(),
            },
        )
        return

    yield format_sse(
        "meta",
        {
            "conversation_id": rec.conversation_id,
            "telemetry": telemetry,
            "retrieved_chunks": retrieved_chunks,
            "validation_issues": validation.issues,
            "generation_diag": stream_stats.as_dict(),
        },
    )
    done_payload = {
        "assistant_text": assistant_text,
        "thinking": thinking_text,
        "conversation_id": rec.conversation_id,
        "interrupted": stream_interrupted,
        "interruption_reason": interruption_reason,
        "generation_diag": stream_stats.as_dict(),
    }
    if telemetry:
        done_payload["telemetry"] = telemetry
    if retrieved_chunks:
        done_payload["retrieved_chunks"] = retrieved_chunks
    if validation.issues:
        done_payload["validation_issues"] = validation.issues
    yield format_sse("done", done_payload)


def start_async_chat_turn(
    *,
    project_id: str,
    conversation_id: str | None,
    message: str,
    model: str,
    workspace: str,
    profile: str | None = None,
    audit_mode: bool = False,
    use_project_memory: bool = True,
    session_rules: str = "",
) -> dict[str, str]:
    from services.chat_turn_runner import start_turn_job
    from services.chat_turn_store import begin_turn

    begun = begin_turn(
        project_id=project_id,
        conversation_id=conversation_id,
        user_content=message,
        model_name=model,
    )

    turn_kwargs = dict(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        message=message,
        model=model,
        workspace=workspace,
        profile=profile,
        audit_mode=audit_mode,
        use_project_memory=use_project_memory,
        session_rules=session_rules,
        turn_id=begun.turn_id,
    )

    def _run():
        yield from run_chat_turn(**turn_kwargs)

    start_turn_job(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        run_turn=_run,
    )
    return {"turn_id": begun.turn_id, "conversation_id": begun.conversation_id}


async def async_chat_sse(**kwargs) -> AsyncIterator[str]:
    for line in run_chat_turn(**kwargs):
        yield line
        await _async_yield()

async def _async_yield():
    import asyncio
    await asyncio.sleep(0)
