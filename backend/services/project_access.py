"""Controle de acesso por dono do projeto (owner_id)."""

from __future__ import annotations

from fastapi import HTTPException

from core.bootstrap import bootstrap_legacy


def get_store():
    bootstrap_legacy()
    from project_store import ProjectStore, apply_project_settings
    from runtime_config import configure_runtime_env

    settings = configure_runtime_env()
    store = ProjectStore(settings.projects_registry_path)
    return store, settings, apply_project_settings


def list_projects_for_user(username: str):
    store, _, _ = get_store()
    return store.list_projects(owner_id=username)


def require_project(username: str, project_id: str):
    """Retorna (store, project, settings) se o utilizador for o dono."""
    store, settings, apply_fn = get_store()
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(404, "Projeto nao encontrado")
    owner = (username or "").strip().lower()
    if (project.owner_id or "").strip().lower() != owner:
        raise HTTPException(404, "Projeto nao encontrado")
    return store, project, apply_fn(settings, project)
