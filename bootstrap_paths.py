"""Configura sys.path e cwd para entry points do projeto."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORE = ROOT / "core"


def project_root() -> Path:
    raw = os.environ.get("PDF_EXTREME_AI_ROOT", "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        return p
    return ROOT


def setup() -> Path:
    root = project_root()
    os.chdir(root)
    core = root / "core"
    for entry in (str(core), str(root)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    return root
