"""Retriever vazio para modo chat geral (sem documentos indexados)."""

from __future__ import annotations

from typing import Optional

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle

from retrieval_pipeline import RetrievalDiagnostics


class EmptyRetriever(BaseRetriever):
    def __init__(self, callback_manager=None) -> None:
        super().__init__(callback_manager=callback_manager)
        self.last_diagnostics: Optional[RetrievalDiagnostics] = None

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        self.last_diagnostics = None
        return []
