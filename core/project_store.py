from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from dataclasses import replace as dc_replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import paths
from runtime_config import RuntimeSettings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug or "projeto"


@dataclass
class ProjectRecord:
    project_id: str
    name: str
    created_at: str
    updated_at: str
    qdrant_collection: str
    lexical_db_path: str
    checkpoint_path: str
    global_rules: str = ""
    documents: list[dict[str, Any]] = field(default_factory=list)
    owner_id: str = ""


def _normalize_owner(username: str) -> str:
    return (username or "").strip().lower()


def _record_from_dict(p: dict[str, Any]) -> ProjectRecord:
    return ProjectRecord(
        project_id=str(p.get("project_id", "")),
        name=str(p.get("name", "")),
        created_at=str(p.get("created_at", "")),
        updated_at=str(p.get("updated_at", "")),
        qdrant_collection=str(p.get("qdrant_collection", "")),
        lexical_db_path=str(p.get("lexical_db_path", "")),
        checkpoint_path=str(p.get("checkpoint_path", "")),
        global_rules=str(p.get("global_rules", "")),
        documents=list(p.get("documents") or []),
        owner_id=_normalize_owner(str(p.get("owner_id", ""))),
    )


class ProjectStore:
    def __init__(self, registry_path: str) -> None:
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = Path(str(self.registry_path) + ".lock")
        self._thread_lock = threading.Lock()
        if not self.registry_path.exists():
            self._save({"projects": []})

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._thread_lock:
            # lock de processo para concorrencia entre workers/uvicorn
            with self._lock_path.open("a", encoding="utf-8") as lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load(self) -> dict[str, Any]:
        with self._lock():
            with self.registry_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        if "projects" not in data or not isinstance(data["projects"], list):
            data = {"projects": []}
        return data

    def _save(self, data: dict[str, Any]) -> None:
        with self._lock():
            tmp_path = self.registry_path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=True, indent=2)
            os.replace(tmp_path, self.registry_path)

    def list_projects(self, owner_id: str | None = None) -> list[ProjectRecord]:
        data = self._load()
        records = [_record_from_dict(p) for p in data["projects"]]
        if owner_id is not None:
            owner = _normalize_owner(owner_id)
            records = [p for p in records if p.owner_id == owner]
        return records

    def get_project(self, project_id: str) -> ProjectRecord | None:
        for p in self.list_projects():
            if p.project_id == project_id:
                return p
        return None

    def delete_project(self, project_id: str) -> ProjectRecord:
        data = self._load()
        for idx, item in enumerate(data["projects"]):
            if item["project_id"] == project_id:
                removed = _record_from_dict(data["projects"].pop(idx))
                self._save(data)
                return removed
        raise RuntimeError(f"Projeto nao encontrado: {project_id}")

    def create_project(self, name: str, owner_id: str = "") -> ProjectRecord:
        data = self._load()
        existing_ids = {p["project_id"] for p in data["projects"]}
        base = _slugify(name)
        project_id = base
        suffix = 2
        while project_id in existing_ids:
            project_id = f"{base}-{suffix}"
            suffix += 1
        now = _now_iso()
        collection = f"proj_{project_id.replace('-', '_')}"
        lexical_db = paths.lexical_db_for_project(project_id)
        checkpoint = paths.checkpoint_for_project(project_id)
        uploads_dir = str(paths.project_uploads_dir(project_id))
        project = ProjectRecord(
            project_id=project_id,
            name=name.strip() or project_id,
            created_at=now,
            updated_at=now,
            qdrant_collection=collection,
            lexical_db_path=lexical_db,
            checkpoint_path=checkpoint,
            documents=[],
            owner_id=_normalize_owner(owner_id),
        )
        data["projects"].append(asdict(project))
        self._save(data)
        Path(uploads_dir).mkdir(parents=True, exist_ok=True)
        return project

    def update_project(self, project: ProjectRecord) -> None:
        data = self._load()
        for idx, item in enumerate(data["projects"]):
            if item["project_id"] == project.project_id:
                project.updated_at = _now_iso()
                data["projects"][idx] = asdict(project)
                self._save(data)
                return
        raise RuntimeError(f"Projeto nao encontrado: {project.project_id}")

    def rename_project(self, project_id: str, name: str) -> ProjectRecord:
        project = self.get_project(project_id)
        if project is None:
            raise RuntimeError(f"Projeto nao encontrado: {project_id}")
        project.name = (name or "").strip() or project.project_id
        self.update_project(project)
        return project

    def set_global_rules(self, project_id: str, rules: str) -> ProjectRecord:
        project = self.get_project(project_id)
        if project is None:
            raise RuntimeError(f"Projeto nao encontrado: {project_id}")
        project.global_rules = (rules or "").strip()[:4000]
        self.update_project(project)
        return project

    def add_documents(self, project_id: str, doc_entries: list[dict[str, Any]]) -> ProjectRecord:
        project = self.get_project(project_id)
        if project is None:
            raise RuntimeError(f"Projeto nao encontrado: {project_id}")
        existing = {str(d.get("file_id", "")): d for d in project.documents}
        for item in doc_entries:
            fid = str(item.get("file_id", "")).strip()
            if not fid:
                continue
            old = existing.get(fid, {})
            merged = {**old, **item}
            merged.setdefault("created_at", _now_iso())
            merged["updated_at"] = _now_iso()
            existing[fid] = merged
        project.documents = sorted(
            list(existing.values()),
            key=lambda d: str(d.get("updated_at", "")),
            reverse=True,
        )
        self.update_project(project)
        return project

    def remove_documents(self, project_id: str, file_ids: list[str]) -> ProjectRecord:
        project = self.get_project(project_id)
        if project is None:
            raise RuntimeError(f"Projeto nao encontrado: {project_id}")
        remove_set = {str(fid) for fid in file_ids}
        project.documents = [d for d in project.documents if str(d.get("file_id", "")) not in remove_set]
        self.update_project(project)
        return project

    def get_documents(self, project_id: str) -> list[dict[str, Any]]:
        project = self.get_project(project_id)
        if project is None:
            return []
        return list(project.documents)


def project_uploads_dir(project_id: str) -> Path:
    return paths.project_uploads_dir(project_id)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def apply_project_settings(settings: RuntimeSettings, project: ProjectRecord) -> RuntimeSettings:
    return dc_replace(
        settings,
        qdrant_collection=project.qdrant_collection,
        lexical_db_path=project.lexical_db_path,
        checkpoint_path=project.checkpoint_path,
    )
