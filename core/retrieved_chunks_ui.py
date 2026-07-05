"""Serializacao e exibicao de trechos recuperados pelo RAG na UI Streamlit."""

from __future__ import annotations

from typing import Any

import streamlit as st
from display_name import human_source_label
from llama_index.core.schema import MetadataMode, NodeWithScore


def nodes_to_serializable(nodes: list[NodeWithScore], *, max_snippet: int = 300) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rank, nws in enumerate(nodes, start=1):
        meta = getattr(nws.node, "metadata", None) or {}
        source = str(meta.get("source_file", "") or "")
        display = str(meta.get("display_name", "") or "") or human_source_label(source)
        body = (nws.node.get_content(metadata_mode=MetadataMode.NONE) or "").strip()
        if len(body) > max_snippet:
            body = body[: max_snippet - 3] + "..."
        out.append(
            {
                "rank": rank,
                "display_name": display,
                "source_file": source,
                "page": int(meta.get("page", 0) or 0),
                "score": float(nws.score or 0.0),
                "snippet": body,
                "lexical_hit": bool(meta.get("lexical_hit")),
                "parent_context": bool(meta.get("parent_context")),
                "page_level": bool(meta.get("page_level")),
                "doc_type": str(meta.get("doc_type", "") or ""),
                "doc_number": str(meta.get("doc_number", "") or ""),
            }
        )
    return out


def render_retrieved_chunks_expander(
    chunks: list[dict[str, Any]] | None,
    *,
    key_suffix: str,
    expanded: bool = False,
) -> None:
    if not chunks:
        return
    with st.expander(f"Trechos usados nesta resposta ({len(chunks)})", expanded=expanded):
        for item in chunks:
            label = item.get("display_name") or item.get("source_file") or "?"
            page = item.get("page", 0)
            score = item.get("score", 0.0)
            lex = " | lexical" if item.get("lexical_hit") else ""
            parent = " | contexto-pai" if item.get("parent_context") else ""
            st.markdown(f"**#{item.get('rank', '?')}** `{label}` — pag. {page} — score {score:.3f}{lex}{parent}")
            st.caption(item.get("snippet", ""))
