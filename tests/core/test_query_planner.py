import unittest

from query_planner import plan_query
from runtime_config import configure_runtime_env


class TestQueryPlanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = configure_runtime_env()

    def test_literal_exaustivo_intent(self):
        plan = plan_query("Onde aparece a palavra contrato nos autos", self.settings)
        self.assertEqual(plan.intent, "literal_exaustivo")
        self.assertTrue(plan.needs_literal_count)

    def test_auditoria_exaustiva_intent(self):
        plan = plan_query("Faca uma varredura exaustiva do termo contrato", self.settings)
        self.assertEqual(plan.intent, "auditoria_exaustiva")

    def test_page_and_range(self):
        plan = plan_query("O que consta na pagina 12 do laudo.pdf", self.settings)
        self.assertEqual(plan.requested_page, 12)
        self.assertEqual(plan.requested_source_hint, "laudo.pdf")

        plan2 = plan_query("fls 3 a 7 do processo", self.settings)
        self.assertEqual(plan2.requested_page_range, (3, 7))


if __name__ == "__main__":
    unittest.main()
