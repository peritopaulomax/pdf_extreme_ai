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



@dataclass
class _ChatTurnState:
    """Estado mutável compartilhado durante um turno de chat."""

    project_id: str
    conversation_id: str | None
    prompt: str
    model_name: str
    workspace: str
    profile: str | None
    audit_mode: bool
    use_project_memory: bool
    session_rules: str
    create_conversation: bool
    turn_id: str | None
    stack: Any
    runtime_settings: Any
    rec: Any
    prior_messages: list[dict]
    stream_stats: StreamStats
    memory: Any
    project_memory: str
    chat_engine: Any
    fallback_chat_engine: Any | None
    hybrid_retriever: Any
    assistant_text: str = ""
    thinking_text: str | None = None
    used_fallback: bool = False
    stream_interrupted: bool = False
    interruption_reason: str | None = None
    stream_error_message: str | None = None
    telemetry: str | None = None
    retrieved_chunks: list[dict] = field(default_factory=list)
    effective_prompt: str = ""
    use_audit_synthesis: bool = False
    use_analytical_synthesis: bool = False
    diagnostics: Any = None
    validation: Any = None


def _load_turn_state(
    *,
    project_id: str,
    conversation_id: str | None,
    message: str,
    model: str,
    workspace: str,
    profile: str | None,
    audit_mode: bool,
    use_project_memory: bool,
    session_rules: str,
    create_conversation: bool,
    turn_id: str | None,
) -> _ChatTurnState:
    """Carrega conversa, stack, memória e engines."""
    bootstrap_legacy()
    import conversation_store as conv_store
    from case_memory import enrich_project_memory
    import project_memory as project_memory_store
    from app_workspace import chat_mode_for_workspace
    from chat_memory import rehydrate_memory_from_messages, sync_memory_with_session
    from llama_index.core.memory import Memory
    from retrieval_pipeline import HybridRetriever
    from runtime_config import configure_runtime_env

    prompt = _normalize_user_prompt(message or "")
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
        if create_conversation and conversation_id:
            rec.conversation_id = conversation_id
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

    hybrid_retriever = stack.hybrid_retriever

    return _ChatTurnState(
        project_id=project_id,
        conversation_id=conversation_id,
        prompt=prompt,
        model_name=model_name,
        workspace=workspace,
        profile=profile,
        audit_mode=audit_mode,
        use_project_memory=use_project_memory,
        session_rules=session_rules,
        create_conversation=create_conversation,
        turn_id=turn_id,
        stack=stack,
        runtime_settings=runtime_settings,
        rec=rec,
        prior_messages=prior_messages,
        stream_stats=stream_stats,
        memory=memory,
        project_memory=pm,
        chat_engine=chat_engine,
        fallback_chat_engine=fallback_chat_engine,
        hybrid_retriever=hybrid_retriever,
        effective_prompt=prompt,
    )


def _run_audit_synthesis(state: _ChatTurnState) -> Iterator[str]:
    """Executa síntese de auditoria quando a intenção exige varredura exaustiva."""
    from llama_index.core.schema import QueryBundle
    from query_expansion import expand_query
    from audit_synthesis import run_audit_synthesis
    from exhaustive_retrieval import format_audit_context, search_exhaustive
    from query_planner import plan_query

    hybrid_retriever = state.hybrid_retriever
    runtime_settings = state.runtime_settings
    effective_prompt = state.effective_prompt
    model_name = state.model_name

    plan_pre = plan_query(
        effective_prompt, runtime_settings, forced_profile=_resolve_forced_profile(state.profile)
    )
    expanded = expand_query(
        effective_prompt,
        project_memory=getattr(hybrid_retriever, "project_memory", ""),
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
        state.use_audit_synthesis = True
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
            state.assistant_text = run_audit_synthesis(
                state.stack.capture_llm.llm,
                effective_prompt,
                audit_pages,
                pages_per_batch=runtime_settings.audit_pages_per_batch,
                progress_callback=_audit_progress,
            )
        finally:
            _release_model_generation_slot(lease)
        if state.assistant_text:
            yield format_sse("token", {"text": state.assistant_text})
        hybrid_retriever.retrieve(QueryBundle(query_str=expanded))
    elif audit_pages:
        state.effective_prompt = (
            f"{effective_prompt}\n\n[Contexto varredura lexical]\n"
            f"{format_audit_context(audit_pages)}"
        )


def _run_analytical_synthesis(state: _ChatTurnState) -> Iterator[str]:
    """Executa síntese analítica em modo map-reduce sobre chunks recuperados."""
    from llama_index.core.schema import QueryBundle
    from analytical_synthesis import run_analytical_synthesis, should_run_analytical_synthesis
    from query_planner import plan_query
    from retrieved_chunks_ui import nodes_to_serializable

    hybrid_retriever = state.hybrid_retriever
    runtime_settings = state.runtime_settings
    effective_prompt = state.effective_prompt
    model_name = state.model_name
    forced_profile = _resolve_forced_profile(state.profile)

    plan_pre = plan_query(effective_prompt, runtime_settings, forced_profile=forced_profile)
    if not should_run_analytical_synthesis(
        effective_prompt,
        plan_pre,
        enabled=getattr(runtime_settings, "analytical_map_reduce_enabled", False),
    ):
        return

    prior_profile = getattr(hybrid_retriever, "forced_profile", None)
    if forced_profile is None and plan_pre.profile != "pericial":
        hybrid_retriever.forced_profile = "pericial"
    fused_nodes = hybrid_retriever.retrieve(QueryBundle(query_str=effective_prompt))
    if prior_profile is not None:
        hybrid_retriever.forced_profile = prior_profile
    elif forced_profile is None:
        hybrid_retriever.forced_profile = None

    if len(fused_nodes) >= getattr(runtime_settings, "analytical_map_reduce_min_chunks", 10):
        state.use_analytical_synthesis = True
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
            state.assistant_text = run_analytical_synthesis(
                state.stack.capture_llm.llm,
                effective_prompt,
                fused_nodes,
                chunks_per_batch=getattr(runtime_settings, "analytical_chunks_per_batch", 5),
                max_batches=getattr(runtime_settings, "analytical_max_batches", 6),
            )
        finally:
            _release_model_generation_slot(lease)
        if state.assistant_text:
            yield format_sse("token", {"text": state.assistant_text})
        state.retrieved_chunks = nodes_to_serializable(fused_nodes)


def _stream_response_from_engine(
    state: _ChatTurnState,
    chat_engine,
    prompt: str,
    *,
    label_prefix: str,
) -> Iterator[str]:
    """Faz streaming de uma resposta a partir de um chat_engine."""
    from chat_response_utils import coalesce_assistant_reply, is_empty_llm_output
    from llm_thinking import clear_captured_thinking, get_captured_thinking

    runtime_settings = state.runtime_settings
    model_name = state.model_name
    stream_stats = state.stream_stats
    capture_llm = state.stack.capture_llm

    start_timeout_s = float(
        getattr(runtime_settings, "chat_stream_start_timeout_s", _STREAM_START_TIMEOUT_S)
    )
    queued = _model_generation_is_busy(model_name)
    if queued:
        yield format_sse(
            "status",
            {
                "message": (
                    f"Modelo {model_name} ocupado; {label_prefix} na fila "
                    "aguardando a geracao anterior terminar..."
                )
            },
        )
    stream_resp = _call_with_timeout(
        lambda: chat_engine.stream_chat(prompt),
        timeout_s=start_timeout_s,
        label=f"{label_prefix}_stream_start",
    )
    if queued:
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
            capture_llm,
            idle_timeout_s=idle_timeout_s,
            stats=stream_stats,
        ):
            if think_snap:
                state.thinking_text = think_snap
                yield format_sse("thinking", {"text": think_snap})
            if piece:
                state.assistant_text += piece
                yield format_sse("token", {"text": piece})
        state.assistant_text = coalesce_assistant_reply(
            state.assistant_text,
            stream_resp,
            chat_engine,
        )
        if is_empty_llm_output(state.assistant_text):
            recovered, recovered_thinking = _sync_chat_reply(
                chat_engine,
                prompt,
                capture_llm,
            )
            if not is_empty_llm_output(recovered):
                state.assistant_text = recovered
                if recovered_thinking:
                    state.thinking_text = recovered_thinking
                yield format_sse("token", {"text": state.assistant_text})
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
                    prompt,
                    capture_llm,
                    stream_stats,
                )
                if not is_empty_llm_output(recovered):
                    state.assistant_text = recovered
                    if recovered_thinking:
                        state.thinking_text = recovered_thinking
                    yield format_sse("token", {"text": state.assistant_text})
    else:
        state.assistant_text = coalesce_assistant_reply(
            getattr(stream_resp, "response", "") or "",
            stream_resp,
            chat_engine,
        )
        if state.assistant_text:
            yield format_sse("token", {"text": state.assistant_text})
        state.thinking_text = get_captured_thinking(capture_llm) or _extract_thinking(
            stream_resp
        )
        if state.thinking_text:
            yield format_sse("thinking", {"text": state.thinking_text})

    state.thinking_text = (
        state.thinking_text
        or get_captured_thinking(capture_llm)
        or _extract_thinking(stream_resp)
    )
    if is_empty_llm_output(state.assistant_text):
        recovered, recovered_thinking = _sync_chat_reply(
            chat_engine,
            prompt,
            capture_llm,
        )
        if not is_empty_llm_output(recovered):
            state.assistant_text = recovered
            if recovered_thinking:
                state.thinking_text = recovered_thinking
            yield format_sse("token", {"text": state.assistant_text})
        elif stream_stats.thinking_updates > 0 or (
            state.thinking_text and not state.assistant_text
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
                prompt,
                capture_llm,
                stream_stats,
            )
            if not is_empty_llm_output(recovered):
                state.assistant_text = recovered
                if recovered_thinking:
                    state.thinking_text = recovered_thinking
                yield format_sse("token", {"text": state.assistant_text})


def _run_fallback_response(state: _ChatTurnState, exc: Exception) -> Iterator[str]:
    """Tenta responder sem reranker quando ele falha."""
    from chat_response_utils import coalesce_assistant_reply, is_empty_llm_output
    from llm_thinking import clear_captured_thinking, get_captured_thinking

    fallback_chat_engine = state.fallback_chat_engine
    if fallback_chat_engine is None:
        raise exc

    state.used_fallback = True
    yield format_sse("status", {"message": "Reranker falhou; respondendo sem reranker."})

    runtime_settings = state.runtime_settings
    model_name = state.model_name
    stream_stats = state.stream_stats
    capture_llm = state.stack.capture_llm
    prompt = state.prompt

    try:
        clear_captured_thinking(capture_llm)
        start_timeout_s = float(
            getattr(runtime_settings, "chat_stream_start_timeout_s", _STREAM_START_TIMEOUT_S)
        )
        queued = _model_generation_is_busy(model_name)
        if queued:
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
        if queued:
            yield format_sse(
                "status",
                {"message": "Modelo liberado; iniciando fallback..."},
            )
        gen_fb = getattr(stream_fb, "response_gen", None)
        state.assistant_text = ""
        if gen_fb is not None:
            idle_timeout_s = float(
                getattr(runtime_settings, "chat_stream_idle_timeout_s", _STREAM_IDLE_TIMEOUT_S)
            )
            for piece, think_snap in _stream_tokens_with_idle_timeout(
                gen_fb,
                capture_llm,
                idle_timeout_s=idle_timeout_s,
                stats=stream_stats,
            ):
                if think_snap:
                    state.thinking_text = think_snap
                    yield format_sse("thinking", {"text": think_snap})
                if piece:
                    state.assistant_text += piece
                    yield format_sse("token", {"text": piece})
            if not state.assistant_text:
                state.assistant_text = (
                    getattr(stream_fb, "response", None)
                    or getattr(stream_fb, "unformatted_response", None)
                    or ""
                )
        else:
            state.assistant_text = getattr(stream_fb, "response", "") or ""
            if state.assistant_text:
                yield format_sse("token", {"text": state.assistant_text})
            state.thinking_text = get_captured_thinking(
                capture_llm
            ) or _extract_thinking(stream_fb)
    except Exception as exc_fb:
        state.stream_error_message = f"Falha no fallback: {exc_fb}"
        state.stream_interrupted = True
        state.interruption_reason = state.stream_error_message


def _run_retry(state: _ChatTurnState, validation) -> Iterator[str]:
    """Executa retry automático via fallback_engine quando a validação pede."""
    from answer_validator import build_retry_prompt
    from chat_response_utils import coalesce_assistant_reply, is_empty_llm_output
    from llm_thinking import clear_captured_thinking, get_captured_thinking
    from retrieval_pipeline import HybridRetriever

    fallback_chat_engine = state.fallback_chat_engine
    if fallback_chat_engine is None:
        return

    pre_retry_issues = list(validation.issues)
    pre_retry_text = state.assistant_text if not is_empty_llm_output(state.assistant_text) else ""
    pre_retry_thinking = state.thinking_text
    retry_failed_message: str | None = None

    yield format_sse(
        "status",
        {
            "message": _retry_status_message(pre_retry_issues),
            "reset_stream": True,
        },
    )

    retry_prompt = build_retry_prompt(state.prompt, validation)
    clear_captured_thinking(state.stack.capture_llm)
    hybrid_retriever = state.hybrid_retriever
    prior_forced_profile = getattr(hybrid_retriever, "forced_profile", None)
    if isinstance(hybrid_retriever, HybridRetriever):
        hybrid_retriever.forced_profile = "pericial"

    retry_resp = None
    try:
        runtime_settings = state.runtime_settings
        model_name = state.model_name
        capture_llm = state.stack.capture_llm
        stream_stats = state.stream_stats

        start_timeout_s = float(
            getattr(runtime_settings, "chat_stream_start_timeout_s", _STREAM_START_TIMEOUT_S)
        )
        queued = _model_generation_is_busy(model_name)
        if queued:
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
        if queued:
            yield format_sse(
                "status",
                {"message": "Modelo liberado; iniciando retry..."},
            )
        state.assistant_text = ""
        state.thinking_text = None
        gen_retry = getattr(retry_resp, "response_gen", None)
        if gen_retry is not None:
            idle_timeout_s = float(
                getattr(runtime_settings, "chat_stream_idle_timeout_s", _STREAM_IDLE_TIMEOUT_S)
            )
            for piece, think_snap in _stream_tokens_with_idle_timeout(
                gen_retry,
                capture_llm,
                idle_timeout_s=idle_timeout_s,
                stats=stream_stats,
            ):
                if think_snap:
                    state.thinking_text = think_snap
                    yield format_sse("thinking", {"text": think_snap})
                if piece:
                    state.assistant_text += piece
                    yield format_sse("token", {"text": piece})
            state.assistant_text = coalesce_assistant_reply(
                state.assistant_text,
                retry_resp,
                fallback_chat_engine,
            )
        else:
            state.assistant_text = coalesce_assistant_reply(
                getattr(retry_resp, "response", "") or "",
                retry_resp,
                fallback_chat_engine,
            )
            if state.assistant_text:
                yield format_sse("token", {"text": state.assistant_text})
            state.thinking_text = get_captured_thinking(
                capture_llm
            ) or _extract_thinking(retry_resp)
            if state.thinking_text:
                yield format_sse("thinking", {"text": state.thinking_text})

        if is_empty_llm_output(state.assistant_text):
            recovered, recovered_thinking = _sync_chat_reply(
                fallback_chat_engine,
                retry_prompt,
                capture_llm,
            )
            if not is_empty_llm_output(recovered):
                state.assistant_text = recovered
                if recovered_thinking:
                    state.thinking_text = recovered_thinking
                    yield format_sse("thinking", {"text": state.thinking_text})
                yield format_sse("token", {"text": state.assistant_text})
            elif stream_stats.thinking_updates > 0 or (
                state.thinking_text and not state.assistant_text
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
                    capture_llm,
                    stream_stats,
                )
                if not is_empty_llm_output(recovered):
                    state.assistant_text = recovered
                    if recovered_thinking:
                        state.thinking_text = recovered_thinking
                        yield format_sse("thinking", {"text": state.thinking_text})
                    yield format_sse("token", {"text": state.assistant_text})

        if is_empty_llm_output(state.assistant_text) and not is_empty_llm_output(pre_retry_text):
            state.assistant_text = pre_retry_text
            state.thinking_text = pre_retry_thinking or state.thinking_text

        state.thinking_text = (
            state.thinking_text
            or get_captured_thinking(capture_llm)
            or (_extract_thinking(retry_resp) if retry_resp is not None else None)
        )
    except Exception as exc_retry:
        retry_failed_message = f"Retry automatico falhou: {exc_retry}"
        state.stream_interrupted = True
        state.interruption_reason = retry_failed_message
        if not is_empty_llm_output(pre_retry_text):
            state.assistant_text = pre_retry_text
            state.thinking_text = pre_retry_thinking
        else:
            state.stream_error_message = retry_failed_message
    finally:
        if isinstance(hybrid_retriever, HybridRetriever):
            hybrid_retriever.forced_profile = prior_forced_profile

    state.used_fallback = True
    state.diagnostics = getattr(hybrid_retriever, "last_diagnostics", state.diagnostics)
    _revalidate_after_retry(state, pre_retry_issues, retry_failed_message)


def _revalidate_after_retry(
    state: _ChatTurnState,
    pre_retry_issues: list[str],
    retry_failed_message: str | None,
) -> None:
    """Revalida a resposta após retry e acrescenta issues anteriores."""
    from answer_validator import validate_answer

    diagnostics = state.diagnostics
    validation_level = _resolve_validation_level(state)
    validation = validate_answer(
        state.assistant_text, diagnostics, validation_level, user_query=state.prompt
    )
    for issue in pre_retry_issues:
        if issue not in validation.issues:
            validation.issues.append(issue)
    if retry_failed_message and retry_failed_message not in validation.issues:
        validation.issues.append(retry_failed_message)
    state.validation = validation


def _resolve_validation_level(state: _ChatTurnState) -> str:
    diagnostics = getattr(state.hybrid_retriever, "last_diagnostics", None)
    if state.workspace == "free":
        return "none"
    if state.stack.chat_mode == "general":
        return "none"
    if diagnostics:
        return state.runtime_settings.retrieval_profiles[diagnostics.plan.profile].validation_level
    return "light"


def _compute_telemetry(state: _ChatTurnState) -> str | None:
    diagnostics = getattr(state.hybrid_retriever, "last_diagnostics", None)
    if state.workspace == "free":
        telemetry = "modo=chat_livre"
    elif state.stack.chat_mode == "general":
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
    else:
        telemetry = None

    if telemetry and state.used_fallback:
        telemetry += " | fallback=on"
    if telemetry and getattr(state, "validation", None) and state.validation.issues:
        telemetry += " | validacao: " + "; ".join(state.validation.issues)
    if telemetry:
        telemetry += f" | gen={state.stream_stats.as_dict()}"
    return telemetry


def _persist_conversation(state: _ChatTurnState) -> None:
    """Persiste mensagens e atualiza título da conversa."""
    import conversation_store as conv_store
    from chat_response_utils import is_empty_llm_output

    rec = state.rec
    project_id = state.project_id
    turn_id = state.turn_id
    prompt = state.prompt
    assistant_text = state.assistant_text
    thinking_text = state.thinking_text
    telemetry = state.telemetry
    retrieved_chunks = state.retrieved_chunks
    validation = getattr(state, "validation", None)
    stream_error_message = state.stream_error_message
    stream_stats = state.stream_stats
    diagnostics = getattr(state.hybrid_retriever, "last_diagnostics", None)

    if not turn_id:
        messages = list(state.prior_messages)
        if not is_empty_llm_output(assistant_text):
            messages.append({"role": "user", "content": prompt})
            payload = {"role": "assistant", "content": assistant_text}
            if thinking_text:
                payload["thinking"] = thinking_text
            if telemetry:
                payload["telemetry"] = telemetry
            if retrieved_chunks:
                payload["retrieved_chunks"] = retrieved_chunks
            if validation and validation.issues:
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
            state.stream_error_message = stream_error_message

        rec.messages = messages
        rec.model_name = state.model_name or rec.model_name
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
            state.stream_error_message = stream_error_message
        rec_fresh = conv_store.load(project_id, rec.conversation_id)
        if rec_fresh is not None:
            user_msgs = [m for m in rec_fresh.messages if m.get("role") == "user"]
            if len(user_msgs) == 1 and rec_fresh.title.strip() in ("Nova conversa", ""):
                rec_fresh.title = _title_from_first_user_message(
                    str(user_msgs[0].get("content", ""))
                )
                conv_store.save(project_id, rec_fresh)


def _emit_final_events(state: _ChatTurnState) -> Iterator[str]:
    """Emite eventos finais SSE (error, meta, done)."""
    from chat_response_utils import is_empty_llm_output

    if state.stream_error_message and is_empty_llm_output(state.assistant_text):
        yield format_sse(
            "error",
            {
                "message": state.stream_error_message,
                "generation_diag": state.stream_stats.as_dict(),
            },
        )
        return

    validation = getattr(state, "validation", None)
    yield format_sse(
        "meta",
        {
            "conversation_id": state.rec.conversation_id,
            "telemetry": state.telemetry,
            "retrieved_chunks": state.retrieved_chunks,
            "validation_issues": validation.issues if validation else [],
            "generation_diag": state.stream_stats.as_dict(),
        },
    )
    done_payload = {
        "assistant_text": state.assistant_text,
        "thinking": state.thinking_text,
        "conversation_id": state.rec.conversation_id,
        "interrupted": state.stream_interrupted,
        "interruption_reason": state.interruption_reason,
        "generation_diag": state.stream_stats.as_dict(),
    }
    if state.telemetry:
        done_payload["telemetry"] = state.telemetry
    if state.retrieved_chunks:
        done_payload["retrieved_chunks"] = state.retrieved_chunks
    if validation and validation.issues:
        done_payload["validation_issues"] = validation.issues
    yield format_sse("done", done_payload)


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
    from answer_validator import validate_answer
    from app_workspace import should_run_audit_synthesis
    from chat_response_utils import is_empty_llm_output
    from llm_thinking import clear_captured_thinking
    from retrieval_pipeline import HybridRetriever

    state = _load_turn_state(
        project_id=project_id,
        conversation_id=conversation_id,
        message=message,
        model=model,
        workspace=workspace,
        profile=profile,
        audit_mode=audit_mode,
        use_project_memory=use_project_memory,
        session_rules=session_rules,
        create_conversation=create_conversation,
        turn_id=turn_id,
    )

    if state.stream_stats.repeat_question:
        yield format_sse(
            "status",
            {"message": "Pergunta repetida: pulando condensacao do historico..."},
        )

    yield format_sse("status", {"message": "Recuperando contexto e preparando resposta..."})
    clear_captured_thinking(state.stack.capture_llm)

    try:
        if state.workspace == "rag" and isinstance(state.hybrid_retriever, HybridRetriever):
            run_audit = should_run_audit_synthesis(
                state.effective_prompt,
                state.runtime_settings,
                forced_profile=_resolve_forced_profile(state.profile),
                audit_mode_ui=state.audit_mode,
            )
            if run_audit:
                yield from _run_audit_synthesis(state)

            if not state.use_audit_synthesis:
                yield from _run_analytical_synthesis(state)

        if not state.use_audit_synthesis and not state.use_analytical_synthesis:
            yield from _stream_response_from_engine(
                state,
                state.chat_engine,
                state.effective_prompt,
                label_prefix="pergunta",
            )
    except Exception as exc:
        msg = str(exc).lower()
        if state.workspace == "rag" and state.fallback_chat_engine and _reranker_runtime_error(msg):
            yield from _run_fallback_response(state, exc)
        else:
            state.stream_error_message = str(exc)
            state.stream_interrupted = True
            state.interruption_reason = state.stream_error_message

    validation_level = _resolve_validation_level(state)
    diagnostics = getattr(state.hybrid_retriever, "last_diagnostics", None)

    if state.turn_id and state.assistant_text.strip():
        yield format_sse("status", {"message": "Validando resposta e finalizando..."})

    validation = validate_answer(
        state.assistant_text, diagnostics, validation_level, user_query=state.prompt
    )
    if state.stream_interrupted:
        interruption_issue = (
            "Resposta interrompida durante stream. Revise e, se necessario, repita a pergunta."
        )
        if interruption_issue not in validation.issues:
            validation.issues.append(interruption_issue)

    runtime_settings = state.runtime_settings
    low_cov_fused_threshold = getattr(runtime_settings, "low_cov_fused_threshold", 0)
    auto_retry_on_low_coverage = getattr(runtime_settings, "auto_retry_on_low_coverage", False)
    low_coverage_runtime = (
        state.workspace == "rag"
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

    if _should_skip_retry_for_cosmetic_validation(validation, state.assistant_text):
        validation.should_retry = False
        validation.retry_hint = None

    if (
        validation.should_retry
        and state.workspace == "rag"
        and state.fallback_chat_engine
        and _model_generation_has_contention(state.model_name)
    ):
        retry_deferred_message = (
            "Retry automatico adiado porque outro turno aguarda o modelo; "
            "resposta inicial preservada."
        )
        state.stream_interrupted = True
        state.interruption_reason = retry_deferred_message
        validation.should_retry = False
        if retry_deferred_message not in validation.issues:
            validation.issues.append(retry_deferred_message)

    state.validation = validation

    if validation.should_retry and state.workspace == "rag" and state.fallback_chat_engine:
        yield from _run_retry(state, validation)

    if state.workspace == "rag" and isinstance(state.hybrid_retriever, HybridRetriever):
        from retrieved_chunks_ui import nodes_to_serializable
        state.retrieved_chunks = nodes_to_serializable(state.hybrid_retriever.last_retrieved_nodes)

    state.telemetry = _compute_telemetry(state)
    _persist_conversation(state)
    yield from _emit_final_events(state)


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
