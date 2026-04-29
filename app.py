import os
import tempfile
import hashlib
from pathlib import Path

from runtime_config import normalize_proxy_env

normalize_proxy_env()

import streamlit as st
import torch
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.chat_engine import CondensePlusContextChatEngine
from llama_index.core.memory import Memory
from llama_index.core.postprocessor import (
    MetadataReplacementPostProcessor,
    SentenceTransformerRerank,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointIdsList

from answer_validator import build_retry_prompt, validate_answer
from ingest_service import run_ingest
from rag_prompts import (
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
    check_ollama_health,
    configure_runtime_env,
    connect_qdrant,
    embedding_device,
    llm_timeout_for_model,
)


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
def load_chat_engines(
    selected_model: str,
    forced_profile: str | None,
    session_rules: str,
    project_id: str | None,
):
    settings = configure_runtime_env()
    if project_id:
        store = ProjectStore(settings.projects_registry_path)
        project = store.get_project(project_id)
        if project is not None:
            settings = apply_project_settings(settings, project)
    check_ollama_health(settings.ollama_host)

    Settings.llm = Ollama(
        model=selected_model,
        request_timeout=llm_timeout_for_model(settings, selected_model),
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
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=settings.qdrant_collection,
    )
    index = VectorStoreIndex.from_vector_store(vector_store)
    lexical_index = LexicalIndex(settings.lexical_db_path)
    hybrid_retriever = HybridRetriever(
        index=index,
        settings=settings,
        lexical_index=lexical_index,
        forced_profile=forced_profile,
    )
    window_expander = MetadataReplacementPostProcessor(target_metadata_key="window")
    node_postprocessors: list = [window_expander]
    if settings.use_reranker:
        node_postprocessors.append(
            SentenceTransformerRerank(
                model=settings.reranker_model_path,
                top_n=max(
                    settings.reranker_top_n,
                    settings.retrieval_profiles["preciso"].reranker_top_n,
                ),
                device="cuda" if torch.cuda.is_available() else "cpu",
            )
        )

    condense_prompt, context_prompt, context_refine_prompt = build_session_prompts(session_rules)
    shared_prompts = dict(
        condense_prompt=condense_prompt,
        context_prompt=context_prompt,
        context_refine_prompt=context_refine_prompt,
    )
    shared_memory = Memory.from_defaults(token_limit=settings.chat_memory_token_limit)
    chat_engine = CondensePlusContextChatEngine.from_defaults(
        retriever=hybrid_retriever,
        memory=shared_memory,
        **shared_prompts,
        node_postprocessors=node_postprocessors,
    )
    fallback_chat_engine = CondensePlusContextChatEngine.from_defaults(
        retriever=hybrid_retriever,
        memory=shared_memory,
        **shared_prompts,
        node_postprocessors=[window_expander],
    )
    return (
        chat_engine,
        fallback_chat_engine,
        hybrid_retriever,
        connected_host,
        settings,
        selected_model,
    )


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
if "auto_ingest_enabled" not in st.session_state:
    st.session_state.auto_ingest_enabled = True
if "last_upload_signature" not in st.session_state:
    st.session_state.last_upload_signature = ""
if "selected_doc_ids" not in st.session_state:
    st.session_state.selected_doc_ids = []

active_project = project_store.get_project(st.session_state.active_project_id) if st.session_state.active_project_id else None
runtime_settings = apply_project_settings(base_settings, active_project) if active_project else base_settings

with st.sidebar:
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
        st.session_state.messages = []
        st.cache_resource.clear()
        st.rerun()

    new_project_name = st.text_input("Novo projeto", placeholder="Ex.: Caso X")
    if st.button("Criar projeto"):
        if not new_project_name.strip():
            st.warning("Informe um nome de projeto.")
        else:
            created = project_store.create_project(new_project_name.strip())
            st.session_state.active_project_id = created.project_id
            st.session_state.messages = []
            st.cache_resource.clear()
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
            st.session_state.ingest_logs = []
            st.session_state.ingest_progress = 0.0
            try:
                result = run_ingest(
                    settings=runtime_settings,
                    input_files=paths,
                    rebuild=rebuild,
                    reprocess_all=reprocess_all,
                    update_checkpoint=True,
                    progress_callback=_append_ingest_log,
                )
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
                active_project = project_store.get_project(active_project.project_id) or active_project
                st.session_state.ingest_progress = 1.0
                st.cache_resource.clear()
                st.success(
                    f"Ingestao concluida: arquivos={result.files_processed}/{result.files_total} "
                    f"| paginas={result.total_pages} | chunks={result.total_chunks} "
                    f"| tempo={result.elapsed_s:.1f}s"
                )
                if result.errors:
                    st.error("Alguns arquivos falharam na ingestao.")
                    for err in result.errors:
                        st.caption(err)
            except Exception as exc:
                st.error(f"Falha na ingestao: {exc}")
            finally:
                st.session_state.ingest_running = False

        upload_sig = _upload_signature(uploaded_pdfs)
        should_auto = (
            bool(uploaded_pdfs)
            and st.session_state.auto_ingest_enabled
            and not st.session_state.ingest_running
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
            if st.button("Ingerir arquivos enviados", disabled=st.session_state.ingest_running):
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

        with st.expander("Documentos do projeto", expanded=False):
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
                    if st.button("Reprocessar selecionados", disabled=st.session_state.ingest_running):
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
                    if st.button("Remover selecionados", disabled=st.session_state.ingest_running):
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
                            st.cache_resource.clear()
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
                        if st.button("Reprocessar", key=f"reproc_{fid}_{idx}", disabled=st.session_state.ingest_running):
                            path = Path(str(doc.get("path", "")))
                            if not path.exists():
                                st.error(f"Arquivo fisico nao encontrado: {path}")
                            else:
                                _run_ingest_for_paths([path], [doc], rebuild=False, reprocess_all=True)
                    with row[1]:
                        if st.button("Remover", key=f"rm_{fid}_{idx}", disabled=st.session_state.ingest_running):
                            _remove_docs_from_indexes(runtime_settings, [doc])
                            p = Path(str(doc.get("path", "")))
                            try:
                                p.unlink(missing_ok=True)
                            except Exception:
                                pass
                            project_store.remove_documents(active_project.project_id, [fid])
                            st.cache_resource.clear()
                            st.rerun()
            else:
                st.caption("Nenhum documento registrado.")

        st.divider()
        st.subheader("Instrucoes globais do projeto")
        if st.session_state.project_rules_loaded_for != active_project.project_id:
            st.session_state.project_rules_input = active_project.global_rules
            st.session_state.project_rules_loaded_for = active_project.project_id
        st.text_area(
            "Regras extras para respostas (persistidas neste projeto)",
            key="project_rules_input",
            max_chars=2000,
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
                st.cache_resource.clear()
                st.success("Regras salvas para este projeto.")
        with rules_cols[1]:
            if st.button("Limpar regras do projeto"):
                st.session_state.project_rules_input = ""
                project_store.set_global_rules(active_project.project_id, "")
                st.cache_resource.clear()
                st.success("Regras removidas.")

selected_model = st.selectbox(
    "Modelo de geracao",
    options=runtime_settings.llm_models,
    index=runtime_settings.llm_models.index(runtime_settings.llm_default_model),
    help="Troque de modelo conforme necessidade. Modelos maiores podem demorar mais.",
)
with st.expander("Opcao avancada de estrategia", expanded=False):
    strategy_mode = st.selectbox(
        "Modo de estrategia",
        options=["automatico", "rapido", "preciso", "pericial"],
        index=0,
        help="Automatico adapta por prompt. Use fixo para auditoria.",
    )
forced_profile = None if strategy_mode == "automatico" else strategy_mode

st.caption(
    "Dica: aguarde a consulta atual terminar antes de trocar de modelo para evitar disputa de VRAM."
)

previous_model = st.session_state.get("selected_model")
if previous_model and previous_model != selected_model:
    st.cache_resource.clear()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    st.session_state.pop("messages", None)
st.session_state["selected_model"] = selected_model

if active_project is None:
    st.info("Crie e selecione um projeto na sidebar para habilitar o chat.")
    st.stop()

try:
    (
        chat_engine,
        fallback_chat_engine,
        hybrid_retriever,
        connected_host,
        runtime_settings,
        active_model,
    ) = load_chat_engines(
        selected_model,
        forced_profile,
        st.session_state.project_rules_input.strip(),
        active_project.project_id,
    )
    st.caption(
        f"Projeto ativo: {active_project.name} | "
        f"Qdrant: {connected_host}:{runtime_settings.qdrant_port} | "
        f"Collection: {runtime_settings.qdrant_collection} | "
        f"LexicalDB: {runtime_settings.lexical_db_path} | "
        f"Modelo ativo: {active_model}"
    )
except Exception as exc:
    st.error(str(exc))
    st.stop()

header_cols = st.columns([4, 1])
with header_cols[1]:
    if st.button("Nova conversa", help="Limpa o historico do chat e a memoria do assistente."):
        chat_engine.reset()
        fallback_chat_engine.reset()
        st.session_state.messages = []
        st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        telemetry = message.get("telemetry")
        if telemetry:
            st.caption(telemetry)

if prompt := st.chat_input("Pergunte sobre os documentos indexados"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            assistant_text = ""
            used_fallback = False
            telemetry = None
            try:
                stream_resp = chat_engine.stream_chat(prompt)
                gen = getattr(stream_resp, "response_gen", None)
                if gen is not None:
                    assistant_text = (st.write_stream(gen) or "").strip()
                    if not assistant_text:
                        assistant_text = (
                            getattr(stream_resp, "response", None)
                            or getattr(stream_resp, "unformatted_response", None)
                            or ""
                        )
                else:
                    assistant_text = getattr(stream_resp, "response", "") or ""
                    st.markdown(assistant_text)
            except Exception as exc:  # pragma: no cover
                msg = str(exc).lower()
                if _reranker_runtime_error(msg):
                    st.warning("Reranker falhou nesta mensagem. Respondendo sem reranker.")
                    used_fallback = True
                    try:
                        stream_fb = fallback_chat_engine.stream_chat(prompt)
                        gen_fb = getattr(stream_fb, "response_gen", None)
                        if gen_fb is not None:
                            assistant_text = (st.write_stream(gen_fb) or "").strip()
                            if not assistant_text:
                                assistant_text = (
                                    getattr(stream_fb, "response", None)
                                    or getattr(stream_fb, "unformatted_response", None)
                                    or ""
                                )
                        else:
                            assistant_text = getattr(stream_fb, "response", "") or ""
                            st.markdown(assistant_text)
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
            validation_level = "light"
            if diagnostics:
                validation_level = runtime_settings.retrieval_profiles[
                    diagnostics.plan.profile
                ].validation_level
            validation = validate_answer(assistant_text, diagnostics, validation_level)
            if validation.should_retry and assistant_text:
                retry_prompt = build_retry_prompt(prompt, validation)
                retry_resp = fallback_chat_engine.chat(retry_prompt)
                assistant_text = str(getattr(retry_resp, "response", retry_resp))
                used_fallback = True

            if diagnostics:
                telemetry = (
                    f"Estrategia: {diagnostics.plan.profile} ({diagnostics.plan.intent}) | "
                    f"semantico={diagnostics.semantic_count} | "
                    f"lexical={diagnostics.lexical_count} | "
                    f"fused={diagnostics.fused_count} | "
                    f"literal_hits={diagnostics.literal_count}"
                )
                if used_fallback:
                    telemetry += " | fallback=on"
                if validation.issues:
                    telemetry += " | validacao: " + "; ".join(validation.issues)
                st.caption(telemetry)

    if assistant_text:
        payload = {"role": "assistant", "content": assistant_text}
        if telemetry:
            payload["telemetry"] = telemetry
        st.session_state.messages.append(payload)
