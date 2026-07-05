from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

from core.bootstrap import bootstrap_legacy

bootstrap_legacy()

from answer_validator import validate_answer  # noqa: E402
from query_expansion import expand_query  # noqa: E402
from query_planner import QueryPlan, plan_query  # noqa: E402
from rag_prompts import build_session_prompts  # noqa: E402
from retrieval_lexical import LexicalIndex, normalize_for_search  # noqa: E402
from retrieval_pipeline import HybridRetriever, RetrievalDiagnostics  # noqa: E402
from runtime_config import configure_runtime_env  # noqa: E402

from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode  # noqa: E402


def _settings():
    return configure_runtime_env()


def _diagnostics(
    *,
    intent: str = "padrao",
    profile: str = "preciso",
    fused_count: int = 2,
    literal_count: int = 0,
    requested_page: int | None = None,
    needs_exhaustive: bool = False,
    needs_literal_count: bool = False,
) -> RetrievalDiagnostics:
    plan = QueryPlan(
        intent=intent,
        profile=profile,
        needs_exhaustive=needs_exhaustive,
        needs_literal_count=needs_literal_count,
        requested_page=requested_page,
        requested_page_range=None,
        requested_source_hint=None,
        requested_section=None,
        reason="test",
    )
    return RetrievalDiagnostics(
        plan=plan,
        semantic_count=0,
        lexical_count=max(literal_count, 1 if needs_literal_count else 0),
        fused_count=fused_count,
        literal_count=literal_count,
        requested_page=requested_page,
        requested_page_range=None,
        requested_source_hint=None,
        requested_section=None,
    )


def _build_temp_index(rows: list[dict]) -> LexicalIndex:
    db_path = Path(tempfile.mkdtemp(prefix="lexical_contract_")) / "lexical.db"
    idx = LexicalIndex(str(db_path))
    idx.upsert_many(rows)
    return idx


def test_plan_query_promotes_historico_oficios_para_busca_exaustiva():
    plan = plan_query(
        (
            "Faça uma narrativa cronológica dos ofícios, despachos, informações e respostas "
            "do banco, cruzando os nexos causais e os desdobramentos periciais."
        ),
        _settings(),
    )

    assert plan.profile == "pericial"
    assert plan.needs_exhaustive is True


def test_plan_query_keeps_short_factual_question_fast():
    plan = plan_query("Qual a página 12?", _settings())
    assert plan.profile == "rapido"
    assert plan.intent == "factual_curta"


def test_expand_query_enriches_analytic_legal_queries_even_without_forensic_terms():
    query = "Faça um histórico narrativo do caso com foco em ofícios e despachos."
    expanded = expand_query(query, intent="analitico")

    assert expanded != query
    assert len(expanded.split()) > len(query.split())


def test_expand_query_uses_project_memory_entities_for_analytic_queries():
    query = "Resuma a movimentação do caso."
    expanded = expand_query(
        query,
        intent="analitico",
        project_memory="Banco Santander respondeu ao SETEC em nome de Márcia Moreira de Carvalho.",
    )

    assert expanded != query
    assert "Santander" in expanded or "SETEC" in expanded


def test_build_session_prompts_mentions_preserving_document_identifiers():
    condense, _, _ = build_session_prompts("", mode="rag", project_memory=None)
    lowered = condense.template.lower()

    assert "preserve literalmente" in lowered
    assert "números de oficio" in lowered or "numeros de oficio" in lowered
    assert "despacho" in lowered


def test_validate_answer_retries_on_low_coverage_in_light_mode():
    diagnostics = _diagnostics(intent="padrao", profile="preciso", fused_count=2, literal_count=1)

    validation = validate_answer(
        "Resposta resumida sem citações nem cobertura adequada.",
        diagnostics,
        "light",
    )

    assert validation.should_retry is True
    assert validation.retry_hint is not None


def test_validate_answer_still_retries_when_answer_denies_mentions_with_hits():
    diagnostics = _diagnostics(
        intent="literal_exaustivo",
        profile="pericial",
        fused_count=8,
        literal_count=3,
        needs_exhaustive=True,
        needs_literal_count=True,
    )

    validation = validate_answer(
        "Não há menção ao documento nos autos.",
        diagnostics,
        "light",
    )

    assert validation.should_retry is True


def test_lexical_search_contract_prefers_documents_matching_all_core_terms():
    idx = _build_temp_index(
        [
            {
                "node_id": "n1",
                "source_file": "oficio_4205816.pdf",
                "page": 182,
                "text": "Ofício nº 4205816/2025 requisita o original físico do contrato ao banco.",
                "window_text": "Ofício nº 4205816/2025 requisita o original físico do contrato ao banco.",
                "normalized_text": normalize_for_search(
                    "Ofício nº 4205816/2025 requisita o original físico do contrato ao banco."
                ),
            },
            {
                "node_id": "n2",
                "source_file": "email_resposta.pdf",
                "page": 188,
                "text": "O banco informou que o contrato foi assinado eletronicamente.",
                "window_text": "O banco informou que o contrato foi assinado eletronicamente.",
                "normalized_text": normalize_for_search(
                    "O banco informou que o contrato foi assinado eletronicamente."
                ),
            },
            {
                "node_id": "n3",
                "source_file": "informacao_108.pdf",
                "page": 178,
                "text": "A Informação 108/2025 trata da perícia grafotécnica e da necessidade de originais.",
                "window_text": "A Informação 108/2025 trata da perícia grafotécnica e da necessidade de originais.",
                "normalized_text": normalize_for_search(
                    "A Informação 108/2025 trata da perícia grafotécnica e da necessidade de originais."
                ),
            },
        ]
    )

    hits = idx.search("oficio 4205816 contrato original fisico", limit=5)

    assert hits
    assert all(
        sum(
            token in normalize_for_search(hit.text)
            for token in ("4205816", "contrato", "original", "fisico")
        )
        >= 2
        for hit in hits
    )


def test_lexical_search_preserves_source_filter_contract():
    idx = _build_temp_index(
        [
            {
                "node_id": "n1",
                "source_file": "oficio_4205816.pdf",
                "page": 182,
                "text": "Ofício nº 4205816/2025 requisita o contrato.",
                "window_text": "Ofício nº 4205816/2025 requisita o contrato.",
                "normalized_text": normalize_for_search("Ofício nº 4205816/2025 requisita o contrato."),
            },
            {
                "node_id": "n2",
                "source_file": "email_resposta.pdf",
                "page": 188,
                "text": "Contrato assinado eletronicamente.",
                "window_text": "Contrato assinado eletronicamente.",
                "normalized_text": normalize_for_search("Contrato assinado eletronicamente."),
            },
        ]
    )

    hits = idx.search("contrato", limit=5, source_hint="email_resposta")

    assert [hit.source_file for hit in hits] == ["email_resposta.pdf"]


class _FakeRetriever:
    def __init__(self, nodes: list[NodeWithScore]):
        self._nodes = nodes

    def retrieve(self, _query_bundle: QueryBundle) -> list[NodeWithScore]:
        return list(self._nodes)


class _FakeIndex:
    def __init__(self, nodes: list[NodeWithScore]):
        self._nodes = nodes

    def as_retriever(self, similarity_top_k: int):
        return _FakeRetriever(self._nodes[:similarity_top_k])


class _FakeLexicalIndex:
    def __init__(self, hits):
        self._hits = hits

    def search(self, query: str, limit: int, page_filter=None, page_range=None, source_hint=None):
        return list(self._hits[:limit])


class _FakePageIndex:
    def get_pages(self, source_file: str, pages: list[int], *, max_chars: int = 4500):
        return [
            type(
                "PageHit",
                (),
                {
                    "source_file": source_file,
                    "page": page,
                    "text": f"Pagina agregada {page} com contexto amplo do documento.",
                    "score": 0.0,
                    "doc_type": "",
                    "doc_number": "",
                },
            )()
            for page in pages
        ]


def test_rrf_fusion_should_diversify_results_when_many_candidates_share_same_page(monkeypatch):
    import retrieval_pipeline as rp

    settings = _settings()
    semantic_nodes = [
        NodeWithScore(
            node=TextNode(text="Ofício 4205816 requisita original do contrato.", metadata={"source_file": "oficio.pdf", "page": 182}),
            score=0.95,
        ),
        NodeWithScore(
            node=TextNode(text="Ofício 4205816 reitera o pedido ao banco.", metadata={"source_file": "oficio.pdf", "page": 182}),
            score=0.94,
        ),
        NodeWithScore(
            node=TextNode(text="Email do Santander informa assinatura eletrônica.", metadata={"source_file": "email.pdf", "page": 188}),
            score=0.70,
        ),
    ]
    lexical_hits = [
        type(
            "LexHit",
            (),
            {
                "source_file": "oficio.pdf",
                "page": 182,
                "text": "Ofício 4205816 requisita original do contrato.",
                "window_text": "Ofício 4205816 requisita original do contrato.",
                "score": 0.95,
                "node_id": "lex-1",
            },
        )(),
        type(
            "LexHit",
            (),
            {
                "source_file": "oficio.pdf",
                "page": 182,
                "text": "Ofício 4205816 reitera o pedido ao banco.",
                "window_text": "Ofício 4205816 reitera o pedido ao banco.",
                "score": 0.94,
                "node_id": "lex-2",
            },
        )(),
    ]

    plan = QueryPlan(
        intent="analitico",
        profile="preciso",
        needs_exhaustive=False,
        needs_literal_count=False,
        requested_page=None,
        requested_page_range=None,
        requested_source_hint=None,
        requested_section=None,
        reason="test",
    )
    monkeypatch.setattr(rp, "plan_query", lambda query, settings, forced_profile=None: plan)
    monkeypatch.setattr(rp, "expand_query", lambda query, project_memory="", intent="": query)

    retriever = HybridRetriever(
        index=_FakeIndex(semantic_nodes),
        settings=settings,
        lexical_index=_FakeLexicalIndex(lexical_hits),
    )

    results = retriever.retrieve(QueryBundle(query_str="Histórico dos documentos bancários"))
    top_two_sources = {
        (str(item.node.metadata.get("source_file")), int(item.node.metadata.get("page", 0)))
        for item in results[:2]
    }

    assert len(top_two_sources) == 2


def test_parent_context_retrieval_adds_page_level_context(monkeypatch):
    import retrieval_pipeline as rp

    settings = _settings()
    settings.parent_context_enabled = True
    settings.parent_context_max_nodes = 2
    settings.parent_context_page_radius = 0
    settings.parent_context_max_chars = 4500
    semantic_nodes = [
        NodeWithScore(
            node=TextNode(
                text="Chunk pequeno sobre cadeia de custodia.",
                metadata={"source_file": "autos.pdf", "page": 12},
            ),
            score=0.95,
        )
    ]
    plan = QueryPlan(
        intent="analitico",
        profile="preciso",
        needs_exhaustive=False,
        needs_literal_count=False,
        requested_page=None,
        requested_page_range=None,
        requested_source_hint=None,
        requested_section=None,
        reason="test",
    )
    monkeypatch.setattr(rp, "plan_query", lambda query, settings, forced_profile=None: plan)
    monkeypatch.setattr(rp, "expand_query", lambda query, project_memory="", intent="": query)

    retriever = HybridRetriever(
        index=_FakeIndex(semantic_nodes),
        settings=settings,
        lexical_index=_FakeLexicalIndex([]),
        page_index=_FakePageIndex(),
    )

    results = retriever.retrieve(QueryBundle(query_str="Analise a cadeia de custodia"))

    assert any(item.node.metadata.get("parent_context") for item in results)
    assert retriever.last_diagnostics is not None
    assert retriever.last_diagnostics.parent_context_count == 1


def test_multi_query_module_contract_exists():
    assert importlib.util.find_spec("multi_query") is not None


def test_cross_doc_graph_module_contract_exists():
    assert importlib.util.find_spec("cross_doc_graph") is not None


def test_document_metadata_classifier_hook_contract_exists():
    import ingest_service

    assert hasattr(ingest_service, "classify_chunk_document_metadata")

