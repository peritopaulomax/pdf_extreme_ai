from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
for entry in (str(CORE), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import bootstrap_paths

bootstrap_paths.setup()
