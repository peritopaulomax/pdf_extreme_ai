"""Chat livre: SimpleChatEngine sem RAG nem sintese de contexto vazio."""

from __future__ import annotations

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.chat_engine import SimpleChatEngine
from llama_index.core.memory import Memory

from rag_prompts import build_free_chat_system_prompt


def build_free_chat_engines(
    capture_llm,
    memory: Memory,
    session_rules: str,
    project_memory: str = "",
) -> tuple[SimpleChatEngine, SimpleChatEngine]:
    system = build_free_chat_system_prompt(session_rules, project_memory or None)
    prefix = [ChatMessage(role=MessageRole.SYSTEM, content=system)]
    engine = SimpleChatEngine.from_defaults(
        llm=capture_llm,
        memory=memory,
        prefix_messages=prefix,
    )
    return engine, engine
