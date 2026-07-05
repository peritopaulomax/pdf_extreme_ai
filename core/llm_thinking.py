"""Captura de thinking/reasoning do Ollama via LlamaIndex."""

from __future__ import annotations

from typing import Any, Sequence

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    ChatResponseAsyncGen,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseAsyncGen,
    CompletionResponseGen,
    LLMMetadata,
    ThinkingBlock,
)
from llama_index.core.bridge.pydantic import Field, PrivateAttr, SerializeAsAny
from llama_index.core.llms.callbacks import llm_chat_callback, llm_completion_callback
from llama_index.core.llms.llm import LLM


def extract_thinking_from_chat_response(resp: ChatResponse | None) -> str | None:
    if resp is None:
        return None
    parts: list[str] = []
    message = getattr(resp, "message", None)
    if message is not None:
        blocks = getattr(message, "blocks", None) or []
        for block in blocks:
            if isinstance(block, ThinkingBlock):
                text = (block.content or "").strip()
                if text:
                    parts.append(text)
    if parts:
        merged = "".join(parts).strip()
        return merged or None
    additional = getattr(resp, "additional_kwargs", None) or {}
    if isinstance(additional, dict):
        for key in ("thinking", "reasoning"):
            val = additional.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
    raw = getattr(resp, "raw", None)
    if isinstance(raw, dict):
        msg = raw.get("message")
        if isinstance(msg, dict):
            thinking = msg.get("thinking")
            if isinstance(thinking, str) and thinking.strip():
                parts.append(thinking.strip())
    if not parts:
        return None
    merged = "".join(parts).strip()
    return merged or None


def _thinking_delta(resp: ChatResponse) -> str:
    """Pedaco incremental de thinking no stream.

    Se `thinking_delta` vier em additional_kwargs (stream Ollama), usa apenas
    isso. Caso contrario extrai texto completo (ex.: respostas nao-stream).
    """
    additional = getattr(resp, "additional_kwargs", None) or {}
    if isinstance(additional, dict) and "thinking_delta" in additional:
        val = additional.get("thinking_delta")
        return val if isinstance(val, str) else ""
    block_text = extract_thinking_from_chat_response(resp)
    return block_text or ""


class ThinkingCaptureLLM(LLM):
    """LLM wrapper que acumula thinking do Ollama em stream_chat/chat."""

    llm: SerializeAsAny[LLM] = Field(description="LLM interno (ex.: Ollama).")
    _last_thinking: str | None = PrivateAttr(default=None)
    _thinking_parts: list[str] = PrivateAttr(default_factory=list)

    @classmethod
    def class_name(cls) -> str:
        return "thinking_capture_llm"

    @property
    def metadata(self) -> LLMMetadata:
        return self.llm.metadata

    @property
    def last_thinking(self) -> str | None:
        return self._last_thinking

    @property
    def live_thinking(self) -> str | None:
        """Thinking parcial durante stream (antes do flush final)."""
        if self._last_thinking:
            return self._last_thinking
        if self._thinking_parts:
            merged = "".join(self._thinking_parts).strip()
            return merged or None
        return None

    def clear_thinking(self) -> None:
        self._last_thinking = None
        self._thinking_parts = []

    def _flush_thinking_parts(self) -> None:
        if self._thinking_parts:
            merged = "".join(self._thinking_parts).strip()
            if merged:
                self._last_thinking = merged

    def _note_response(self, resp: ChatResponse) -> None:
        delta = _thinking_delta(resp)
        if delta:
            self._thinking_parts.append(delta)
        extracted = extract_thinking_from_chat_response(resp)
        if extracted:
            self._last_thinking = extracted

    @llm_chat_callback()
    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        self.clear_thinking()
        resp = self.llm.chat(messages, **kwargs)
        self._note_response(resp)
        self._flush_thinking_parts()
        return resp

    @llm_chat_callback()
    async def achat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponse:
        self.clear_thinking()
        resp = await self.llm.achat(messages, **kwargs)
        self._note_response(resp)
        self._flush_thinking_parts()
        return resp

    @llm_chat_callback()
    def stream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseGen:
        self.clear_thinking()

        def gen() -> ChatResponseGen:
            for resp in self.llm.stream_chat(messages, **kwargs):
                self._note_response(resp)
                yield resp
            self._flush_thinking_parts()

        return gen()

    @llm_chat_callback()
    async def astream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseAsyncGen:
        self.clear_thinking()

        async def gen() -> ChatResponseAsyncGen:
            async for resp in self.llm.astream_chat(messages, **kwargs):
                self._note_response(resp)
                yield resp
            self._flush_thinking_parts()

        return gen()

    @llm_completion_callback()
    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        return self.llm.complete(prompt, formatted=formatted, **kwargs)

    @llm_completion_callback()
    async def acomplete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        return await self.llm.acomplete(prompt, formatted=formatted, **kwargs)

    @llm_completion_callback()
    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseGen:
        return self.llm.stream_complete(prompt, formatted=formatted, **kwargs)

    @llm_completion_callback()
    async def astream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseAsyncGen:
        return await self.llm.astream_complete(prompt, formatted=formatted, **kwargs)


def get_live_thinking(llm: Any) -> str | None:
    if isinstance(llm, ThinkingCaptureLLM):
        return llm.live_thinking
    return None


def get_captured_thinking(llm: Any) -> str | None:
    if isinstance(llm, ThinkingCaptureLLM):
        return llm.live_thinking or llm.last_thinking
    return None


def clear_captured_thinking(llm: Any) -> None:
    if isinstance(llm, ThinkingCaptureLLM):
        llm.clear_thinking()
