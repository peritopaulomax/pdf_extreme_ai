import unittest

from app_workspace import should_run_audit_synthesis, workspace_from_label
from runtime_config import configure_runtime_env


class TestAppWorkspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = configure_runtime_env()

    def test_workspace_labels(self):
        self.assertEqual(workspace_from_label("Chat livre"), "free")
        self.assertEqual(workspace_from_label("Corretor"), "proofread")

    def test_audit_blocked_for_resumo(self):
        self.assertFalse(
            should_run_audit_synthesis(
                "Faca um resumo do caso",
                self.settings,
                forced_profile=None,
                audit_mode_ui=True,
            )
        )

    def test_audit_allowed_for_literal_with_checkbox(self):
        self.assertTrue(
            should_run_audit_synthesis(
                "Onde aparece a palavra contrato nos autos",
                self.settings,
                forced_profile=None,
                audit_mode_ui=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
