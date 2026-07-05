"""Inicializa paths e imports do motor core."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_LEGACY_ROOT: Path | None = None


def legacy_root() -> Path:
    if _LEGACY_ROOT is None:
        raise RuntimeError("bootstrap_legacy() nao foi chamado")
    return _LEGACY_ROOT


def bootstrap_legacy() -> Path:
    global _LEGACY_ROOT
    if _LEGACY_ROOT is not None:
        return _LEGACY_ROOT

    backend_dir = Path(__file__).resolve().parents[1]
    raw = os.environ.get("PDF_EXTREME_AI_ROOT", "").strip()
    if raw:
        root = Path(raw).expanduser()
        if not root.is_absolute():
            root = (backend_dir.parent / raw).resolve()
    else:
        root = backend_dir.parent.resolve()

    core = root / "core"
    if not (core / "runtime_config.py").exists():
        raise FileNotFoundError(
            f"PDF_EXTREME_AI_ROOT invalido: {root} (core/runtime_config.py nao encontrado)"
        )

    _LEGACY_ROOT = root
    os.chdir(root)
    for entry in (str(core), str(root)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=False)
    except ImportError:
        pass

    import http_proxy_bootstrap  # noqa: F401

    import llama_index_stream_queue_patch

    llama_index_stream_queue_patch.apply()

    return root
