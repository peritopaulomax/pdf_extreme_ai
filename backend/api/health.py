from __future__ import annotations

from fastapi import APIRouter

from core.bootstrap import bootstrap_legacy, legacy_root

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    root = bootstrap_legacy()
    return {
        "status": "ok",
        "legacy_root": str(legacy_root()),
        "core_exists": (root / "core" / "runtime_config.py").exists(),
        "app_exists": (root / "legacy" / "app.py").exists(),
    }
