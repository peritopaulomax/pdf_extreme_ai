from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from api.schemas import MemoryBody, RulesBody
from auth.dependencies import require_auth
from services.project_access import require_project

router = APIRouter(prefix="/projects/{project_id}", tags=["project-settings"])


@router.get("/rules")
def get_rules(project_id: str, user: dict = Depends(require_auth)):
    _, project, _ = require_project(user["usuario"], project_id)
    return {"global_rules": project.global_rules or ""}


@router.patch("/rules")
def patch_rules(
    project_id: str,
    body: RulesBody,
    user: dict = Depends(require_auth),
):
    store, _, _ = require_project(user["usuario"], project_id)
    updated = store.set_global_rules(project_id, body.global_rules)
    return {"global_rules": updated.global_rules or ""}


@router.get("/memory")
def get_memory(project_id: str, user: dict = Depends(require_auth)):
    import project_memory as project_memory_store

    require_project(user["usuario"], project_id)
    return {"text": project_memory_store.load(project_id)}


@router.put("/memory")
def put_memory(
    project_id: str,
    body: MemoryBody,
    user: dict = Depends(require_auth),
):
    import project_memory as project_memory_store

    require_project(user["usuario"], project_id)
    project_memory_store.save(project_id, body.text)
    return {"text": project_memory_store.load(project_id)}
