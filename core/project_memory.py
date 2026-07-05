"""Memoria editavel do caso por projeto (markdown + JSON estruturado opcional)."""

from __future__ import annotations

import json
from pathlib import Path


import paths


def path_for(project_id: str) -> Path:
    base = paths.project_dir(project_id)
    base.mkdir(parents=True, exist_ok=True)
    return base / "project_memory.md"


def structured_path_for(project_id: str) -> Path:
    base = paths.project_dir(project_id)
    base.mkdir(parents=True, exist_ok=True)
    return base / "project_memory.json"


def load_structured(project_id: str) -> dict:
    p = structured_path_for(project_id)
    if not p.is_file():
        return {"events": [], "parties": [], "notes": ""}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"events": [], "parties": [], "notes": ""}
        return {
            "events": list(data.get("events") or []),
            "parties": list(data.get("parties") or []),
            "notes": str(data.get("notes") or ""),
        }
    except Exception:
        return {"events": [], "parties": [], "notes": ""}


def save_structured(project_id: str, data: dict) -> None:
    payload = {
        "events": list((data or {}).get("events") or []),
        "parties": list((data or {}).get("parties") or []),
        "notes": str((data or {}).get("notes") or ""),
    }
    structured_path_for(project_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _structured_summary(data: dict) -> str:
    parts: list[str] = []
    parties = data.get("parties") or []
    if parties:
        parts.append("Partes: " + "; ".join(str(p) for p in parties[:12]))
    events = data.get("events") or []
    if events:
        parts.append("Eventos: " + "; ".join(str(e) for e in events[:12]))
    notes = str(data.get("notes") or "").strip()
    if notes:
        parts.append("Notas: " + notes[:500])
    return "\n".join(parts)


def load(project_id: str) -> str:
    p = path_for(project_id)
    md = ""
    if p.is_file():
        try:
            md = p.read_text(encoding="utf-8").strip()
        except Exception:
            md = ""
    struct = _structured_summary(load_structured(project_id))
    if struct and md:
        return f"{md}\n\n{struct}"
    return md or struct


def save(project_id: str, text: str) -> None:
    p = path_for(project_id)
    content = (text or "").strip()
    if content:
        p.write_text(content + "\n", encoding="utf-8")
    elif p.is_file():
        p.unlink(missing_ok=True)
