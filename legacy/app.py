import os

import sys
from pathlib import Path

# Bootstrap paths antes de qualquer import do core
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
import bootstrap_paths

bootstrap_paths.setup()

# 1. Deleta as variáveis que causam o erro no httpx/socks
proxies_para_remover = ['all_proxy', 'ALL_PROXY', 'socks_proxy', 'SOCKS_PROXY']
for proxy in proxies_para_remover:
    os.environ.pop(proxy, None)

# 2. Garante que requisições locais ignorem os proxies restantes (http/https)
os.environ['no_proxy'] = 'localhost,127.0.0.1,0.0.0.0,::1'
os.environ['NO_PROXY'] = 'localhost,127.0.0.1,0.0.0.0,::1'
import tempfile
import hashlib
import subprocess
import time
import shutil
import base64
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import streamlit as st
import streamlit.components.v1 as components
import torch
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.schema import QueryBundle
from llama_index.core.chat_engine import CondensePlusContextChatEngine
from llama_index.core.memory import Memory

import llama_index_stream_queue_patch

llama_index_stream_queue_patch.apply()
from llama_index.core.postprocessor import (
    MetadataReplacementPostProcessor,
    SentenceTransformerRerank,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from ollama_thinking_stream import OllamaThinkingStream
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointIdsList

import conversation_store as conv_store

from answer_validator import build_retry_prompt, validate_answer
from app_workspace import (
    WORKSPACE_LABELS,
    chat_mode_for_workspace,
    label_for_workspace,
    rag_index_ready,
    should_run_audit_synthesis,
    workspace_from_label,
)
from analytical_synthesis import run_analytical_synthesis, should_run_analytical_synthesis
from audit_synthesis import run_audit_synthesis
from case_memory import enrich_project_memory
from entity_timeline import load_entities
from exhaustive_retrieval import format_audit_context, search_exhaustive
from page_index import PageLexicalIndex
from query_expansion import expand_query
from query_planner import plan_query
from proofread_ui import render_proofread_workspace
from retrieved_chunks_ui import nodes_to_serializable, render_retrieved_chunks_expander
from chat_memory import rehydrate_memory_from_messages, sync_memory_with_session
from chat_response_utils import coalesce_assistant_reply, is_empty_llm_output
from free_chat_engine import build_free_chat_engines
from display_name import DisplayNamePostprocessor
from empty_retriever import EmptyRetriever
from gpu_runtime import chat_gpu_available, is_ingest_active, release_cuda_cache
from index_bootstrap import (
    embedding_vector_size,
    ensure_qdrant_collection,
    project_index_counts,
    project_index_empty,
)
from ingest_service import release_ingest_models, run_ingest
from llm_thinking import (
    ThinkingCaptureLLM,
    clear_captured_thinking,
    get_captured_thinking,
    get_live_thinking,
)
import project_memory as project_memory_store
from rag_prompts import (
    ChatPromptMode,
    build_session_prompts,
)
from retrieval_lexical import LexicalIndex
from retrieval_pipeline import HybridRetriever
from project_store import (
    ProjectStore,
    apply_project_settings,
    file_sha256,
    project_uploads_dir,
)
from runtime_config import (
    RuntimeSettings,
    check_ollama_health,
    configure_runtime_env,
    connect_qdrant,
    embedding_device,
    llm_timeout_for_model,
    reranker_inference_device,
)

MODEL_LABELS = {
    "gemma4:26b": "gemma4:26b (default)",
    "gemma4:e4b": "gemma4:e4b (rapido)",
}


def _reranker_runtime_error(msg: str) -> bool:
    m = msg.lower()
    return "rerank" in m or "cross-encoder" in m or "sentence_transformer" in m


def _upload_signature(files) -> str:
    parts = []
    for f in files or []:
        try:
            parts.append(f"{f.name}:{len(f.getvalue())}")
        except Exception:
            parts.append(f"{f.name}:0")
    return "|".join(sorted(parts))


def _render_ingest_quality_warnings(
    per_file: list[dict], *, threshold: float
) -> None:
    for item in per_file:
        status = str(item.get("status", ""))
        quality = float(item.get("quality", 1.0) or 1.0)
        pages = int(item.get("pages", 0) or 0)
        src = str(item.get("source_file") or item.get("file") or "?")
        if status in ("empty", "empty_chunks") or pages == 0:
            st.warning(
                f"**{src}**: possivel PDF escaneado ou extracao falhou (0 paginas/chunks). "
                "Considere reprocessar com OCR (`ENABLE_OCR=true` no .env; ver OPERATIONS.md)."
            )
        elif quality < threshold:
            st.warning(
                f"**{src}**: qualidade de texto baixa ({quality:.2f} < {threshold:.2f}). "
                "Considere reprocessar com OCR."
            )


def _unload_ollama_model(model_name: str) -> tuple[bool, str]:
    model = (model_name or "").strip()
    if not model:
        return False, "modelo vazio"
    try:
        proc = subprocess.run(
            ["ollama", "stop", model],
            check=False,
            capture_output=True,
            text=True,
            timeout=12,
        )
        if proc.returncode == 0:
            return True, (proc.stdout or "ok").strip()
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        detail = stderr or stdout or f"exit={proc.returncode}"
        return False, detail
    except Exception as exc:
        return False, str(exc)


def _prewarm_ollama_model(model_name: str, host: str, keep_alive: str) -> tuple[bool, str]:
    model = (model_name or "").strip()
    if not model:
        return False, "modelo vazio"
    url = f"{host.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": "OK",
        "stream": False,
        "keep_alive": keep_alive,
        "options": {"num_predict": 1},
    }
    req = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            if resp.status >= 400:
                return False, f"http={resp.status}"
            return True, body[:120] or "ok"
    except URLError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def _thinking_stream_tick(outer_ph, state: dict, live: str | None) -> None:
    """Atualiza o texto do thinking sem recriar o expander a cada token."""
    if not live:
        return
    if state.get("body") is None:
        with outer_ph.container():
            with st.expander("Thinking do modelo", expanded=True):
                state["body"] = st.empty()
    state["body"].markdown(live)


def _thinking_finalize_collapsed(outer_ph, text: str | None) -> None:
    if not text:
        return
    outer_ph.empty()
    with outer_ph.container():
        with st.expander("Thinking do modelo", expanded=False):
            st.markdown(text)


def _stream_assistant_reply(
    token_gen,
    capture_llm: ThinkingCaptureLLM,
    thinking_outer_ph,
    text_ph,
    status_ph,
    thinking_state: dict,
) -> tuple[str, str | None]:
    """Stream na UI; thinking com expander fixo e markdown interno atualizado."""
    assistant_text = ""
    thinking_text = None
    status_cleared = False

    def clear_status_once() -> None:
        nonlocal status_cleared
        if status_ph is not None and not status_cleared:
            status_ph.empty()
            status_cleared = True

    for token in token_gen:
        live = get_live_thinking(capture_llm)
        if live:
            clear_status_once()
            _thinking_stream_tick(thinking_outer_ph, thinking_state, live)
            thinking_text = live
        piece = token if isinstance(token, str) else str(token or "")
        if piece:
            clear_status_once()
            assistant_text += piece
            text_ph.markdown(assistant_text)
        time.sleep(0)

    if status_ph is not None and not status_cleared:
        status_ph.empty()
        text_ph.markdown(assistant_text)
    final_thinking = get_captured_thinking(capture_llm) or thinking_text
    if final_thinking:
        _thinking_finalize_collapsed(thinking_outer_ph, final_thinking)
    thinking_state.clear()
    return assistant_text.strip(), final_thinking


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
    raw = getattr(candidate, "raw", None)
    if isinstance(raw, dict):
        for key in keys:
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _title_from_first_user_message(text: str, max_words: int = 8) -> str:
    words = [w for w in (text or "").replace("\n", " ").strip().split() if w]
    if not words:
        return "Nova conversa"
    snippet = " ".join(words[:max_words])
    if len(words) > max_words:
        snippet += "..."
    return snippet[:120]


def _build_assistant_export_md(
    *,
    project_name: str,
    model_name: str,
    user_prompt: str,
    assistant_md: str,
    thinking: str | None,
    telemetry: str | None,
) -> str:
    lines = [
        f"# Resposta — {project_name}",
        "",
        f"- **Modelo:** {model_name}",
        "",
        "## Pergunta",
        "",
        user_prompt.strip(),
        "",
        "## Resposta",
        "",
        assistant_md.strip(),
        "",
    ]
    if thinking:
        lines += ["## Thinking", "", thinking.strip(), ""]
    if telemetry:
        lines += ["## Telemetria", "", telemetry, ""]
    return "\n".join(lines).strip() + "\n"


def _copy_markdown_button(markdown_text: str, *, widget_key: str) -> None:
    """Um clique: botao estilizado como o restante da UI; copia UTF-8 (Clipboard + fallback)."""
    b64 = base64.b64encode(markdown_text.encode("utf-8")).decode("ascii")
    b64_lit = json.dumps(b64)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in widget_key) or "cp"
    html = f"""
<div style="font-family:system-ui,sans-serif;display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
  <button id="btn_{safe}" type="button" style="padding:0.35rem 0.75rem;cursor:pointer;border-radius:0.5rem;font:inherit;">
    Copiar Markdown
  </button>
  <span id="msg_{safe}" style="font-size:0.85rem;opacity:0.9;"></span>
</div>
<script>
  const b64 = {b64_lit};
  function b64ToUtf8(s) {{
    const bin = atob(s);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder("utf-8").decode(bytes);
  }}
  const text = b64ToUtf8(b64);
  function copyViaExec(s) {{
    const ta = document.createElement("textarea");
    ta.value = s;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, s.length);
    let ok = false;
    try {{ ok = document.execCommand("copy"); }} catch (e) {{}}
    document.body.removeChild(ta);
    return ok;
  }}
  async function copyAll() {{
    if (navigator.clipboard && window.isSecureContext) {{
      try {{ await navigator.clipboard.writeText(text); return true; }} catch (e) {{}}
    }}
    try {{
      if (window.parent && window.parent !== window && window.parent.navigator.clipboard) {{
        await window.parent.navigator.clipboard.writeText(text);
        return true;
      }}
    }} catch (e) {{}}
    return copyViaExec(text);
  }}
  const btn = document.getElementById("btn_{safe}");
  const msg = document.getElementById("msg_{safe}");
  btn.addEventListener("click", async () => {{
    const ok = await copyAll();
    msg.textContent = ok ? "Copiado." : "Falhou — use Exportar .md.";
  }});
</script>
"""
    components.html(html, height=44)


def _persist_uploaded_files(active_project, uploaded_pdfs) -> tuple[list[Path], list[dict], list[str]]:
    upload_dir = project_uploads_dir(active_project.project_id)
    existing = active_project.documents
    by_hash = {(d.get("sha256"), d.get("display_name")): d for d in existing}
    paths: list[Path] = []
    entries: list[dict] = []
    skipped: list[str] = []
    for up in uploaded_pdfs:
        suffix = Path(up.name).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            payload = up.getvalue()
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        digest = file_sha256(tmp_path)
        key = (digest, up.name)
        if key in by_hash:
            skipped.append(up.name)
            tmp_path.unlink(missing_ok=True)
            continue
        file_id = hashlib.sha1(f"{up.name}:{digest}".encode("utf-8")).hexdigest()[:16]
        stored_name = f"{file_id}_{up.name}"
        dest = upload_dir / stored_name
        if dest.exists():
            dest.unlink(missing_ok=True)
        tmp_path.replace(dest)
        size_mb = round(len(payload) / (1024 * 1024), 3)
        paths.append(dest)
        entries.append(
            {
                "file_id": file_id,
                "display_name": up.name,
                "storage_name": stored_name,
                "path": str(dest),
                "sha256": digest,
                "size_mb": size_mb,
                "status": "pending",
            }
        )
    return paths, entries, skipped


def _remove_docs_from_indexes(settings, docs: list[dict]) -> tuple[int, int]:
    source_files = [str(d.get("storage_name") or Path(str(d.get("path", ""))).name) for d in docs]
    lexical_removed = LexicalIndex(settings.lexical_db_path).delete_by_source_files(source_files)
    client, _ = connect_qdrant(settings)
    deleted_points = 0
    for source in source_files:
        points, _ = client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="source_file", match=MatchValue(value=source))]
            ),
            with_payload=False,
            with_vectors=False,
            limit=10_000,
        )
        ids = [p.id for p in points if p.id is not None]
        if ids:
            client.delete(
                collection_name=settings.qdrant_collection,
                points_selector=PointIdsList(points=ids),
            )
            deleted_points += len(ids)
    return deleted_points, lexical_removed


@st.cache_resource(show_spinner=False)
def _load_proofread_llm(
    selected_model: str,
    ollama_host: str,
    keep_alive: str,
    timeout: float,
):
    return OllamaThinkingStream(
        model=selected_model,
        request_timeout=timeout,
        keep_alive=keep_alive,
        thinking=False,
        context_window=-1,
    )


def _invalidate_conversation_memory() -> None:
    st.session_state.pop("chat_memory", None)
    st.session_state.pop("chat_memory_key", None)


def _invalidate_project_stack_cache() -> None:
    _load_project_stack.clear()


def _reset_chat_state(
    *,
    reset_messages: bool = True,
    reset_doc_selection: bool = True,
    reset_conversation_id: bool = True,
    invalidate_project_cache: bool = False,
) -> None:
    if reset_messages:
        st.session_state.messages = []
    if reset_doc_selection:
        st.session_state.selected_doc_ids = []
    if reset_conversation_id:
        st.session_state.active_conversation_id = ""
    st.session_state.last_upload_signature = ""
    _invalidate_conversation_memory()
    if invalidate_project_cache:
        _invalidate_project_stack_cache()


def _get_chat_memory(settings) -> Memory:
    cid = (st.session_state.get("active_conversation_id") or "").strip()
    mem_key = f"chat_memory_{cid or 'default'}"
    if st.session_state.get("chat_memory_key") != mem_key or "chat_memory" not in st.session_state:
        st.session_state.chat_memory = Memory.from_defaults(
            token_limit=settings.chat_memory_token_limit
        )
        st.session_state.chat_memory_key = mem_key
    return st.session_state.chat_memory


def _chat_blocked_reason() -> str | None:
    if st.session_state.ingest_running or is_ingest_active():
        return "Indexacao em andamento. O chat sera liberado ao terminar."
    if not chat_gpu_available():
        return "GPU ocupada com indexacao em outra sessao. Aguarde a conclusao."
    return None


def _cleanup_project_assets(settings, project) -> dict:
    removed = {
        "uploads_removed": 0,
        "lexical_removed": False,
        "checkpoint_removed": False,
        "qdrant_collection_removed": False,
    }
    import paths

    # Files tracked in project documents.
    for doc in list(project.documents or []):
        path_value = str(doc.get("path", "")).strip()
        if not path_value:
            continue
        p = paths.resolve_path(path_value)
        if p.exists():
            try:
                p.unlink(missing_ok=True)
                removed["uploads_removed"] += 1
            except Exception:
                pass

    project_root = paths.project_dir(project.project_id)
    if project_root.exists():
        try:
            shutil.rmtree(project_root, ignore_errors=True)
        except Exception:
            pass

    lexical_db = paths.resolve_path(project.lexical_db_path)
    if lexical_db.exists():
        lexical_db.unlink(missing_ok=True)
        removed["lexical_removed"] = True

    checkpoint_file = paths.resolve_path(project.checkpoint_path)
    if checkpoint_file.exists():
        checkpoint_file.unlink(missing_ok=True)
        removed["checkpoint_removed"] = True

    try:
        client, _ = connect_qdrant(settings)
        if client.collection_exists(project.qdrant_collection):
            client.delete_collection(project.qdrant_collection)
            removed["qdrant_collection_removed"] = True
    except Exception:
        pass
    return removed


@dataclass
class ProjectStack:
    hybrid_retriever: HybridRetriever | EmptyRetriever
    connected_host: str
    settings: RuntimeSettings
    selected_model: str
    capture_llm: ThinkingCaptureLLM
    window_expander: MetadataReplacementPostProcessor
    display_name_pp: DisplayNamePostprocessor
    use_reranker: bool
    chat_mode: ChatPromptMode


@st.cache_resource(show_spinner=False)
def _load_reranker(reranker_model_path: str, reranker_top_n: int, torch_device_settings_key: str):
    """torch_device_settings_key evita cache errado ao trocar RERANKER_DEVICE (cpu/cuda/auto)."""
    return SentenceTransformerRerank(
        model=reranker_model_path,
        top_n=reranker_top_n,
        device=reranker_inference_device(torch_device_settings_key),
    )


@st.cache_resource(show_spinner=False)
def _load_project_stack(
    selected_model: str,
    forced_profile: str | None,
    project_id: str | None,
    chat_mode: str,
    workspace: str,
) -> ProjectStack:
    settings = configure_runtime_env()
    if project_id:
        store = ProjectStore(settings.projects_registry_path)
        project = store.get_project(project_id)
        if project is not None:
            settings = apply_project_settings(settings, project)
    check_ollama_health(settings.ollama_host)

    base_llm = OllamaThinkingStream(
        model=selected_model,
        request_timeout=llm_timeout_for_model(settings, selected_model),
        keep_alive=settings.ollama_keep_alive,
        thinking=settings.ollama_thinking,
        context_window=-1,
    )
    capture_llm = ThinkingCaptureLLM(llm=base_llm)
    window_expander = MetadataReplacementPostProcessor(target_metadata_key="window")
    display_name_pp = DisplayNamePostprocessor()
    mode: ChatPromptMode = "general" if chat_mode == "general" else "rag"

    if mode == "general":
        return ProjectStack(
            hybrid_retriever=EmptyRetriever(),
            connected_host="—",
            settings=settings,
            selected_model=selected_model,
            capture_llm=capture_llm,
            window_expander=window_expander,
            display_name_pp=display_name_pp,
            use_reranker=False,
            chat_mode=mode,
        )

    query_embed_device = os.environ.get("QUERY_EMBED_DEVICE", "cpu").strip().lower()
    if query_embed_device not in ("cpu", "cuda"):
        query_embed_device = embedding_device()
    Settings.embed_model = HuggingFaceEmbedding(
        model_name=settings.embedding_model_path,
        device=query_embed_device,
    )
    Settings.chunk_size = settings.chunk_size
    Settings.chunk_overlap = settings.chunk_overlap

    client, connected_host = connect_qdrant(settings)
    embed_dim = embedding_vector_size(settings)
    ensure_qdrant_collection(client, settings, embed_dim, rebuild=False)
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=settings.qdrant_collection,
    )
    index = VectorStoreIndex.from_vector_store(vector_store)
    lexical_index = LexicalIndex(settings.lexical_db_path)
    page_index = PageLexicalIndex(settings.lexical_db_path)
    pm = enrich_project_memory(project_id, project_memory_store.load(project_id)) if project_id else ""
    hybrid_retriever = HybridRetriever(
        index=index,
        settings=settings,
        lexical_index=lexical_index,
        forced_profile=forced_profile,
        page_index=page_index,
        project_memory=pm,
        project_id=project_id,
    )
    return ProjectStack(
        hybrid_retriever=hybrid_retriever,
        connected_host=connected_host,
        settings=settings,
        selected_model=selected_model,
        capture_llm=capture_llm,
        window_expander=window_expander,
        display_name_pp=display_name_pp,
        use_reranker=settings.use_reranker,
        chat_mode=mode,
    )


def build_chat_engines(
    stack: ProjectStack,
    session_rules: str,
    memory: Memory,
    project_memory: str = "",
    *,
    workspace: str = "rag",
):
    if workspace == "free":
        return build_free_chat_engines(
            stack.capture_llm,
            memory,
            session_rules,
            project_memory=project_memory,
        )

    settings = stack.settings
    node_postprocessors: list = [stack.window_expander, stack.display_name_pp]
    if stack.use_reranker:
        reranker_top_n = max(
            settings.reranker_top_n,
            settings.retrieval_profiles["preciso"].reranker_top_n,
        )
        node_postprocessors.append(
            _load_reranker(
                settings.reranker_model_path,
                reranker_top_n,
                settings.reranker_device,
            )
        )

    condense_prompt, context_prompt, context_refine_prompt = build_session_prompts(
        session_rules,
        mode=stack.chat_mode,
        project_memory=project_memory or None,
    )
    shared_prompts = dict(
        condense_prompt=condense_prompt,
        context_prompt=context_prompt,
        context_refine_prompt=context_refine_prompt,
    )
    chat_engine = CondensePlusContextChatEngine.from_defaults(
        retriever=stack.hybrid_retriever,
        memory=memory,
        llm=stack.capture_llm,
        **shared_prompts,
        node_postprocessors=node_postprocessors,
    )
    fallback_chat_engine = CondensePlusContextChatEngine.from_defaults(
        retriever=stack.hybrid_retriever,
        memory=memory,
        llm=stack.capture_llm,
        **shared_prompts,
        node_postprocessors=[stack.window_expander, stack.display_name_pp],
    )
    return chat_engine, fallback_chat_engine


def _setup_chat_engines(
    stack: ProjectStack,
    project_id: str,
    *,
    rehydrate: bool = False,
    use_project_memory: bool = True,
    workspace: str = "rag",
):
    settings = stack.settings
    chat_memory = _get_chat_memory(settings)
    messages = st.session_state.get("messages") or []
    if rehydrate and messages:
        rehydrate_memory_from_messages(
            chat_memory,
            messages,
            settings=settings,
            llm=getattr(getattr(stack, "capture_llm", None), "llm", None),
        )
    else:
        sync_memory_with_session(
            chat_memory,
            messages,
            settings=settings,
            llm=getattr(getattr(stack, "capture_llm", None), "llm", None),
        )
    pm = ""
    if use_project_memory and project_id:
        pm = enrich_project_memory(project_id, project_memory_store.load(project_id))
    if isinstance(stack.hybrid_retriever, HybridRetriever):
        stack.hybrid_retriever.project_memory = pm
    return build_chat_engines(
        stack,
        st.session_state.project_rules_input.strip(),
        chat_memory,
        project_memory=pm,
        workspace=workspace,
    )


def _save_active_conversation(project_id: str, model_name: str) -> None:
    cid = (st.session_state.get("active_conversation_id") or "").strip()
    if not cid:
        return
    rec = conv_store.load(project_id, cid)
    if rec is None:
        rec = conv_store.create(project_id, title="Nova conversa", model_name=model_name)
        st.session_state.active_conversation_id = rec.conversation_id
    rec.messages = [dict(m) for m in st.session_state.messages]
    rec.model_name = model_name or rec.model_name
    conv_store.save(project_id, rec)


def _maybe_auto_title_conversation(project_id: str) -> None:
    msgs = st.session_state.messages
    user_msgs = [m for m in msgs if m.get("role") == "user"]
    if len(user_msgs) != 1:
        return
    cid = (st.session_state.get("active_conversation_id") or "").strip()
    if not cid:
        return
    rec = conv_store.load(project_id, cid)
    if rec is None or rec.title.strip() not in ("Nova conversa",):
        return
    new_title = _title_from_first_user_message(str(user_msgs[0].get("content", "")))
    conv_store.rename(project_id, cid, new_title)



st.set_page_config(layout="wide", page_title="PDF Extreme AI")
st.title("PDF EXTREME AI")
base_settings = configure_runtime_env()
project_store = ProjectStore(base_settings.projects_registry_path)
all_projects = project_store.list_projects()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "ingest_logs" not in st.session_state:
    st.session_state.ingest_logs = []
if "ingest_running" not in st.session_state:
    st.session_state.ingest_running = False
if "ingest_progress" not in st.session_state:
    st.session_state.ingest_progress = 0.0
if "active_project_id" not in st.session_state:
    st.session_state.active_project_id = all_projects[0].project_id if all_projects else ""
if "project_rules_input" not in st.session_state:
    st.session_state.project_rules_input = ""
if "project_rules_loaded_for" not in st.session_state:
    st.session_state.project_rules_loaded_for = ""
if "clear_project_rules_input" not in st.session_state:
    st.session_state.clear_project_rules_input = False
if "project_memory_input" not in st.session_state:
    st.session_state.project_memory_input = ""
if "project_memory_loaded_for" not in st.session_state:
    st.session_state.project_memory_loaded_for = ""
if "clear_project_memory_input" not in st.session_state:
    st.session_state.clear_project_memory_input = False
if "app_workspace" not in st.session_state:
    st.session_state.app_workspace = "rag"
if "_workspace_prev" not in st.session_state:
    st.session_state._workspace_prev = st.session_state.app_workspace
if "free_use_project_memory" not in st.session_state:
    st.session_state.free_use_project_memory = False
if "proofread_last_result" not in st.session_state:
    st.session_state.proofread_last_result = None
if "audit_mode_ui" not in st.session_state:
    st.session_state.audit_mode_ui = False
if "last_ingest_per_file" not in st.session_state:
    st.session_state.last_ingest_per_file = []
if "force_ocr_reprocess" not in st.session_state:
    st.session_state.force_ocr_reprocess = False
if "auto_ingest_enabled" not in st.session_state:
    st.session_state.auto_ingest_enabled = True
if "last_upload_signature" not in st.session_state:
    st.session_state.last_upload_signature = ""
if "selected_doc_ids" not in st.session_state:
    st.session_state.selected_doc_ids = []
if "model_switch_running" not in st.session_state:
    st.session_state.model_switch_running = False
if "model_switch_status" not in st.session_state:
    st.session_state.model_switch_status = ""
if "delete_confirm_input" not in st.session_state:
    st.session_state.delete_confirm_input = ""
if "clear_delete_confirm_input" not in st.session_state:
    st.session_state.clear_delete_confirm_input = False
if "model_selected_prev" not in st.session_state:
    st.session_state.model_selected_prev = ""
if "model_ready" not in st.session_state:
    st.session_state.model_ready = False
if "model_warm_set" not in st.session_state:
    st.session_state.model_warm_set = []
if "active_conversation_id" not in st.session_state:
    st.session_state.active_conversation_id = ""
if "gpu_phase" not in st.session_state:
    st.session_state.gpu_phase = "setup"

active_project = project_store.get_project(st.session_state.active_project_id) if st.session_state.active_project_id else None
runtime_settings = apply_project_settings(base_settings, active_project) if active_project else base_settings

left_pane, right_pane = st.columns([0.38, 0.62])
with left_pane:
    st.header("Projetos")
    project_names = {p.project_id: p.name for p in all_projects}
    project_options = list(project_names.keys())
    selected_project_id = st.selectbox(
        "Projeto ativo",
        options=project_options,
        index=project_options.index(st.session_state.active_project_id)
        if st.session_state.active_project_id in project_options
        else 0,
        format_func=lambda pid: project_names.get(pid, pid),
        disabled=not project_options,
    ) if project_options else ""

    if project_options and selected_project_id and selected_project_id != st.session_state.active_project_id:
        st.session_state.active_project_id = selected_project_id
        st.session_state.gpu_phase = "setup"
        _reset_chat_state(invalidate_project_cache=True)
        st.rerun()

    new_project_name = st.text_input("Novo projeto", placeholder="Ex.: Caso X")
    if st.button("Criar projeto"):
        if not new_project_name.strip():
            st.warning("Informe um nome de projeto.")
        else:
            created = project_store.create_project(new_project_name.strip())
            st.session_state.active_project_id = created.project_id
            st.session_state.gpu_phase = "setup"
            _reset_chat_state(invalidate_project_cache=True)
            st.rerun()

    if active_project is not None:
        with st.expander("Excluir projeto", expanded=False):
            st.caption(
                "Acao destrutiva: remove projeto, colecao Qdrant, DB lexical, checkpoint e uploads."
            )
            if st.session_state.clear_delete_confirm_input:
                st.session_state.delete_confirm_input = ""
                st.session_state.clear_delete_confirm_input = False
            st.text_input(
                f"Digite '{active_project.project_id}' para confirmar",
                key="delete_confirm_input",
            )
            can_delete = st.session_state.delete_confirm_input.strip() == active_project.project_id
            if st.button(
                "Excluir projeto e base associada",
                disabled=not can_delete,
                type="primary",
            ):
                with st.spinner("Excluindo projeto e limpando bases..."):
                    removed_project = project_store.delete_project(active_project.project_id)
                    cleanup = _cleanup_project_assets(base_settings, removed_project)
                all_after = project_store.list_projects()
                st.session_state.active_project_id = all_after[0].project_id if all_after else ""
                st.session_state.clear_delete_confirm_input = True
                st.session_state.gpu_phase = "setup"
                _reset_chat_state(invalidate_project_cache=True)
                st.success(
                    "Projeto removido com sucesso. "
                    f"uploads={cleanup['uploads_removed']} | "
                    f"lexical_db={cleanup['lexical_removed']} | "
                    f"checkpoint={cleanup['checkpoint_removed']} | "
                    f"qdrant_collection={cleanup['qdrant_collection_removed']}"
                )
                st.rerun()

    if active_project is None:
        st.info("Crie um projeto para habilitar ingestao e chat.")
    else:
        st.caption(
            f"Colecao: {active_project.qdrant_collection} | "
            f"LexicalDB: {active_project.lexical_db_path}"
        )

        st.divider()
        st.header("Base de conhecimento")
        st.caption(
            f"Limites: ate {runtime_settings.ui_ingest_max_files} PDF(s), "
            f"{runtime_settings.ui_ingest_max_file_mb} MB por arquivo."
        )
        st.toggle(
            "Auto-ingest ao subir arquivo(s)",
            key="auto_ingest_enabled",
            value=True,
        )
        uploaded_pdfs = st.file_uploader(
            "Arraste PDFs para ingestao",
            type=["pdf"],
            accept_multiple_files=True,
        )
        ingest_rebuild = st.checkbox("Rebuild da base (destrutivo)", value=False)
        if ingest_rebuild:
            st.warning("Rebuild afeta somente o projeto ativo.")

        def _append_ingest_log(event: dict) -> None:
            stage = str(event.get("stage", ""))
            msg = str(event.get("message", stage))
            current = int(event.get("current", 0) or 0)
            total = int(event.get("total", 0) or 0)
            if total > 0:
                st.session_state.ingest_progress = min(1.0, current / total)
            st.session_state.ingest_logs.append(msg)

        def _run_ingest_for_paths(paths: list[Path], entries: list[dict], rebuild: bool, reprocess_all: bool) -> None:
            st.session_state.ingest_running = True
            st.session_state.gpu_phase = "ingesting"
            st.session_state.ingest_logs = []
            st.session_state.ingest_progress = 0.0
            ollama_model = (
                st.session_state.get("model_selected_prev") or runtime_settings.llm_default_model
            )
            try:
                if runtime_settings.ingest_pause_ollama and ollama_model:
                    _unload_ollama_model(ollama_model)
                    time.sleep(0.2)
                prev_ocr = os.environ.get("ENABLE_OCR", "")
                if st.session_state.get("force_ocr_reprocess"):
                    os.environ["ENABLE_OCR"] = "true"
                try:
                    result = run_ingest(
                        settings=runtime_settings,
                        input_files=paths,
                        rebuild=rebuild,
                        reprocess_all=reprocess_all,
                        update_checkpoint=True,
                        progress_callback=_append_ingest_log,
                        project_id=active_project.project_id,
                    )
                finally:
                    if st.session_state.get("force_ocr_reprocess"):
                        if prev_ocr:
                            os.environ["ENABLE_OCR"] = prev_ocr
                        else:
                            os.environ.pop("ENABLE_OCR", None)
                st.session_state.last_ingest_per_file = list(result.per_file)
                by_source = {item.get("source_file"): item for item in result.per_file}
                for entry in entries:
                    source = entry.get("storage_name", "")
                    if source in by_source:
                        info = by_source[source]
                        entry["status"] = info.get("status", "indexed")
                        entry["pages"] = int(info.get("pages", 0) or 0)
                        entry["chunks"] = int(info.get("chunks", 0) or 0)
                    else:
                        entry["status"] = "indexed"
                    entry["last_ingested_at"] = Path(".").stat().st_mtime
                project_store.add_documents(active_project.project_id, entries)
                st.session_state.ingest_progress = 1.0
                release_ingest_models()
                _invalidate_project_stack_cache()
                release_cuda_cache()
                if runtime_settings.ingest_pause_ollama and ollama_model:
                    st.session_state.model_switch_status = "Base indexada — preparando assistente..."
                    _prewarm_ollama_model(
                        ollama_model,
                        runtime_settings.ollama_host,
                        runtime_settings.ollama_keep_alive,
                    )
                st.session_state.gpu_phase = "chat_ready"
                st.session_state.model_ready = True
                st.session_state.model_switch_status = "Pronto para conversar"
                st.success(
                    f"Ingestao concluida: arquivos={result.files_processed}/{result.files_total} "
                    f"| paginas={result.total_pages} | chunks={result.total_chunks} "
                    f"| tempo={result.elapsed_s:.1f}s"
                )
                if result.errors:
                    st.error("Alguns arquivos falharam na ingestao.")
                    for err in result.errors:
                        st.caption(err)
                if result.per_file:
                    _render_ingest_quality_warnings(
                        result.per_file,
                        threshold=runtime_settings.ingest_quality_warn_threshold,
                    )
            except Exception as exc:
                st.session_state.gpu_phase = "setup"
                st.error(f"Falha na ingestao: {exc}")
            finally:
                st.session_state.ingest_running = False

        upload_sig = _upload_signature(uploaded_pdfs)
        should_auto = (
            bool(uploaded_pdfs)
            and st.session_state.auto_ingest_enabled
            and not st.session_state.ingest_running
            and not is_ingest_active()
            and upload_sig
            and upload_sig != st.session_state.last_upload_signature
        )
        if should_auto:
            if len(uploaded_pdfs) > runtime_settings.ui_ingest_max_files:
                st.error(
                    f"Limite excedido: maximo de {runtime_settings.ui_ingest_max_files} arquivos por lote."
                )
            else:
                try:
                    paths, entries, skipped = _persist_uploaded_files(active_project, uploaded_pdfs)
                    if skipped:
                        st.info(f"Ignorados (duplicados): {', '.join(skipped)}")
                    if paths:
                        _run_ingest_for_paths(paths, entries, rebuild=ingest_rebuild, reprocess_all=True)
                    st.session_state.last_upload_signature = upload_sig
                except Exception as exc:
                    st.error(f"Falha no auto-ingest: {exc}")

        if not st.session_state.auto_ingest_enabled:
            if st.button(
                "Ingerir arquivos enviados",
                disabled=st.session_state.ingest_running or is_ingest_active(),
            ):
                if not uploaded_pdfs:
                    st.warning("Envie ao menos um PDF para iniciar ingestao.")
                else:
                    try:
                        paths, entries, skipped = _persist_uploaded_files(active_project, uploaded_pdfs)
                        if skipped:
                            st.info(f"Ignorados (duplicados): {', '.join(skipped)}")
                        if not paths:
                            st.warning("Nenhum arquivo novo para ingerir.")
                        else:
                            _run_ingest_for_paths(paths, entries, rebuild=ingest_rebuild, reprocess_all=True)
                            st.session_state.last_upload_signature = upload_sig
                    except Exception as exc:
                        st.error(f"Falha na ingestao: {exc}")

        st.progress(float(st.session_state.ingest_progress))
        with st.expander("Logs de ingestao", expanded=False):
            if st.session_state.ingest_logs:
                st.code("\n".join(st.session_state.ingest_logs[-80:]), language="text")
            else:
                st.caption("Sem logs nesta sessao.")

        if st.session_state.last_ingest_per_file:
            with st.expander("Alertas da ultima ingestao", expanded=True):
                _render_ingest_quality_warnings(
                    st.session_state.last_ingest_per_file,
                    threshold=runtime_settings.ingest_quality_warn_threshold,
                )

        with st.expander("Documentos do projeto", expanded=False):
            st.checkbox(
                "Forcar OCR no proximo reprocessamento",
                key="force_ocr_reprocess",
                help="Define ENABLE_OCR=true apenas na proxima ingest/reprocess (requer Tesseract).",
            )
            docs = list(active_project.documents)
            if docs:
                select_options: list[str] = []
                label_map: dict[str, str] = {}
                for i, d in enumerate(docs):
                    fid = str(d.get("file_id", "")).strip() or f"legacy_{i}"
                    select_options.append(fid)
                    label_map[fid] = (
                        f"{d.get('display_name', d.get('name', 'arquivo'))} | "
                        f"status={d.get('status', 'ok')} | pgs={d.get('pages', 0)} | chunks={d.get('chunks', 0)}"
                    )
                st.multiselect(
                    "Selecionar arquivos",
                    options=select_options,
                    default=st.session_state.selected_doc_ids,
                    format_func=lambda fid: label_map.get(fid, fid),
                    key="selected_doc_ids",
                )

                action_cols = st.columns(2)
                with action_cols[0]:
                    if st.button(
                        "Reprocessar selecionados",
                        disabled=st.session_state.ingest_running or is_ingest_active(),
                    ):
                        selected = []
                        for i, d in enumerate(docs):
                            fid = str(d.get("file_id", "")).strip() or f"legacy_{i}"
                            if fid in st.session_state.selected_doc_ids:
                                selected.append(d)
                        paths = [Path(str(d.get("path", ""))) for d in selected if str(d.get("path", ""))]
                        if not paths:
                            st.warning("Selecione ao menos um arquivo com path valido.")
                        else:
                            _run_ingest_for_paths(paths, selected, rebuild=False, reprocess_all=True)
                with action_cols[1]:
                    if st.button(
                        "Remover selecionados",
                        disabled=st.session_state.ingest_running or is_ingest_active(),
                    ):
                        selected = []
                        remove_ids: list[str] = []
                        for i, d in enumerate(docs):
                            fid = str(d.get("file_id", "")).strip() or f"legacy_{i}"
                            if fid in st.session_state.selected_doc_ids:
                                selected.append(d)
                                if str(d.get("file_id", "")).strip():
                                    remove_ids.append(str(d.get("file_id", "")))
                        if not selected:
                            st.warning("Selecione arquivos para remover.")
                        else:
                            removed_vec, removed_lex = _remove_docs_from_indexes(runtime_settings, selected)
                            for doc in selected:
                                p = Path(str(doc.get("path", "")))
                                try:
                                    p.unlink(missing_ok=True)
                                except Exception:
                                    pass
                            project_store.remove_documents(active_project.project_id, remove_ids)
                            st.success(
                                f"Remocao concluida. vetorial={removed_vec} | lexical={removed_lex} | arquivos={len(selected)}"
                            )
                            st.rerun()

                st.caption("Acoes por arquivo")
                for idx, doc in enumerate(docs[-30:]):
                    fid = str(doc.get("file_id", "")) or f"legacy_{idx}"
                    name = doc.get("display_name", doc.get("name", "arquivo"))
                    st.markdown(
                        f"- `{name}` | status={doc.get('status', 'ok')} | "
                        f"pgs={doc.get('pages', 0)} | chunks={doc.get('chunks', 0)}"
                    )
                    row = st.columns(2)
                    with row[0]:
                        if st.button(
                            "Reprocessar",
                            key=f"reproc_{fid}_{idx}",
                            disabled=st.session_state.ingest_running or is_ingest_active(),
                        ):
                            path = Path(str(doc.get("path", "")))
                            if not path.exists():
                                st.error(f"Arquivo fisico nao encontrado: {path}")
                            else:
                                _run_ingest_for_paths([path], [doc], rebuild=False, reprocess_all=True)
                    with row[1]:
                        if st.button(
                            "Remover",
                            key=f"rm_{fid}_{idx}",
                            disabled=st.session_state.ingest_running or is_ingest_active(),
                        ):
                            _remove_docs_from_indexes(runtime_settings, [doc])
                            p = Path(str(doc.get("path", "")))
                            try:
                                p.unlink(missing_ok=True)
                            except Exception:
                                pass
                            project_store.remove_documents(active_project.project_id, [fid])
                            st.rerun()
            else:
                st.caption("Nenhum documento registrado.")

        st.divider()
        st.subheader("Instrucoes globais do projeto")
        if st.session_state.project_rules_loaded_for != active_project.project_id:
            st.session_state.project_rules_input = active_project.global_rules
            st.session_state.project_rules_loaded_for = active_project.project_id
        if st.session_state.clear_project_rules_input:
            st.session_state.project_rules_input = ""
            st.session_state.clear_project_rules_input = False
        st.text_area(
            "Regras extras para respostas (persistidas neste projeto)",
            key="project_rules_input",
            max_chars=4000,
            height=180,
            help="Valem apenas para o projeto ativo.",
        )
        rules_cols = st.columns(2)
        with rules_cols[0]:
            if st.button("Salvar regras do projeto"):
                project_store.set_global_rules(
                    active_project.project_id,
                    st.session_state.project_rules_input.strip(),
                )
                st.success("Regras salvas para este projeto.")
        with rules_cols[1]:
            if st.button("Limpar regras do projeto"):
                project_store.set_global_rules(active_project.project_id, "")
                st.session_state.clear_project_rules_input = True
                st.success("Regras removidas.")

        st.subheader("Memoria do caso")
        if st.session_state.project_memory_loaded_for != active_project.project_id:
            st.session_state.project_memory_input = project_memory_store.load(
                active_project.project_id
            )
            st.session_state.project_memory_loaded_for = active_project.project_id
        if st.session_state.clear_project_memory_input:
            st.session_state.project_memory_input = ""
            st.session_state.clear_project_memory_input = False
        st.text_area(
            "Contexto narrativo do projeto (decisoes, partes, teses)",
            key="project_memory_input",
            max_chars=4000,
            height=160,
            help="Incluido nos prompts. Documentos indexados prevalecem em conflito factual.",
        )
        mem_cols = st.columns(2)
        with mem_cols[0]:
            if st.button("Salvar memoria do caso"):
                project_memory_store.save(
                    active_project.project_id,
                    st.session_state.project_memory_input.strip(),
                )
                st.success("Memoria do caso salva.")
        with mem_cols[1]:
            if st.button("Limpar memoria do caso"):
                project_memory_store.save(active_project.project_id, "")
                st.session_state.clear_project_memory_input = True
                st.success("Memoria do caso removida.")

        entities = load_entities(active_project.project_id)
        with st.expander("Timeline / entidades (NER leve)", expanded=False):
            if entities:
                for ent in entities[-30:]:
                    st.caption(
                        f"{ent.get('kind', '?')}: {ent.get('value', '')} "
                        f"— {ent.get('source_file', '')} pag. {ent.get('page', 0)}"
                    )
            else:
                st.caption("Sem entidades extraidas ainda. Reingira PDFs para popular.")

with right_pane:
    selected_model = st.selectbox(
        "Modelo de geracao",
        options=runtime_settings.llm_models,
        index=(
            runtime_settings.llm_models.index(runtime_settings.llm_default_model)
            if runtime_settings.llm_default_model in runtime_settings.llm_models
            else 0
        ),
        format_func=lambda model: MODEL_LABELS.get(model, model),
        help="Troque de modelo conforme necessidade. Modelos maiores podem demorar mais.",
        disabled=(
            st.session_state.ingest_running
            or st.session_state.model_switch_running
            or is_ingest_active()
        ),
    )
    ws_options = list(WORKSPACE_LABELS.values())
    ws_default_label = label_for_workspace(st.session_state.app_workspace)
    if ws_default_label not in ws_options:
        ws_default_label = ws_options[0]
    ws_label = st.segmented_control(
        "Modo de uso",
        options=ws_options,
        default=ws_default_label,
        key="app_workspace_label",
        disabled=(
            st.session_state.ingest_running
            or st.session_state.model_switch_running
            or is_ingest_active()
        ),
    )
    new_ws = workspace_from_label(str(ws_label or ws_default_label))
    if new_ws != st.session_state.get("_workspace_prev"):
        st.session_state.messages = []
        st.session_state.active_conversation_id = ""
        _invalidate_conversation_memory()
        _invalidate_project_stack_cache()
        st.session_state.proofread_last_result = None
    st.session_state.app_workspace = new_ws
    st.session_state._workspace_prev = new_ws

    forced_profile = None
    if new_ws == "rag":
        with st.expander("Opcao avancada de estrategia (RAG)", expanded=False):
            strategy_mode = st.selectbox(
                "Modo de estrategia",
                options=["automatico", "rapido", "preciso", "pericial"],
                index=0,
                help="Automatico adapta por prompt. Use fixo para auditoria.",
                disabled=(
                    st.session_state.ingest_running
                    or st.session_state.model_switch_running
                    or is_ingest_active()
                ),
            )
        forced_profile = None if strategy_mode == "automatico" else strategy_mode
        st.checkbox(
            "Modo auditoria (varredura lexical)",
            key="audit_mode_ui",
            help=(
                "So para buscas literais/exaustivas de termos (nao use em resumos). "
                "Com muitas paginas, sintese em lotes com barra de progresso."
            ),
        )
    elif new_ws == "free":
        st.checkbox(
            "Incluir memoria do caso no chat livre",
            key="free_use_project_memory",
            help="Desligado por padrao: conversa sem contexto dos autos.",
        )
    else:
        st.caption("Corretor: cole texto e corrija — sem RAG e sem historico de conversas.")

    st.caption(
        "Dica: aguarde a consulta atual terminar antes de trocar de modelo para evitar disputa de VRAM."
    )
    chat_block = _chat_blocked_reason()
    if chat_block:
        st.info(chat_block)
    elif st.session_state.ingest_running:
        st.info("Processando ingestao da base de conhecimento...")
    if st.session_state.model_switch_status:
        st.info(st.session_state.model_switch_status)
    if not st.session_state.model_ready and not st.session_state.model_switch_running:
        st.session_state.model_switch_status = "Preparando modelo na GPU..."

    previous_model = st.session_state.get("model_selected_prev")
    if previous_model and previous_model != selected_model:
        st.session_state.model_switch_running = True
        st.session_state.model_ready = False
        with st.spinner("Trocando modelo..."):
            unloaded, unload_detail = True, "omitido"
            if base_settings.ollama_unload_on_switch:
                st.session_state.model_switch_status = f"Trocando modelo: descarregando {previous_model}..."
                unloaded, unload_detail = _unload_ollama_model(previous_model)
                time.sleep(0.2)
            else:
                st.session_state.model_switch_status = "Trocando modelo (sem unload forcado na VRAM)..."
                time.sleep(0.05)
            st.session_state.model_switch_status = f"Trocando modelo: pre-carregando {selected_model}..."
            warmed, warm_detail = _prewarm_ollama_model(
                selected_model,
                runtime_settings.ollama_host,
                runtime_settings.ollama_keep_alive,
            )
            _invalidate_project_stack_cache()
            release_cuda_cache()
        if base_settings.ollama_unload_on_switch and not unloaded:
            st.caption(f"Aviso unload Ollama ({previous_model}): {unload_detail}")
        if not warmed:
            st.caption(f"Aviso preload Ollama ({selected_model}): {warm_detail}")
        else:
            known_warm = set(st.session_state.model_warm_set)
            known_warm.add(selected_model)
            st.session_state.model_warm_set = sorted(known_warm)
        st.session_state.model_switch_status = f"Modelo ativo atualizado para: {selected_model}"
        st.session_state.model_switch_running = False
        st.session_state.model_ready = True

    st.session_state.model_selected_prev = selected_model

    if not st.session_state.model_ready and not st.session_state.model_switch_running:
        st.session_state.model_switch_status = "Preparando modelo default na GPU..."
        with st.spinner("Preparando modelo default na GPU..."):
            warmed, warm_detail = _prewarm_ollama_model(
                selected_model,
                runtime_settings.ollama_host,
                runtime_settings.ollama_keep_alive,
            )
        if not warmed:
            st.warning(f"Prewarm do modelo falhou, seguindo mesmo assim: {warm_detail}")
        else:
            known_warm = set(st.session_state.model_warm_set)
            known_warm.add(selected_model)
            st.session_state.model_warm_set = sorted(known_warm)
        st.session_state.model_ready = True
        st.session_state.gpu_phase = "chat_ready"
        st.session_state.model_switch_status = "Pronto para conversar"

    if active_project is None:
        st.info("Crie e selecione um projeto no painel esquerdo para habilitar o chat.")
        st.stop()

    if chat_block:
        st.stop()

    workspace = st.session_state.app_workspace

    if workspace == "proofread":
        st.session_state.model_switch_status = "Modo corretor — pronto"
        proof_llm = _load_proofread_llm(
            selected_model,
            runtime_settings.ollama_host,
            runtime_settings.ollama_keep_alive,
            llm_timeout_for_model(runtime_settings, selected_model),
        )
        st.caption(
            f"Projeto: {active_project.name} | Modo: Corretor ortografico | "
            f"Modelo: {selected_model}"
        )
        render_proofread_workspace(proof_llm, max_chars=12000)
        st.stop()

    try:
        st.session_state.model_switch_status = "Conectando servicos..."
        chat_mode = chat_mode_for_workspace(workspace)
        if workspace == "rag" and not rag_index_ready(runtime_settings):
            st.warning(
                "Modo **Autos (RAG)** requer documentos indexados. "
                "Faca upload e ingestao no painel esquerdo, ou use **Chat livre**."
            )
            st.stop()
        stack = _load_project_stack(
            selected_model,
            forced_profile,
            active_project.project_id,
            chat_mode,
            workspace,
        )
        Settings.llm = stack.capture_llm
        runtime_settings = stack.settings
        active_model = stack.selected_model
        connected_host = stack.connected_host
        hybrid_retriever = stack.hybrid_retriever
        use_pm = workspace == "rag" or st.session_state.get("free_use_project_memory")
        chat_engine, fallback_chat_engine = _setup_chat_engines(
            stack,
            active_project.project_id,
            use_project_memory=use_pm,
            workspace=workspace,
        )
        mode_label = (
            "Chat livre (sem RAG)"
            if workspace == "free"
            else "Autos / RAG (documentos indexados)"
        )
        st.caption(
            f"Projeto ativo: {active_project.name} | "
            f"Modo: {mode_label} | "
            f"Qdrant: {connected_host}:{runtime_settings.qdrant_port} | "
            f"Collection: {runtime_settings.qdrant_collection} | "
            f"LexicalDB: {runtime_settings.lexical_db_path} | "
            f"Modelo ativo: {active_model}"
        )
        st.session_state.model_switch_status = "Pronto para conversar"
        pending_cid = st.session_state.pop("_pending_open_conversation_id", None)
        if pending_cid:
            rec_open = conv_store.load(active_project.project_id, pending_cid)
            if rec_open is not None:
                st.session_state.active_conversation_id = pending_cid
                st.session_state.messages = [dict(m) for m in rec_open.messages]
                _invalidate_conversation_memory()
                chat_engine, fallback_chat_engine = _setup_chat_engines(
                    stack,
                    active_project.project_id,
                    rehydrate=True,
                    workspace=workspace,
                )
        cid0 = (st.session_state.get("active_conversation_id") or "").strip()
        if not cid0 or conv_store.load(active_project.project_id, cid0) is None:
            blank = conv_store.create(
                active_project.project_id,
                title="Nova conversa",
                model_name=str(active_model),
            )
            st.session_state.active_conversation_id = blank.conversation_id
            st.session_state.messages = []
        lexical_nodes, vector_points = project_index_counts(runtime_settings)
        if workspace == "free":
            st.info(
                "Chat livre: sem busca nos PDFs. Regras do projeto aplicam-se; "
                "memoria do caso so se o checkbox estiver ligado. "
                "Thinking do modelo: ativo se OLLAMA_THINKING=true."
            )
        elif lexical_nodes == 0 or vector_points == 0:
            st.warning(
                "Base do projeto parece incompleta (ingest parcial). "
                f"lexical_nodes={lexical_nodes}, vector_points={vector_points}. "
                "Confirme o projeto ativo ou rode ingestao novamente."
            )
    except Exception as exc:
        detail = str(exc).strip() or f"{type(exc).__name__}"
        st.error(f"Falha ao conectar o chat: {detail}")
        st.exception(exc)
        st.stop()

    st.subheader("Conversas deste projeto")
    conv_list = conv_store.list_conversations(active_project.project_id)
    conv_ids = [c.conversation_id for c in conv_list]
    conv_labels = {c.conversation_id: f"{c.title} — {c.updated_at[:19]}" for c in conv_list}
    pick_cols = st.columns([2.2, 1, 1, 1])
    with pick_cols[0]:
        pick = st.selectbox(
            "Historico salvo",
            options=[""] + conv_ids,
            index=0,
            format_func=lambda x: "(selecione)" if not x else conv_labels.get(x, x),
            key="conversation_pick_select",
        )
    with pick_cols[1]:
        if st.button("Abrir", disabled=not pick):
            st.session_state._pending_open_conversation_id = pick
            _invalidate_conversation_memory()
            st.rerun()
    with pick_cols[2]:
        if st.button("Nova conversa", help="Nova conversa vazia (salva no projeto)."):
            nrec = conv_store.create(
                active_project.project_id,
                title="Nova conversa",
                model_name=str(active_model),
            )
            st.session_state.active_conversation_id = nrec.conversation_id
            st.session_state.messages = []
            _invalidate_conversation_memory()
            chat_engine, fallback_chat_engine = _setup_chat_engines(
                stack,
                active_project.project_id,
                workspace=workspace,
            )
            chat_engine.reset()
            fallback_chat_engine.reset()
            st.rerun()
    with pick_cols[3]:
        if st.button("Excluir", disabled=not pick):
            if pick and conv_store.delete(active_project.project_id, pick):
                if st.session_state.get("active_conversation_id") == pick:
                    st.session_state.active_conversation_id = ""
                    st.session_state.messages = []
                    _invalidate_conversation_memory()
                    chat_engine, fallback_chat_engine = _setup_chat_engines(
                        stack,
                        active_project.project_id,
                        workspace=workspace,
                    )
                    chat_engine.reset()
                    fallback_chat_engine.reset()
                st.rerun()
    rename_cols = st.columns([3, 1])
    with rename_cols[0]:
        new_conv_title = st.text_input(
            "Renomear conversa ativa",
            value="",
            placeholder="Novo titulo",
            key="conversation_rename_input",
        )
    with rename_cols[1]:
        if st.button("Salvar titulo"):
            cid_r = (st.session_state.get("active_conversation_id") or "").strip()
            if cid_r and new_conv_title.strip():
                conv_store.rename(active_project.project_id, cid_r, new_conv_title.strip())
                st.rerun()

    chat_placeholder = (
        "Pergunte sobre os documentos indexados"
        if workspace == "rag"
        else "Conversa livre com o modelo (sem RAG)"
    )

    prompt = st.session_state.pop("_pdf_extreme_pending_prompt", None)

    last_user_for_export = ""
    for idx_msg, message in enumerate(st.session_state.messages):
        if message.get("role") == "user":
            last_user_for_export = str(message.get("content", ""))
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            thinking = message.get("thinking")
            if thinking:
                with st.expander("Thinking do modelo", expanded=False):
                    st.markdown(thinking)
            telemetry = message.get("telemetry")
            if telemetry:
                st.caption(telemetry)
            if message.get("role") == "assistant":
                render_retrieved_chunks_expander(
                    message.get("retrieved_chunks"),
                    key_suffix=f"hist_{idx_msg}",
                )
                md_export = _build_assistant_export_md(
                    project_name=active_project.name,
                    model_name=str(active_model),
                    user_prompt=last_user_for_export,
                    assistant_md=str(message.get("content", "")),
                    thinking=message.get("thinking"),
                    telemetry=message.get("telemetry"),
                )
                ex_cols = st.columns([1, 1, 4])
                with ex_cols[0]:
                    st.download_button(
                        label="Exportar .md",
                        data=md_export,
                        file_name=f"resposta_{(st.session_state.get('active_conversation_id') or 'conv')[:8]}_{idx_msg}.md",
                        mime="text/markdown",
                        key=f"dl_md_{idx_msg}",
                    )
                with ex_cols[1]:
                    _copy_markdown_button(md_export, widget_key=f"cp_md_{idx_msg}")

    if not prompt:
        _chat_ui_disabled = (
            bool(chat_block)
            or st.session_state.ingest_running
            or st.session_state.model_switch_running
            or not st.session_state.model_ready
        )
        st.caption("Nova pergunta — **Enter** envia; **Shift+Enter** nova linha.")
        submitted_ask = st.chat_input(
            chat_placeholder,
            disabled=_chat_ui_disabled,
            key="pdf_extreme_chat_input",
        )
        if submitted_ask and str(submitted_ask).strip():
            st.session_state["_pdf_extreme_pending_prompt"] = str(submitted_ask).strip()
            st.rerun()

    if prompt:
        effective_prompt = prompt
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            thinking_ph = st.empty()
            text_ph = st.empty()
            status_ph = st.empty()
            assistant_text = ""
            thinking_text = None
            used_fallback = False
            telemetry = None
            retrieved_chunks: list[dict] = []
            clear_captured_thinking(stack.capture_llm)
            status_ph.caption("Recuperando contexto e preparando resposta...")
            use_audit_synthesis = False
            use_analytical_synthesis = False
            if workspace == "rag" and isinstance(hybrid_retriever, HybridRetriever):
                plan_pre = plan_query(
                    effective_prompt, runtime_settings, forced_profile=forced_profile
                )
                run_audit = should_run_audit_synthesis(
                    effective_prompt,
                    runtime_settings,
                    forced_profile=forced_profile,
                    audit_mode_ui=bool(st.session_state.get("audit_mode_ui")),
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
                        prog = st.progress(0.0, text="Modo auditoria: sintese em lotes...")
                        batch_total = min(
                            8,
                            max(
                                1,
                                (
                                    len(audit_pages)
                                    + runtime_settings.audit_pages_per_batch
                                    - 1
                                )
                                // runtime_settings.audit_pages_per_batch,
                            ),
                        )

                        def _audit_progress(i: int, total: int, phase: str) -> None:
                            if phase == "consolidacao":
                                prog.progress(0.95, text="Consolidando resposta final...")
                            else:
                                prog.progress(
                                    min(0.9, i / max(1, total)),
                                    text=f"Modo auditoria: lote {i}/{total} ({len(audit_pages)} paginas)...",
                                )

                        assistant_text = run_audit_synthesis(
                            stack.capture_llm.llm,
                            effective_prompt,
                            audit_pages,
                            pages_per_batch=runtime_settings.audit_pages_per_batch,
                            progress_callback=_audit_progress,
                        )
                        prog.progress(1.0, text="Concluido.")
                        text_ph.markdown(assistant_text)
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
                        status_ph.caption(
                            f"Modo analitico: {len(fused_nodes)} trechos, sintese em lotes..."
                        )
                        assistant_text = run_analytical_synthesis(
                            stack.capture_llm.llm,
                            effective_prompt,
                            fused_nodes,
                            chunks_per_batch=runtime_settings.analytical_chunks_per_batch,
                            max_batches=runtime_settings.analytical_max_batches,
                        )
                        text_ph.markdown(assistant_text)
                        retrieved_chunks = nodes_to_serializable(fused_nodes)
            try:
                if not use_audit_synthesis and not use_analytical_synthesis:
                    stream_resp = chat_engine.stream_chat(effective_prompt)
                    gen = getattr(stream_resp, "response_gen", None)
                    if gen is not None:
                        thinking_state: dict = {}
                        assistant_text, thinking_text = _stream_assistant_reply(
                            gen,
                            stack.capture_llm,
                            thinking_ph,
                            text_ph,
                            status_ph,
                            thinking_state,
                        )
                        assistant_text = coalesce_assistant_reply(
                            assistant_text,
                            stream_resp,
                            chat_engine,
                        )
                        if is_empty_llm_output(assistant_text):
                            fb = chat_engine.chat(effective_prompt)
                            assistant_text = coalesce_assistant_reply(
                                str(getattr(fb, "response", fb) or ""),
                                fb,
                                chat_engine,
                                wait_history=False,
                            )
                        if assistant_text:
                            text_ph.markdown(assistant_text)
                    else:
                        status_ph.empty()
                        assistant_text = coalesce_assistant_reply(
                            getattr(stream_resp, "response", "") or "",
                            stream_resp,
                            chat_engine,
                        )
                        text_ph.markdown(assistant_text)
                        thinking_text = get_captured_thinking(
                            stack.capture_llm
                        ) or _extract_thinking(stream_resp)
                        if thinking_text:
                            _thinking_finalize_collapsed(thinking_ph, thinking_text)
                    thinking_text = (
                        thinking_text
                        or get_captured_thinking(stack.capture_llm)
                        or _extract_thinking(stream_resp)
                    )
                    if is_empty_llm_output(assistant_text):
                        fb = chat_engine.chat(effective_prompt)
                        assistant_text = coalesce_assistant_reply(
                            str(getattr(fb, "response", fb) or ""),
                            fb,
                            chat_engine,
                            wait_history=False,
                        )
                        if assistant_text:
                            text_ph.markdown(assistant_text)
                else:
                    status_ph.empty()
            except Exception as exc:  # pragma: no cover
                status_ph.empty()
                msg = str(exc).lower()
                if _reranker_runtime_error(msg):
                    st.warning("Reranker falhou nesta mensagem. Respondendo sem reranker.")
                    used_fallback = True
                    try:
                        clear_captured_thinking(stack.capture_llm)
                        stream_fb = fallback_chat_engine.stream_chat(prompt)
                        gen_fb = getattr(stream_fb, "response_gen", None)
                        if gen_fb is not None:
                            fb_state: dict = {}
                            assistant_text, thinking_text = _stream_assistant_reply(
                                gen_fb,
                                stack.capture_llm,
                                thinking_ph,
                                text_ph,
                                status_ph,
                                fb_state,
                            )
                            if not assistant_text:
                                assistant_text = (
                                    getattr(stream_fb, "response", None)
                                    or getattr(stream_fb, "unformatted_response", None)
                                    or ""
                                )
                                if assistant_text:
                                    text_ph.markdown(assistant_text)
                        else:
                            status_ph.empty()
                            assistant_text = getattr(stream_fb, "response", "") or ""
                            text_ph.markdown(assistant_text)
                            thinking_text = get_captured_thinking(
                                stack.capture_llm
                            ) or _extract_thinking(stream_fb)
                            if thinking_text:
                                _thinking_finalize_collapsed(thinking_ph, thinking_text)
                        thinking_text = (
                            thinking_text
                            or get_captured_thinking(stack.capture_llm)
                            or _extract_thinking(stream_fb)
                        )
                    except Exception as exc_fb:
                        st.error(f"Falha tambem no fallback: {exc_fb}")
                        assistant_text = ""
                elif "timeout" in msg:
                    st.error("Timeout ao consultar o modelo. Tente modelo mais leve.")
                elif "cuda" in msg and "out of memory" in msg:
                    st.error("Memoria de GPU insuficiente para este modelo.")
                else:
                    st.error(f"Falha na consulta: {exc}")

            diagnostics = hybrid_retriever.last_diagnostics
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
            validation = validate_answer(assistant_text, diagnostics, validation_level)
            if validation.should_retry and assistant_text:
                retry_prompt = build_retry_prompt(prompt, validation)
                clear_captured_thinking(stack.capture_llm)
                retry_resp = fallback_chat_engine.chat(retry_prompt)
                assistant_text = str(getattr(retry_resp, "response", retry_resp))
                text_ph.markdown(assistant_text)
                thinking_text = get_captured_thinking(
                    stack.capture_llm
                ) or _extract_thinking(retry_resp)
                if thinking_text:
                    _thinking_finalize_collapsed(thinking_ph, thinking_text)
                used_fallback = True

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
                if diagnostics.requested_page is not None:
                    telemetry += f" | page={diagnostics.requested_page}"
                if diagnostics.requested_page_range is not None:
                    telemetry += f" | range={diagnostics.requested_page_range[0]}-{diagnostics.requested_page_range[1]}"
                if diagnostics.requested_source_hint:
                    telemetry += f" | source~={diagnostics.requested_source_hint}"
                if diagnostics.requested_section:
                    telemetry += f" | section={diagnostics.requested_section}"
                if diagnostics.exhaustive_page_groups:
                    telemetry += f" | audit_pages={diagnostics.exhaustive_page_groups}"
            if telemetry and used_fallback:
                telemetry += " | fallback=on"
            if telemetry and validation.issues:
                telemetry += " | validacao: " + "; ".join(validation.issues)
            if telemetry:
                st.caption(telemetry)
            if (
                workspace == "rag"
                and diagnostics
                and diagnostics.fused_count < 5
            ):
                st.caption(
                    "Poucos trechos recuperados (fused < 5). Considere perfil **pericial** "
                    "ou subir `PROFILE_PRECISO_SEMANTIC_TOP_K` / `PROFILE_PRECISO_RERANKER_TOP_N` "
                    "no `.env` (ver OPERATIONS.md §4.3.2)."
                )
            if workspace == "rag" and isinstance(hybrid_retriever, HybridRetriever):
                retrieved_chunks = nodes_to_serializable(
                    hybrid_retriever.last_retrieved_nodes
                )
                render_retrieved_chunks_expander(
                    retrieved_chunks, key_suffix=f"live_{len(st.session_state.messages)}"
                )

            if assistant_text:
                live_idx = len(st.session_state.messages)
                md_export_live = _build_assistant_export_md(
                    project_name=active_project.name,
                    model_name=str(active_model),
                    user_prompt=prompt,
                    assistant_md=assistant_text,
                    thinking=thinking_text,
                    telemetry=telemetry,
                )
                ex_cols_live = st.columns([1, 1, 4])
                with ex_cols_live[0]:
                    st.download_button(
                        label="Exportar .md",
                        data=md_export_live,
                        file_name=f"resposta_{(st.session_state.get('active_conversation_id') or 'conv')[:8]}_{live_idx}.md",
                        mime="text/markdown",
                        key=f"dl_md_{live_idx}",
                    )
                with ex_cols_live[1]:
                    _copy_markdown_button(
                        md_export_live, widget_key=f"cp_md_live_{live_idx}"
                    )

        if assistant_text:
            payload = {"role": "assistant", "content": assistant_text}
            if thinking_text:
                payload["thinking"] = thinking_text
            if telemetry:
                payload["telemetry"] = telemetry
            if retrieved_chunks:
                payload["retrieved_chunks"] = retrieved_chunks
            st.session_state.messages.append(payload)
        _maybe_auto_title_conversation(active_project.project_id)
        _save_active_conversation(active_project.project_id, str(active_model))
        # Sem isso, apos streaming longo o ramo `if not prompt` (historico + form) pode nao repintar;
        # o usuario via resposta mas sem caixa ate outro rerun (ex. sidebar).
        st.rerun()
