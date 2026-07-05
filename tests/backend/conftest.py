from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
ROOT = BACKEND.parent
CORE = ROOT / "core"
AUTH_DIR = Path(tempfile.mkdtemp(prefix="pdf_auth_"))
REGISTRY_DIR = Path(tempfile.mkdtemp(prefix="pdf_registry_"))
DATA_DIR = Path(tempfile.mkdtemp(prefix="pdf_data_"))

os.environ.setdefault("PDF_EXTREME_AI_ROOT", str(ROOT))
os.environ.setdefault("DATA_DIR", str(DATA_DIR))
os.environ.setdefault("AUTH_DATA_DIR", str(AUTH_DIR))
os.environ.setdefault("SESSION_SECRET", "pdf-extreme-tests")
os.environ.setdefault("PROJECTS_REGISTRY_PATH", str(REGISTRY_DIR / "projects_registry.json"))

for entry in (str(BACKEND), str(CORE), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)


@pytest.fixture(autouse=True)
def _reset_backend_test_state():
    auth_dir = Path(os.environ["AUTH_DATA_DIR"])
    registry_path = Path(os.environ["PROJECTS_REGISTRY_PATH"])

    auth_dir.mkdir(parents=True, exist_ok=True)
    for entry in auth_dir.iterdir():
        if entry.is_file():
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)

    if registry_path.exists():
        registry_path.unlink()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    yield
