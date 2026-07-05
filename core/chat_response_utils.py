"""Extracao robusta de texto da resposta do chat (evita 'Empty Response')."""

from __future__ import annotations

import time
from typing import Any

from llama_index.core.base.llms.types import TextBlock, ThinkingBlock


_EMPTY_MARKERS = frozenset({"", "empty response"})


def is_empty_llm_output(text: str | None) -> bool:
    t = (text or "").strip()
    return not t or t.lower() in _EMPTY_MARKERS


def assign_assistant_text_to_message(message: Any, final_text: str) -> None:
    """Atualiza texto da resposta sem quebrar blocos de thinking (multi-block)."""
    text = (final_text or "").strip()
    blocks = list(getattr(message, "blocks", None) or [])
    if not blocks:
        if text:
            message.blocks = [TextBlock(text=text)]
        return

    new_blocks: list = []
    text_written = False
    for block in blocks:
        if isinstance(block, ThinkingBlock):
            new_blocks.append(block)
        elif isinstance(block, TextBlock):
            if not text_written:
                new_blocks.append(TextBlock(text=text))
                text_written = True
        else:
            new_blocks.append(block)
    if not text_written and text:
        new_blocks.append(TextBlock(text=text))
    message.blocks = new_blocks


def message_text(message: Any) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()
    parts: list[str] = []
    for block in getattr(message, "blocks", None) or []:
        if isinstance(block, TextBlock):
            t = (block.text or "").strip()
            if t:
                parts.append(t)
    return "".join(parts).strip()


def text_from_streaming_response(stream_resp: Any) -> str:
    for attr in ("response", "unformatted_response"):
        val = getattr(stream_resp, attr, None)
        if val is not None and not is_empty_llm_output(str(val)):
            return str(val).strip()
    return ""


def wait_stream_history_thread(stream_resp: Any, *, timeout_s: float = 300.0) -> None:
    thread = getattr(stream_resp, "write_response_to_history_thread", None)
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout_s)


def text_from_chat_engine_history(chat_engine: Any) -> str:
    hist = getattr(chat_engine, "chat_history", None) or []
    for msg in reversed(hist):
        role = str(getattr(msg, "role", "") or "").lower()
        if role in ("assistant", "chatbot", "agent"):
            t = message_text(msg)
            if t and not is_empty_llm_output(t):
                return t
    return ""


def coalesce_assistant_reply(
    streamed_text: str,
    stream_resp: Any,
    chat_engine: Any,
    *,
    wait_history: bool = True,
) -> str:
    if not is_empty_llm_output(streamed_text):
        return streamed_text.strip()
    if wait_history:
        wait_stream_history_thread(stream_resp)
    from_resp = text_from_streaming_response(stream_resp)
    if from_resp:
        return from_resp
    from_hist = text_from_chat_engine_history(chat_engine)
    if from_hist:
        return from_hist
    return streamed_text.strip()
