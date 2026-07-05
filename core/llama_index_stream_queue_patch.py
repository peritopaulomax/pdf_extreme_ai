"""Patch para LlamaIndex: enfileirar tambem delta vazio no stream do chat.

O CondensePlusContextChatEngine alimenta a fila de `StreamingAgentChatResponse`
somente quando `if chat.delta:`. Durante a fase de thinking do Ollama o delta de
texto e '' — a fila nao avanca, a UI nao atualiza ate o primeiro token da
resposta. Este modulo passa a dar `put_in_queue` em todo chunk do stream.
"""

from __future__ import annotations

from typing import Callable, Optional

_applied = False


def apply() -> None:
    global _applied
    if _applied:
        return

    from llama_index.core.chat_engine.types import (
        StreamingAgentChatResponse,
        dispatcher,
        is_function,
    )
    from llama_index.core.instrumentation.events.chat_engine import (
        StreamChatEndEvent,
        StreamChatErrorEvent,
        StreamChatStartEvent,
        StreamChatDeltaReceivedEvent,
    )
    from llama_index.core.memory import BaseMemory

    @dispatcher.span
    def write_response_to_history(
        self,
        memory: BaseMemory,
        on_stream_end_fn: Optional[Callable] = None,
    ) -> None:
        if self.chat_stream is None:
            raise ValueError(
                "chat_stream is None. Cannot write to history without chat_stream."
            )

        dispatcher.event(StreamChatStartEvent())
        stream_finished = False
        try:
            from chat_response_utils import assign_assistant_text_to_message, message_text

            final_text = ""
            last_chat = None
            for chat in self.chat_stream:
                last_chat = chat
                self.is_function = is_function(chat.message)
                delta = chat.delta or ""
                if chat.delta:
                    dispatcher.event(
                        StreamChatDeltaReceivedEvent(
                            delta=chat.delta,
                        )
                    )
                self.put_in_queue(delta)
                final_text += delta
            if last_chat is not None and self.is_function is not None:
                if not final_text.strip():
                    final_text = message_text(last_chat.message)
                assign_assistant_text_to_message(last_chat.message, final_text)
                memory.put(last_chat.message)
            stream_finished = True
        except Exception as e:
            dispatcher.event(StreamChatErrorEvent(exception=e))
            self.exception = e
            self.is_function_not_none_thread_event.set()
            self.put_in_queue("")
            raise
        finally:
            if stream_finished:
                dispatcher.event(StreamChatEndEvent())
            # Always release response_gen waiters, even after exceptions/timeouts.
            self.is_done = True
            self.is_function_not_none_thread_event.set()
            if stream_finished and on_stream_end_fn is not None and not self.is_function:
                on_stream_end_fn()

    StreamingAgentChatResponse.write_response_to_history = write_response_to_history
    _applied = True
