"""Ollama com stream que nao descarta chunks so de thinking (LlamaIndex ignora por padrao)."""

from __future__ import annotations

from typing import Any, List, Sequence

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    ChatResponseGen,
    MessageRole,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
)
from llama_index.core.llms.callbacks import llm_chat_callback
from llama_index.llms.ollama import Ollama


class OllamaThinkingStream(Ollama):
    """Emite ChatResponse tambem quando ha thinking sem content (fase de raciocinio)."""

    @llm_chat_callback()
    def stream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseGen:
        ollama_messages = self._convert_to_ollama_messages(messages)
        tools = kwargs.pop("tools", None)
        think = kwargs.pop("think", None) or self.thinking
        format = kwargs.pop("format", "json" if self.json_mode else None)

        def gen() -> ChatResponseGen:
            response = self.client.chat(
                model=self.model,
                messages=ollama_messages,
                stream=True,
                format=format,
                tools=tools,
                think=think,
                options=self._model_kwargs,
                keep_alive=self.keep_alive,
            )

            response_txt = ""
            thinking_txt = ""
            seen_tool_calls: set[tuple[str, str]] = set()
            all_tool_calls: list[dict] = []

            for r in response:
                msg = r["message"]
                thinking_piece = msg.get("thinking") or ""
                content_piece = msg.get("content")
                if content_piece is None and not thinking_piece:
                    continue

                r = dict(r)
                prev_len = len(response_txt)
                response_txt += content_piece or ""
                thinking_txt += thinking_piece
                stream_delta = content_piece if content_piece is not None else ""
                if not stream_delta and len(response_txt) > prev_len:
                    stream_delta = response_txt[prev_len:]

                new_tool_calls = [dict(t) for t in msg.get("tool_calls") or []]
                for tool_call in new_tool_calls:
                    key = (
                        str(tool_call["function"]["name"]),
                        str(tool_call["function"]["arguments"]),
                    )
                    if key in seen_tool_calls:
                        continue
                    seen_tool_calls.add(key)
                    all_tool_calls.append(tool_call)

                token_counts = self._get_response_token_counts(r)
                if token_counts:
                    r["usage"] = token_counts

                output_blocks: List[ThinkingBlock | TextBlock | ToolCallBlock] = [
                    TextBlock(text=response_txt)
                ]
                if thinking_txt:
                    output_blocks.insert(0, ThinkingBlock(content=thinking_txt))
                if all_tool_calls:
                    for tool_call in all_tool_calls:
                        output_blocks.append(
                            ToolCallBlock(
                                tool_name=tool_call.get("function", {}).get("name", ""),
                                tool_kwargs=tool_call.get("function", {}).get(
                                    "arguments", {}
                                ),
                            )
                        )

                yield ChatResponse(
                    message=ChatMessage(
                        blocks=output_blocks,
                        role=msg.get("role", MessageRole.ASSISTANT),
                    ),
                    delta=stream_delta or "",
                    raw=r,
                    # Sempre string: se usar None, LlamaIndex/"delta vazio" faz o
                    # ThinkingCaptureLLM cair no extract acumulado e repetir N vezes.
                    additional_kwargs={"thinking_delta": thinking_piece},
                )

        return gen()
