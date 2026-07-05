from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import MetadataMode, NodeWithScore, QueryBundle, TextNode

from cross_doc_graph import extract_reference_keys, load_graph
from exhaustive_retrieval import PageOccurrence, search_exhaustive
from multi_query import build_multi_queries, fuse_query_lists
from page_index import PageLexicalIndex
from query_expansion import expand_query
from query_planner import QueryPlan, plan_query
from retrieval_lexical import LexicalIndex
from runtime_config import RuntimeSettings

RRF_K = 60


@dataclass
class RetrievalDiagnostics:
    plan: QueryPlan
    semantic_count: int
    lexical_count: int
    fused_count: int
    literal_count: int
    requested_page: int | None
    requested_page_range: tuple[int, int] | None
    requested_source_hint: str | None
    requested_section: str | None
    exhaustive_page_groups: int = 0
    multi_query_count: int = 1
    graph_expansion_count: int = 0
    entity_boost_count: int = 0
    parent_context_count: int = 0


def _normalize_scores(nodes: list[NodeWithScore]) -> list[float]:
    if not nodes:
        return []
    vals = [float(n.score or 0.0) for n in nodes]
    v_min = min(vals)
    v_max = max(vals)
    if abs(v_max - v_min) < 1e-9:
        return [1.0 for _ in vals]
    return [(v - v_min) / (v_max - v_min) for v in vals]


def _rrf_fuse(
    ranked_lists: list[list[NodeWithScore]],
    key_fn,
) -> dict[str, NodeWithScore]:
    scores: dict[str, float] = {}
    nodes: dict[str, NodeWithScore] = {}
    for rlist in ranked_lists:
        for rank, item in enumerate(rlist):
            k = key_fn(item)
            scores[k] = scores.get(k, 0.0) + 1.0 / (RRF_K + rank + 1)
            if k not in nodes:
                nodes[k] = item
    for k, sc in scores.items():
        nodes[k].score = sc
    return nodes


def _diversify_nodes(nodes: list[NodeWithScore], limit: int) -> list[NodeWithScore]:
    if len(nodes) <= 1:
        return nodes[:limit]
    picked: list[NodeWithScore] = []
    repeated: list[NodeWithScore] = []
    seen_locations: set[tuple[str, int]] = set()
    for item in nodes:
        source = str(item.node.metadata.get("source_file", ""))
        page = int(item.node.metadata.get("page", 0) or 0)
        key = (source, page)
        if key not in seen_locations:
            seen_locations.add(key)
            picked.append(item)
        else:
            repeated.append(item)
    return (picked + repeated)[:limit]


def _matches_filters(
    item: NodeWithScore,
    page_filter: int | None,
    page_range: tuple[int, int] | None,
    source_hint: str | None,
) -> bool:
    page = int(item.node.metadata.get("page", 0) or 0)
    source = str(item.node.metadata.get("source_file", "")).lower()
    if page_filter is not None and page != int(page_filter):
        return False
    if page_range is not None:
        start, end = page_range
        if page < int(start) or page > int(end):
            return False
    if source_hint and source_hint.strip():
        if source_hint.strip().lower() not in source:
            return False
    return True


def _section_markers(section: str | None) -> tuple[str, ...]:
    if not section:
        return ()
    mapping = {
        "titulo": ("title", "título", "titulo", "keywords", "abstract", "resumo"),
        "metodologia": ("metodologia", "método", "materials and methods", "materiais e métodos"),
        "conclusao": ("conclusão", "conclusao", "considerações finais", "consideracoes finais"),
        "introducao": ("introdução", "introducao", "introduction"),
        "cadeia_custodia": ("cadeia de custódia", "cadeia de custodia", "hash", "lacre"),
    }
    return mapping.get(section, ())


def _key_of(item: NodeWithScore) -> str:
    source = str(item.node.metadata.get("source_file", ""))
    page = str(item.node.metadata.get("page", ""))
    body = item.node.get_content(metadata_mode=MetadataMode.NONE)[:240]
    return f"{source}|{page}|{body}"


def _hits_to_nodes(hits) -> list[NodeWithScore]:
    nodes: list[NodeWithScore] = []
    for hit in hits:
        content = hit.window_text or hit.text
        node = TextNode(
            text=content,
            metadata={
                "source_file": hit.source_file,
                "page": hit.page,
                "lexical_hit": True,
                "node_id": getattr(hit, "node_id", ""),
                "doc_type": getattr(hit, "doc_type", "") or "",
                "doc_number": getattr(hit, "doc_number", "") or "",
            },
        )
        nodes.append(NodeWithScore(node=node, score=hit.score))
    return nodes


def _parse_ref_key(key: str) -> tuple[str, str] | None:
    kind, _, number = str(key or "").partition(":")
    kind = kind.strip().lower()
    number = number.strip()
    if not kind or not number:
        return None
    return kind, number


def _seed_ref_keys(nodes: list[NodeWithScore], *, max_nodes: int = 10) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for item in nodes[:max_nodes]:
        meta = getattr(item.node, "metadata", None) or {}
        doc_type = str(meta.get("doc_type") or "").strip().lower()
        doc_number = str(meta.get("doc_number") or "").strip()
        if doc_type and doc_number:
            key = f"{doc_type}:{doc_number}"
            if key not in seen:
                seen.add(key)
                keys.append(key)
        body = item.node.get_content(metadata_mode=MetadataMode.NONE)
        for key in extract_reference_keys(body):
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def _boost_entity_coverage(
    nodes: list[NodeWithScore], project_id: str | None
) -> tuple[list[NodeWithScore], int]:
    if not nodes or not project_id:
        return nodes, 0
    try:
        from entity_timeline import load_entities
    except Exception:
        return nodes, 0
    raw_entities = load_entities(project_id)
    terms: list[str] = []
    seen_terms: set[str] = set()
    for item in raw_entities:
        value = str(item.get("value") or "").strip().lower()
        if len(value) < 4 or value in seen_terms:
            continue
        seen_terms.add(value)
        terms.append(value)
        if len(terms) >= 18:
            break
    if not terms:
        return nodes, 0
    covered: set[str] = set()
    total_new_hits = 0
    for item in nodes:
        body = item.node.get_content(metadata_mode=MetadataMode.NONE).lower()
        matched = {term for term in terms if term in body}
        new_hits = matched - covered
        if new_hits:
            item.score = float(item.score or 0.0) + min(0.18, 0.04 * len(new_hits))
            covered.update(new_hits)
            total_new_hits += len(new_hits)
    return sorted(nodes, key=lambda n: float(n.score or 0.0), reverse=True), total_new_hits


def _add_parent_context_nodes(
    nodes: list[NodeWithScore],
    page_index: PageLexicalIndex | None,
    settings: RuntimeSettings,
) -> tuple[list[NodeWithScore], int]:
    if not nodes or page_index is None:
        return nodes, 0
    if not getattr(settings, "parent_context_enabled", True):
        return nodes, 0

    max_seed_nodes = max(0, int(getattr(settings, "parent_context_max_nodes", 4)))
    if max_seed_nodes <= 0:
        return nodes, 0
    page_radius = max(0, int(getattr(settings, "parent_context_page_radius", 0)))
    max_chars = max(500, int(getattr(settings, "parent_context_max_chars", 4500)))

    existing_parent_pages: set[tuple[str, int]] = set()
    for item in nodes:
        meta = getattr(item.node, "metadata", None) or {}
        if meta.get("page_level") or meta.get("parent_context"):
            source = str(meta.get("source_file") or "")
            page = int(meta.get("page") or 0)
            if source and page > 0:
                existing_parent_pages.add((source, page))

    parent_nodes: list[NodeWithScore] = []
    seed_count = 0
    for item in nodes:
        meta = getattr(item.node, "metadata", None) or {}
        if meta.get("page_level") or meta.get("parent_context"):
            continue
        source = str(meta.get("source_file") or "")
        page = int(meta.get("page") or 0)
        if not source or page <= 0:
            continue
        seed_count += 1
        if seed_count > max_seed_nodes:
            break
        pages = [p for p in range(page - page_radius, page + page_radius + 1) if p > 0]
        for ph in page_index.get_pages(source, pages, max_chars=max_chars):
            key = (ph.source_file, ph.page)
            if key in existing_parent_pages:
                continue
            existing_parent_pages.add(key)
            parent_nodes.append(
                NodeWithScore(
                    node=TextNode(
                        text=ph.text,
                        metadata={
                            "source_file": ph.source_file,
                            "page": ph.page,
                            "parent_context": True,
                            "page_level": True,
                            "doc_type": ph.doc_type,
                            "doc_number": ph.doc_number,
                        },
                    ),
                    score=max(0.0, float(item.score or 0.0) - 0.02),
                )
            )

    if not parent_nodes:
        return nodes, 0
    enriched = sorted(
        [*nodes, *parent_nodes],
        key=lambda n: float(n.score or 0.0),
        reverse=True,
    )
    return enriched, len(parent_nodes)


class HybridRetriever(BaseRetriever):
    def __init__(
        self,
        index,
        settings: RuntimeSettings,
        lexical_index: LexicalIndex,
        forced_profile: Optional[str] = None,
        page_index: Optional[PageLexicalIndex] = None,
        project_memory: str = "",
        project_id: str | None = None,
        callback_manager=None,
    ) -> None:
        super().__init__(callback_manager=callback_manager)
        self.index = index
        self.settings = settings
        self.lexical_index = lexical_index
        self.page_index = page_index
        self.forced_profile = forced_profile
        self.project_memory = project_memory or ""
        self.project_id = project_id or ""
        self.last_diagnostics: Optional[RetrievalDiagnostics] = None
        self.last_retrieved_nodes: list[NodeWithScore] = []
        self.last_audit_pages: list[PageOccurrence] = []

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        query = query_bundle.query_str or ""
        plan, profile = self._build_plan(query)
        page_filter = plan.requested_page
        page_range = plan.requested_page_range
        source_hint = plan.requested_source_hint
        section_markers = _section_markers(plan.requested_section)

        expanded, query_variants = self._expand_query_variants(query, plan)
        semantic_nodes, lex_nodes, exhaustive_pages, page_groups = self._retrieve_nodes(
            expanded, query_variants, plan, profile
        )
        page_nodes = self._retrieve_page_nodes(expanded, plan, profile)

        self._apply_section_boost(semantic_nodes, section_markers)
        self._apply_section_boost(lex_nodes, section_markers)

        fused_nodes = self._fuse_and_diversify(semantic_nodes, lex_nodes, page_nodes, profile)
        fused_nodes, graph_expansion_count = self._apply_graph_expansion(fused_nodes, profile)
        fused_nodes, entity_boost_count = _boost_entity_coverage(fused_nodes, self.project_id)
        fused_nodes = _diversify_nodes(fused_nodes, profile.reranker_candidate_k)
        fused_nodes, parent_context_count = _add_parent_context_nodes(
            fused_nodes, self.page_index, self.settings
        )

        literal_count = len(lex_nodes) if plan.intent != "auditoria_exaustiva" else exhaustive_pages

        self.last_diagnostics = RetrievalDiagnostics(
            plan=plan,
            semantic_count=len(semantic_nodes),
            lexical_count=len(lex_nodes),
            fused_count=len(fused_nodes),
            literal_count=literal_count,
            requested_page=page_filter,
            requested_page_range=page_range,
            requested_source_hint=source_hint,
            requested_section=plan.requested_section,
            exhaustive_page_groups=exhaustive_pages,
            multi_query_count=len(query_variants),
            graph_expansion_count=graph_expansion_count,
            entity_boost_count=entity_boost_count,
            parent_context_count=parent_context_count,
        )
        self.last_retrieved_nodes = list(fused_nodes)
        self.last_audit_pages = list(page_groups)
        return fused_nodes

    def _build_plan(self, query: str) -> tuple[QueryPlan, Any]:
        plan = plan_query(query, self.settings, forced_profile=self.forced_profile)
        profile = self.settings.retrieval_profiles[plan.profile]
        return plan, profile

    def _expand_query_variants(self, query: str, plan: QueryPlan) -> tuple[str, list[str]]:
        expanded = expand_query(
            query,
            project_memory=self.project_memory,
            intent=plan.intent,
        )
        query_variants = [expanded]
        if (
            self.settings.multi_query_mode != "off"
            and not plan.requested_page
            and plan.intent in ("analitico", "padrao", "historico_documental", "tese_acusacao_defesa")
        ):
            alts = build_multi_queries(
                query,
                intent=plan.intent,
                max_queries=max(1, self.settings.multi_query_max_subq),
            )
            expanded_alts = [
                expand_query(item, project_memory=self.project_memory, intent=plan.intent)
                for item in alts
            ]
            query_variants = fuse_query_lists(expanded, expanded_alts)
        return expanded, query_variants

    def _retrieve_nodes(
        self,
        expanded: str,
        query_variants: list[str],
        plan: QueryPlan,
        profile: Any,
    ) -> tuple[list[NodeWithScore], list[NodeWithScore], int, list[PageOccurrence]]:
        page_filter = plan.requested_page
        page_range = plan.requested_page_range
        source_hint = plan.requested_source_hint
        critical_intent = plan.intent in (
            "literal_exaustivo",
            "cadeia_custodia",
            "forense_autenticidade",
            "tese_acusacao_defesa",
            "auditoria_exaustiva",
        ) or page_range is not None
        semantic_top_k = profile.semantic_top_k * (2 if critical_intent else 1)
        lexical_top_k = profile.lexical_top_k * (2 if critical_intent else 1)

        if plan.intent == "auditoria_exaustiva":
            ex_hits, page_groups = search_exhaustive(
                self.lexical_index,
                expanded,
                batch_size=self.settings.exhaustive_batch_size,
                max_total=self.settings.exhaustive_max_hits,
                page_filter=page_filter,
                page_range=page_range,
                source_hint=source_hint,
            )
            lex_nodes = _hits_to_nodes(ex_hits[: profile.reranker_candidate_k])
            return [], lex_nodes, len(page_groups), page_groups

        sem_retriever = self.index.as_retriever(similarity_top_k=semantic_top_k)
        semantic_nodes: list[NodeWithScore] = []
        lexical_hits = []
        for idx, variant in enumerate(query_variants):
            variant_bundle = QueryBundle(query_str=variant)
            batch_semantic = sem_retriever.retrieve(variant_bundle)
            batch_semantic = [
                item
                for item in batch_semantic
                if _matches_filters(item, page_filter, page_range, source_hint)
            ]
            if idx:
                for item in batch_semantic:
                    item.score = float(item.score or 0.0) * max(0.75, 1.0 - 0.08 * idx)
            semantic_nodes.extend(batch_semantic)
            lexical_hits.extend(
                self.lexical_index.search(
                    variant,
                    limit=lexical_top_k,
                    page_filter=page_filter,
                    page_range=page_range,
                    source_hint=source_hint,
                )
            )
        lex_nodes = _hits_to_nodes(lexical_hits)
        return semantic_nodes, lex_nodes, 0, []

    def _retrieve_page_nodes(
        self,
        expanded: str,
        plan: QueryPlan,
        profile: Any,
    ) -> list[NodeWithScore]:
        page_nodes: list[NodeWithScore] = []
        if not self.page_index or (not plan.requested_page and not plan.requested_page_range):
            return page_nodes
        for ph in self.page_index.search(
            expanded,
            limit=min(12, profile.reranker_candidate_k),
            page_filter=plan.requested_page,
            page_range=plan.requested_page_range,
            source_hint=plan.requested_source_hint,
        ):
            node = TextNode(
                text=ph.text,
                metadata={
                    "source_file": ph.source_file,
                    "page": ph.page,
                    "page_level": True,
                    "doc_type": ph.doc_type,
                    "doc_number": ph.doc_number,
                },
            )
            page_nodes.append(NodeWithScore(node=node, score=ph.score + 0.05))
        return page_nodes

    def _apply_section_boost(
        self, nodes: list[NodeWithScore], section_markers: tuple[str, ...]
    ) -> None:
        if not section_markers:
            return
        for item in nodes:
            body = item.node.get_content(metadata_mode=MetadataMode.NONE).lower()
            if any(marker in body for marker in section_markers):
                item.score = float(item.score or 0.0) + 0.15

    def _fuse_and_diversify(
        self,
        semantic_nodes: list[NodeWithScore],
        lex_nodes: list[NodeWithScore],
        page_nodes: list[NodeWithScore],
        profile: Any,
    ) -> list[NodeWithScore]:
        ranked_lists = [semantic_nodes, lex_nodes]
        if page_nodes:
            ranked_lists.append(page_nodes)
        fused_map = _rrf_fuse(ranked_lists, _key_of)
        fused_nodes = sorted(
            fused_map.values(), key=lambda n: float(n.score or 0.0), reverse=True
        )
        return _diversify_nodes(fused_nodes, profile.reranker_candidate_k)

    def _apply_graph_expansion(
        self, fused_nodes: list[NodeWithScore], profile: Any
    ) -> tuple[list[NodeWithScore], int]:
        graph_expansion_count = 0
        if not self.project_id:
            return fused_nodes, graph_expansion_count
        graph = load_graph(self.project_id)
        if not graph:
            return fused_nodes, graph_expansion_count

        related_pairs: list[tuple[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for seed in _seed_ref_keys(fused_nodes):
            parsed_seed = _parse_ref_key(seed)
            if parsed_seed and parsed_seed not in seen_pairs:
                seen_pairs.add(parsed_seed)
                related_pairs.append(parsed_seed)
            entry = graph.get(seed) or {}
            for related in entry.get("references") or []:
                parsed = _parse_ref_key(str(related))
                if parsed and parsed not in seen_pairs:
                    seen_pairs.add(parsed)
                    related_pairs.append(parsed)

        extra_hits = self.lexical_index.search_by_doc_refs(
            related_pairs,
            limit=max(4, profile.reranker_top_n // 2),
        )
        extra_nodes = _hits_to_nodes(extra_hits)
        if not extra_nodes:
            return fused_nodes, graph_expansion_count

        existing_keys = {_key_of(item) for item in fused_nodes}
        for item in extra_nodes:
            key = _key_of(item)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            item.score = float(item.score or 0.0) + 0.03
            fused_nodes.append(item)

        fused_nodes = sorted(
            fused_nodes, key=lambda n: float(n.score or 0.0), reverse=True
        )
        fused_nodes = _diversify_nodes(fused_nodes, profile.reranker_candidate_k)
        return fused_nodes, len(extra_nodes)
