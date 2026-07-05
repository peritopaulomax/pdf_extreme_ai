import unittest

from llama_index.core.base.llms.types import ChatMessage, MessageRole, TextBlock, ThinkingBlock

from chat_response_utils import assign_assistant_text_to_message, message_text


class TestChatMessageBlocks(unittest.TestCase):
    def test_assign_preserves_thinking_block(self):
        msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[
                ThinkingBlock(content="reasoning here"),
                TextBlock(text="old answer"),
            ],
        )
        assign_assistant_text_to_message(msg, "resposta final")
        self.assertEqual(len(msg.blocks), 2)
        self.assertIsInstance(msg.blocks[0], ThinkingBlock)
        self.assertEqual(msg.blocks[0].content, "reasoning here")
        self.assertIsInstance(msg.blocks[1], TextBlock)
        self.assertEqual(msg.blocks[1].text, "resposta final")
        self.assertEqual(message_text(msg), "resposta final")

    def test_assign_does_not_raise_on_multi_block(self):
        msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ThinkingBlock(content="x"), TextBlock(text="y")],
        )
        try:
            msg.content = "z"
            self.fail("expected ValueError")
        except ValueError:
            pass
        assign_assistant_text_to_message(msg, "z")
        self.assertEqual(message_text(msg), "z")


if __name__ == "__main__":
    unittest.main()
