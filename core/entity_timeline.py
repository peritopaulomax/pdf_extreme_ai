"""Extracao leve de entidades (regex) para painel de timeline na UI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EntityHit:
    kind: str
    value: str
    source_file: str
    page: int


_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_UPPER_NAME = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{3,40}\b")


def extract_entities_from_text(
    text: str, *, source_file: str = "", page: int = 0, max_hits: int = 40
) -> list[EntityHit]:
    hits: list[EntityHit] = []
    for m in _CPF.finditer(text):
        hits.append(EntityHit("cpf", m.group(0), source_file, page))
    for m in _CNPJ.finditer(text):
        hits.append(EntityHit("cnpj", m.group(0), source_file, page))
    for m in _UPPER_NAME.finditer(text):
        val = m.group(0).strip()
        if len(val.split()) >= 2:
            hits.append(EntityHit("nome", val, source_file, page))
    return hits[:max_hits]


def entities_db_path(project_id: str) -> Path:
    import paths

    base = paths.project_dir(project_id)
    base.mkdir(parents=True, exist_ok=True)
    return base / "entities.json"


def load_entities(project_id: str) -> list[dict]:
    p = entities_db_path(project_id)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_entities(project_id: str, entities: list[dict]) -> None:
    entities_db_path(project_id).write_text(
        json.dumps(entities, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
