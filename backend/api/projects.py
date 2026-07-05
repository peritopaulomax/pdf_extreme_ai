from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import ProjectCreate, ProjectRename
from auth.dependencies import require_auth
from services.project_access import list_projects_for_user, require_project
from services.project_cleanup import cleanup_project_assets, delete_project_from_registry

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(user: dict = Depends(require_auth)):
    projects = list_projects_for_user(user["usuario"])
    return {"projects": [asdict(p) for p in projects]}


@router.post("")
def create_project(body: ProjectCreate, user: dict = Depends(require_auth)):
    from services.project_access import get_store

    store, _, _ = get_store()
    if not body.name.strip():
        raise HTTPException(400, "Nome do projeto obrigatorio")
    project = store.create_project(body.name.strip(), owner_id=user["usuario"])
    return asdict(project)


@router.get("/{project_id}")
def get_project(project_id: str, user: dict = Depends(require_auth)):
    _, project, _ = require_project(user["usuario"], project_id)
    return asdict(project)


@router.patch("/{project_id}")
def rename_project(
    project_id: str,
    body: ProjectRename,
    user: dict = Depends(require_auth),
):
    store, _, _ = require_project(user["usuario"], project_id)
    if not body.name.strip():
        raise HTTPException(400, "Nome do projeto obrigatorio")
    updated = store.rename_project(project_id, body.name.strip())
    return asdict(updated)


@router.delete("/{project_id}")
def delete_project(project_id: str, user: dict = Depends(require_auth)):
    store, project, settings = require_project(user["usuario"], project_id)
    try:
        removed = delete_project_from_registry(store, project_id)
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc
    cleanup = cleanup_project_assets(settings, removed)
    return {"removed": asdict(removed), "cleanup": cleanup}
