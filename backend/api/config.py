from __future__ import annotations

from fastapi import APIRouter

from core.bootstrap import bootstrap_legacy

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
def get_config():
    bootstrap_legacy()
    from runtime_config import configure_runtime_env

    s = configure_runtime_env()
    return {
        "llm_models": s.llm_models,
        "llm_default_model": s.llm_default_model,
        "ui_ingest_max_files": s.ui_ingest_max_files,
        "ui_ingest_max_file_mb": s.ui_ingest_max_file_mb,
        "ingest_quality_warn_threshold": s.ingest_quality_warn_threshold,
    }
