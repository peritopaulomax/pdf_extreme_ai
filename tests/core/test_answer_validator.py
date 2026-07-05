import unittest

from answer_validator import validate_answer
from query_planner import QueryPlan
from retrieval_pipeline import RetrievalDiagnostics


def _diag(**kwargs) -> RetrievalDiagnostics:
    plan = QueryPlan(
        intent=kwargs.pop("intent", "literal_exaustivo"),
        profile=kwargs.pop("profile", "preciso"),
        needs_exhaustive=True,
        needs_literal_count=True,
        requested_page=kwargs.pop("requested_page", None),
        requested_page_range=kwargs.pop("requested_page_range", None),
        requested_source_hint=None,
        requested_section=None,
        reason="test",
    )
    return RetrievalDiagnostics(
        plan=plan,
        semantic_count=kwargs.get("semantic_count", 4),
        lexical_count=kwargs.get("lexical_count", 5),
        fused_count=kwargs.get("fused_count", 5),
        literal_count=kwargs.get("literal_count", 3),
        requested_page=plan.requested_page,
        requested_page_range=plan.requested_page_range,
        requested_source_hint=None,
        requested_section=None,
    )


class TestAnswerValidator(unittest.TestCase):
    def test_light_retry_when_denies_but_literal_hits(self):
        answer = "Nao ha mencao do termo nos autos analisados."
        result = validate_answer(answer, _diag(), "light")
        self.assertFalse(result.ok)
        self.assertTrue(result.should_retry)
        self.assertIsNotNone(result.retry_hint)

    def test_light_no_retry_without_literal_hits(self):
        answer = "Nao ha mencao do termo nos autos."
        result = validate_answer(answer, _diag(literal_count=0), "light")
        self.assertTrue(result.should_retry is False or result.ok)

    def test_fused_low_analitico_issue(self):
        answer = "Resumo sem citacao."
        diag = _diag(intent="analitico", fused_count=2, literal_count=0)
        result = validate_answer(answer, diag, "light")
        self.assertTrue(any("fused" in i.lower() for i in result.issues))

    def test_strong_skips_total_requirement_for_summary_query(self):
        answer = "Resumo com citacao [arquivo.pdf, fls. 2] sem contagem literal."
        diag = _diag(intent="forense_autenticidade", literal_count=10)
        result = validate_answer(
            answer,
            diag,
            "strong",
            user_query="Faça um resumo do caso com audio e video",
        )
        self.assertNotIn(
            "Consulta literal exaustiva sem total de ocorrencias no texto.",
            result.issues,
        )
        self.assertFalse(result.should_retry)


if __name__ == "__main__":
    unittest.main()
