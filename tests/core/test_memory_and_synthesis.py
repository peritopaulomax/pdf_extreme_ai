import unittest

from analytical_synthesis import should_run_analytical_synthesis
from answer_validator import validate_answer
from conversation_memory import compress_messages_for_memory, _count_turns
from case_memory import build_auto_case_context, enrich_project_memory
from query_planner import QueryPlan
from retrieval_pipeline import RetrievalDiagnostics


def _plan(intent: str = "analitico") -> QueryPlan:
    return QueryPlan(
        intent=intent,
        profile="preciso",
        needs_exhaustive=False,
        needs_literal_count=False,
        requested_page=None,
        requested_page_range=None,
        requested_source_hint=None,
        requested_section=None,
        reason="test",
    )


def _diag(**kwargs) -> RetrievalDiagnostics:
    plan = _plan(kwargs.pop("intent", "analitico"))
    return RetrievalDiagnostics(
        plan=plan,
        semantic_count=kwargs.get("semantic_count", 8),
        lexical_count=kwargs.get("lexical_count", 8),
        fused_count=kwargs.get("fused_count", 10),
        literal_count=kwargs.get("literal_count", 0),
        requested_page=None,
        requested_page_range=None,
        requested_source_hint=None,
        requested_section=None,
    )


class TestConversationMemory(unittest.TestCase):
    def test_no_compress_below_threshold(self):
        msgs = [{"role": "user", "content": f"Pergunta {i}"} for i in range(4)]
        out = compress_messages_for_memory(msgs, summarize_threshold_turns=8)
        self.assertEqual(len(out), 4)

    def test_compress_above_threshold(self):
        msgs = []
        for i in range(10):
            msgs.append({"role": "user", "content": f"Pergunta {i}"})
            msgs.append({"role": "assistant", "content": f"Resposta {i}"})
        self.assertEqual(_count_turns(msgs), 10)
        out = compress_messages_for_memory(msgs, recent_turns=2, summarize_threshold_turns=4)
        self.assertGreaterEqual(len(out), 3)
        self.assertTrue(out[0]["content"].startswith("[Resumo da conversa anterior"))
        self.assertEqual(out[-2]["content"], "Pergunta 9")


class TestAnalyticalSynthesis(unittest.TestCase):
    def test_triggers_on_summary_query(self):
        self.assertTrue(
            should_run_analytical_synthesis("Faca um panorama do caso", _plan("padrao"))
        )

    def test_skips_literal_exhaustive(self):
        self.assertFalse(
            should_run_analytical_synthesis(
                "onde aparece contrato",
                _plan("literal_exaustivo"),
            )
        )


class TestAnswerValidatorGrounding(unittest.TestCase):
    def test_retry_when_no_citation_but_fused_high(self):
        answer = "O processo trata de fraude bancaria sem citar paginas."
        result = validate_answer(answer, _diag(fused_count=10), "light")
        self.assertTrue(any("nao citou" in i.lower() for i in result.issues))
        self.assertTrue(result.should_retry)


class TestCaseMemory(unittest.TestCase):
    def test_enrich_combines_manual_and_auto(self):
        text = enrich_project_memory("proj-inexistente", "Regra manual do perito.")
        self.assertEqual(text, "Regra manual do perito.")
        self.assertEqual(build_auto_case_context(""), "")


if __name__ == "__main__":
    unittest.main()
