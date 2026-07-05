"""Paths centralizados para dados de runtime."""

from __future__ import annotations

import os
from pathlib import Path

_LEGACY_PREFIXES = (
    ("projects_data/", "data/projects/"),
    (".lexical_", "data/lexical/"),
    (".ingest_checkpoint_", "data/checkpoints/"),
)


def _root() -> Path:
    raw = os.environ.get("PDF_EXTREME_AI_ROOT", "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[1] / p
        return p.resolve()
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    raw = os.environ.get("DATA_DIR", "data").strip() or "data"
    p = Path(raw)
    if not p.is_absolute():
        p = _root() / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def projects_dir() -> Path:
    p = data_dir() / "projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def lexical_dir() -> Path:
    p = data_dir() / "lexical"
    p.mkdir(parents=True, exist_ok=True)
    return p


def checkpoints_dir() -> Path:
    p = data_dir() / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p


def auth_dir() -> Path:
    raw = os.environ.get("AUTH_DATA_DIR", "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = _root() / p
    else:
        p = data_dir() / "auth"
    p.mkdir(parents=True, exist_ok=True)
    return p


def registry_file() -> Path:
    raw = os.environ.get("PROJECTS_REGISTRY_PATH", "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = _root() / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    p = data_dir() / "projects_registry.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def project_dir(project_id: str) -> Path:
    return projects_dir() / project_id


def project_uploads_dir(project_id: str) -> Path:
    p = project_dir(project_id) / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def conversations_dir(project_id: str) -> Path:
    p = project_dir(project_id) / "conversations"
    p.mkdir(parents=True, exist_ok=True)
    return p


def lexical_db_for_project(project_id: str) -> str:
    return str(lexical_dir() / f"{project_id}.db")


def checkpoint_for_project(project_id: str) -> str:
    return str(checkpoints_dir() / f"{project_id}.json")


def normalize_stored_path(path: str) -> str:
    """Converte paths legados (raiz) para o layout em data/."""
    if not path:
        return path
    normalized = path.replace("\\", "/")
    if normalized.startswith("data/"):
        return normalized
    for old, new in _LEGACY_PREFIXES:
        if normalized.startswith(old):
            rest = normalized[len(old) :]
            if old == ".lexical_":
                return f"data/lexical/{rest.removesuffix('.db')}.db"
            if old == ".ingest_checkpoint_":
                return f"data/checkpoints/{rest.removesuffix('.json')}.json"
            return new + rest
    if normalized.startswith("/") and "projects_data/" in normalized:
        idx = normalized.index("projects_data/")
        return "data/projects/" + normalized[idx + len("projects_data/") :]
    return normalized


def resolve_path(path: str | Path) -> Path:
    p = Path(str(path))
    if p.is_absolute():
        return p
    return _root() / p
