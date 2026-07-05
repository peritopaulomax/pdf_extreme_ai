import unittest

from proofread_service import build_highlighted_html


class TestProofreadHighlight(unittest.TestCase):
    def test_correction_bold_yellow(self):
        html_out = build_highlighted_html(
            "Este texto esta correto.",
            "Este texto estava errado.",
            [{"original": "estava errado", "corrected": "esta correto", "reason": "x"}],
        )
        self.assertIn("background-color:#fff59d", html_out)
        self.assertIn("font-weight:700", html_out)
        self.assertIn("esta correto", html_out)

    def test_suppression_context_words(self):
        source = "O valor com erro aqui foi pago."
        corrected = "O valor aqui foi pago."
        html_out = build_highlighted_html(
            corrected,
            source,
            [{"original": "com erro ", "corrected": "", "reason": "supressao"}],
        )
        self.assertIn("background-color:#fff59d", html_out)
        self.assertIn("valor", html_out)
        self.assertIn("aqui", html_out)


if __name__ == "__main__":
    unittest.main()
