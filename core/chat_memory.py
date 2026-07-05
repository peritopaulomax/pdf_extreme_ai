"""Reidrata Memory do LlamaIndex a partir de mensagens salvas na UI."""

from __future__ import annotations

from typing import Any

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.memory import Memory


def _messages_to_batch(messages: list[dict[str, Any]]) -> list[ChatMessage]:
    batch: list[ChatMessage] = []
    for msg in messages:
        role = str(msg.get("role", "")).strip().lower()
        content = str(msg.get("content", "") or "").strip()
        if not content:
            continue
        if role == "user":
            batch.append(ChatMessage(content=content, role=MessageRole.USER))
        elif role == "assistant":
            batch.append(ChatMessage(content=content, role=MessageRole.ASSISTANT))
    return batch


def rehydrate_memory_from_messages(
    memory: Memory,
    messages: list[dict[str, Any]],
    *,
    settings=None,
    llm=None,
) -> int:
    """Carrega user/assistant na Memory; retorna quantidade de mensagens inseridas."""
    payload = list(messages)
    if settings is not None and getattr(settings, "chat_memory_summarize_enabled", True):
        from conversation_memory import compress_messages_for_memory

        payload = compress_messages_for_memory(
            payload,
            recent_turns=getattr(settings, "chat_memory_recent_turns", 6),
            summarize_threshold_turns=getattr(settings, "chat_memory_summarize_threshold_turns", 8),
            llm=llm,
        )

    batch = _messages_to_batch(payload)
    memory.reset()
    if batch:
        memory.set(batch)
    return len(batch)


def memory_is_empty(memory: Memory) -> bool:
    try:
        return len(memory.get_all()) == 0
    except Exception:
        return True


def sync_memory_with_session(
    memory: Memory,
    messages: list[dict[str, Any]],
    *,
    settings=None,
    llm=None,
) -> bool:
    """Se a memoria esta vazia e ha mensagens na sessao, reidrata."""
    if not messages:
        return False
    if not memory_is_empty(memory):
        return False
    rehydrate_memory_from_messages(memory, messages, settings=settings, llm=llm)
    return True
