"""Limpeza de assets ao excluir projeto (paridade com app._cleanup_project_assets)."""

from __future__ import annotations

import shutil
from pathlib import Path

from core.bootstrap import bootstrap_legacy


def cleanup_project_assets(settings, project) -> dict:
    bootstrap_legacy()
    import paths
    from runtime_config import connect_qdrant

    removed = {
        "uploads_removed": 0,
        "lexical_removed": False,
        "checkpoint_removed": False,
        "qdrant_collection_removed": False,
    }
    for doc in list(project.documents or []):
        path_value = str(doc.get("path", "")).strip()
        if not path_value:
            continue
        p = paths.resolve_path(path_value)
        if p.exists():
            try:
                p.unlink(missing_ok=True)
                removed["uploads_removed"] += 1
            except OSError:
                pass

    project_root = paths.project_dir(project.project_id)
    if project_root.exists():
        shutil.rmtree(project_root, ignore_errors=True)

    lexical_db = paths.resolve_path(project.lexical_db_path)
    if lexical_db.exists():
        lexical_db.unlink(missing_ok=True)
        removed["lexical_removed"] = True

    checkpoint_file = paths.resolve_path(project.checkpoint_path)
    if checkpoint_file.exists():
        checkpoint_file.unlink(missing_ok=True)
        removed["checkpoint_removed"] = True

    try:
        client, _ = connect_qdrant(settings)
        if client.collection_exists(project.qdrant_collection):
            client.delete_collection(project.qdrant_collection)
            removed["qdrant_collection_removed"] = True
    except Exception:
        pass
    return removed


def delete_project_from_registry(store, project_id: str):
    """Remove projeto do registry usando a API publica do ProjectStore."""
    return store.delete_project(project_id)
