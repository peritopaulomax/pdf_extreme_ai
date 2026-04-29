from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import MetadataMode, NodeWithScore, QueryBundle, TextNode

from query_planner import QueryPlan, plan_query
from retrieval_lexical import LexicalIndex
from runtime_config import RuntimeSettings


@dataclass
class RetrievalDiagnostics:
    plan: QueryPlan
    semantic_count: int
    lexical_count: int
    fused_count: int
    literal_count: int


def _normalize_scores(nodes: list[NodeWithScore]) -> list[float]:
    if not nodes:
        return []
    vals = [float(n.score or 0.0) for n in nodes]
    v_min = min(vals)
    v_max = max(vals)
    if abs(v_max - v_min) < 1e-9:
        return [1.0 for _ in vals]
    return [(v - v_min) / (v_max - v_min) for v in vals]


class HybridRetriever(BaseRetriever):
    def __init__(
        self,
        index,
        settings: RuntimeSettings,
        lexical_index: LexicalIndex,
        forced_profile: Optional[str] = None,
        callback_manager=None,
    ) -> None:
        super().__init__(callback_manager=callback_manager)
        self.index = index
        self.settings = settings
        self.lexical_index = lexical_index
        self.forced_profile = forced_profile
        self.last_diagnostics: Optional[RetrievalDiagnostics] = None

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        query = query_bundle.query_str or ""
        plan = plan_query(query, self.settings, forced_profile=self.forced_profile)
        profile = self.settings.retrieval_profiles[plan.profile]

        sem_retriever = self.index.as_retriever(
            similarity_top_k=profile.semantic_top_k,
        )
        semantic_nodes = sem_retriever.retrieve(query_bundle)
        sem_norm = _normalize_scores(semantic_nodes)

        lexical_hits = self.lexical_index.search(query, limit=profile.lexical_top_k)
        lex_nodes: list[NodeWithScore] = []
        for hit in lexical_hits:
            content = hit.window_text or hit.text
            node = TextNode(
                text=content,
                metadata={
                    "source_file": hit.source_file,
                    "page": hit.page,
                    "lexical_hit": True,
                    "node_id": hit.node_id,
                },
            )
            lex_nodes.append(NodeWithScore(node=node, score=hit.score))
        lex_norm = _normalize_scores(lex_nodes)

        fused: dict[str, NodeWithScore] = {}

        def key_of(item: NodeWithScore) -> str:
            source = str(item.node.metadata.get("source_file", ""))
            page = str(item.node.metadata.get("page", ""))
            body = item.node.get_content(metadata_mode=MetadataMode.NONE)[:240]
            return f"{source}|{page}|{body}"

        for idx, item in enumerate(semantic_nodes):
            k = key_of(item)
            weighted = sem_norm[idx] * profile.semantic_weight
            current = fused.get(k)
            if current is None or weighted > float(current.score or 0.0):
                item.score = weighted
                fused[k] = item

        for idx, item in enumerate(lex_nodes):
            k = key_of(item)
            weighted = lex_norm[idx] * profile.lexical_weight
            current = fused.get(k)
            if current is None:
                item.score = weighted
                fused[k] = item
            else:
                current.score = float(current.score or 0.0) + weighted

        fused_nodes = sorted(fused.values(), key=lambda n: float(n.score or 0.0), reverse=True)
        fused_nodes = fused_nodes[: profile.reranker_candidate_k]

        self.last_diagnostics = RetrievalDiagnostics(
            plan=plan,
            semantic_count=len(semantic_nodes),
            lexical_count=len(lex_nodes),
            fused_count=len(fused_nodes),
            literal_count=len(lexical_hits),
        )
        return fused_nodes
