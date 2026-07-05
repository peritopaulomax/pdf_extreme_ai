"""Persistência de turnos de chat (checkpoints em conversation JSON)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import conversation_store as conv_store

_CHECKPOINT_DEBOUNCE_S = 1.0
_last_checkpoint_at: dict[str, float] = {}


def _now_iso() -> str:
    return conv_store._now_iso()


def new_turn_id() -> str:
    return f"t_{uuid.uuid4().hex}"


def _assistant_for_turn(messages: list[dict[str, Any]], turn_id: str) -> dict[str, Any] | None:
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("turn_id") == turn_id:
            return msg
    return None


def get_turn_snapshot(
    project_id: str,
    conversation_id: str,
    turn_id: str,
) -> dict[str, Any] | None:
    rec = conv_store.load(project_id, conversation_id)
    if rec is None:
        return None
    assistant = _assistant_for_turn(rec.messages, turn_id)
    if assistant is None:
        return None
    return {
        "assistant_text": str(assistant.get("content") or ""),
        "thinking": assistant.get("thinking"),
        "status": assistant.get("status", "running"),
        "updated_at": assistant.get("updated_at"),
        "error": assistant.get("error"),
    }


@dataclass
class TurnBeginResult:
    turn_id: str
    conversation_id: str


def begin_turn(
    *,
    project_id: str,
    conversation_id: str | None,
    user_content: str,
    model_name: str = "",
    title_if_new: str = "Nova conversa",
) -> TurnBeginResult:
    rec = None
    if conversation_id:
        rec = conv_store.load(project_id, conversation_id)
    if rec is None:
        rec = conv_store.create(project_id, title=title_if_new, model_name=model_name)

    if rec.active_turn_id:
        cancel_turn(
            project_id=project_id,
            conversation_id=rec.conversation_id,
            turn_id=rec.active_turn_id,
            reason="Substituido por novo turno",
        )
        rec = conv_store.load(project_id, rec.conversation_id)
        assert rec is not None

    turn_id = new_turn_id()
    now = _now_iso()
    messages = list(rec.messages or [])
    messages.append(
        {
            "role": "user",
            "content": user_content,
            "turn_id": turn_id,
            "created_at": now,
        }
    )
    messages.append(
        {
            "role": "assistant",
            "content": "",
            "thinking": "",
            "turn_id": turn_id,
            "status": "running",
            "updated_at": now,
            "error": None,
            "telemetry": None,
            "retrieved_chunks": [],
            "validation_issues": [],
        }
    )
    rec.messages = messages
    rec.active_turn_id = turn_id
    if model_name:
        rec.model_name = model_name
    conv_store.save(project_id, rec)
    return TurnBeginResult(turn_id=turn_id, conversation_id=rec.conversation_id)


def checkpoint_turn(
    *,
    project_id: str,
    conversation_id: str,
    turn_id: str,
    content: str | None = None,
    thinking: str | None = None,
    force: bool = False,
) -> bool:
    now = time.monotonic()
    last = _last_checkpoint_at.get(turn_id, 0.0)
    if not force and (now - last) < _CHECKPOINT_DEBOUNCE_S:
        return False

    rec = conv_store.load(project_id, conversation_id)
    if rec is None:
        return False
    assistant = _assistant_for_turn(rec.messages, turn_id)
    if assistant is None or assistant.get("status") != "running":
        return False

    if content is not None:
        assistant["content"] = content
    if thinking is not None:
        assistant["thinking"] = thinking
    assistant["updated_at"] = _now_iso()
    conv_store.save(project_id, rec)
    _last_checkpoint_at[turn_id] = now
    return True


def complete_turn(
    *,
    project_id: str,
    conversation_id: str,
    turn_id: str,
    content: str,
    thinking: str | None = None,
    telemetry: str | None = None,
    retrieved_chunks: list | None = None,
    validation_issues: list | None = None,
) -> None:
    rec = conv_store.load(project_id, conversation_id)
    if rec is None:
        return
    assistant = _assistant_for_turn(rec.messages, turn_id)
    if assistant is None:
        return
    assistant["content"] = content
    if thinking:
        assistant["thinking"] = thinking
    if telemetry:
        assistant["telemetry"] = telemetry
    if retrieved_chunks is not None:
        assistant["retrieved_chunks"] = retrieved_chunks
    if validation_issues is not None:
        assistant["validation_issues"] = validation_issues
    assistant["status"] = "completed"
    assistant["updated_at"] = _now_iso()
    assistant["error"] = None
    rec.active_turn_id = None
    conv_store.save(project_id, rec)
    _last_checkpoint_at.pop(turn_id, None)


def fail_turn(
    *,
    project_id: str,
    conversation_id: str,
    turn_id: str,
    error: str,
    content: str | None = None,
    thinking: str | None = None,
) -> None:
    rec = conv_store.load(project_id, conversation_id)
    if rec is None:
        return
    assistant = _assistant_for_turn(rec.messages, turn_id)
    if assistant is None:
        return
    if content is not None:
        assistant["content"] = content
    if thinking is not None:
        assistant["thinking"] = thinking
    assistant["status"] = "failed"
    assistant["error"] = error
    assistant["updated_at"] = _now_iso()
    rec.active_turn_id = None
    conv_store.save(project_id, rec)
    _last_checkpoint_at.pop(turn_id, None)


def cancel_turn(
    *,
    project_id: str,
    conversation_id: str,
    turn_id: str,
    reason: str = "Cancelado pelo usuario",
) -> None:
    rec = conv_store.load(project_id, conversation_id)
    if rec is None:
        return
    assistant = _assistant_for_turn(rec.messages, turn_id)
    if assistant is None:
        return
    if assistant.get("status") == "running":
        assistant["status"] = "cancelled"
        assistant["error"] = reason
        assistant["updated_at"] = _now_iso()
    if rec.active_turn_id == turn_id:
        rec.active_turn_id = None
    conv_store.save(project_id, rec)
    _last_checkpoint_at.pop(turn_id, None)


def mark_orphan_running_as_failed(project_id: str, conversation_id: str) -> None:
    rec = conv_store.load(project_id, conversation_id)
    if rec is None or not rec.active_turn_id:
        return
    turn_id = rec.active_turn_id
    assistant = _assistant_for_turn(rec.messages, turn_id)
    if assistant is not None and str(assistant.get("content") or "").strip():
        assistant["status"] = "completed"
        assistant["error"] = "Interrompido pelo servidor; resposta parcial preservada"
        assistant["updated_at"] = _now_iso()
        issues = list(assistant.get("validation_issues") or [])
        warning = "Interrompido pelo servidor; resposta parcial preservada."
        if warning not in issues:
            issues.append(warning)
        assistant["validation_issues"] = issues
        rec.active_turn_id = None
        conv_store.save(project_id, rec)
        _last_checkpoint_at.pop(turn_id, None)
        return
    fail_turn(
        project_id=project_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        error="Interrompido pelo servidor",
    )
