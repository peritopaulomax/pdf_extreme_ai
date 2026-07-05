"""Cache do ProjectStack (equivalente a st.cache_resource em app.py)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import Any

from core.bootstrap import bootstrap_legacy

_lock = Lock()
_reranker_cache: dict[tuple, Any] = {}


@dataclass
class ProjectStack:
    hybrid_retriever: Any
    connected_host: str
    settings: Any
    selected_model: str
    capture_llm: Any
    window_expander: Any
    display_name_pp: Any
    use_reranker: bool
    chat_mode: str


def _load_reranker(settings, reranker_top_n: int):
    from llama_index.core.postprocessor import SentenceTransformerRerank
    from runtime_config import reranker_inference_device

    key = (
        settings.reranker_model_path,
        reranker_top_n,
        settings.reranker_device,
    )
    if key in _reranker_cache:
        return _reranker_cache[key]
    rr = SentenceTransformerRerank(
        model=settings.reranker_model_path,
        top_n=reranker_top_n,
        device=reranker_inference_device(settings.reranker_device),
    )
    _reranker_cache[key] = rr
    return rr


def load_project_stack(
    selected_model: str,
    forced_profile: str | None,
    project_id: str | None,
    chat_mode: str,
    workspace: str,
) -> ProjectStack:
    bootstrap_legacy()
    from llama_index.core import Settings
    from llama_index.core.postprocessor import MetadataReplacementPostProcessor
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.core import VectorStoreIndex
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    from ollama_thinking_stream import OllamaThinkingStream
    from empty_retriever import EmptyRetriever
    from display_name import DisplayNamePostprocessor
    from index_bootstrap import embedding_vector_size, ensure_qdrant_collection
    from page_index import PageLexicalIndex
    from retrieval_lexical import LexicalIndex
    from retrieval_pipeline import HybridRetriever
    import project_memory as project_memory_store
    from case_memory import enrich_project_memory
    from project_store import ProjectStore, apply_project_settings
    from runtime_config import (
        check_ollama_health,
        configure_runtime_env,
        connect_qdrant,
        embedding_device,
        llm_timeout_for_model,
    )
    from llm_thinking import ThinkingCaptureLLM
    from rag_prompts import ChatPromptMode

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


@lru_cache(maxsize=16)
def get_cached_stack(
    selected_model: str,
    forced_profile: str | None,
    project_id: str,
    chat_mode: str,
    workspace: str,
) -> ProjectStack:
    return load_project_stack(
        selected_model, forced_profile, project_id, chat_mode, workspace
    )


def build_chat_engines(
    stack: ProjectStack,
    session_rules: str,
    memory,
    project_memory: str = "",
    *,
    workspace: str = "rag",
):
    bootstrap_legacy()
    from llama_index.core.chat_engine import CondensePlusContextChatEngine
    from free_chat_engine import build_free_chat_engines
    from rag_prompts import build_session_prompts

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
            _load_reranker(settings, reranker_top_n)
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


def invalidate_stack_cache() -> None:
    get_cached_stack.cache_clear()
    _reranker_cache.clear()
