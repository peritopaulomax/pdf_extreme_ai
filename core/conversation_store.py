from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


import paths


def conversations_dir(project_id: str) -> Path:
    return paths.conversations_dir(project_id)


def _safe_filename(conversation_id: str) -> str:
    cid = re.sub(r"[^a-zA-Z0-9_-]+", "", conversation_id.strip())
    return cid or "conv"


@dataclass
class ConversationRecord:
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[dict[str, Any]]
    model_name: str = ""
    active_turn_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("active_turn_id") is None:
            data.pop("active_turn_id", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationRecord:
        active = data.get("active_turn_id")
        return cls(
            conversation_id=str(data.get("conversation_id", "")),
            title=str(data.get("title", "Conversa")),
            created_at=str(data.get("created_at", _now_iso())),
            updated_at=str(data.get("updated_at", _now_iso())),
            messages=list(data.get("messages") or []),
            model_name=str(data.get("model_name", "")),
            active_turn_id=str(active) if active else None,
        )


def _path_for(project_id: str, conversation_id: str) -> Path:
    return conversations_dir(project_id) / f"{_safe_filename(conversation_id)}.json"


def list_conversations(project_id: str) -> list[ConversationRecord]:
    root = conversations_dir(project_id)
    out: list[ConversationRecord] = []
    for p in sorted(root.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(ConversationRecord.from_dict(data))
        except Exception:
            continue
    return out


def create(project_id: str, title: str = "Nova conversa", model_name: str = "") -> ConversationRecord:
    cid = uuid.uuid4().hex
    now = _now_iso()
    rec = ConversationRecord(
        conversation_id=cid,
        title=title.strip() or "Nova conversa",
        created_at=now,
        updated_at=now,
        messages=[],
        model_name=model_name or "",
    )
    save(project_id, rec)
    return rec


def load(project_id: str, conversation_id: str) -> ConversationRecord | None:
    path = _path_for(project_id, conversation_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ConversationRecord.from_dict(data)
    except Exception:
        return None


def save(project_id: str, record: ConversationRecord) -> None:
    record.updated_at = _now_iso()
    path = _path_for(project_id, record.conversation_id)
    payload = json.dumps(record.to_dict(), ensure_ascii=True, indent=2)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def rename(project_id: str, conversation_id: str, new_title: str) -> ConversationRecord | None:
    rec = load(project_id, conversation_id)
    if rec is None:
        return None
    rec.title = (new_title or "").strip() or rec.title
    save(project_id, rec)
    return rec


def delete(project_id: str, conversation_id: str) -> bool:
    path = _path_for(project_id, conversation_id)
    if path.exists():
        path.unlink(missing_ok=True)
        return True
    return False
