"""Coordenacao de GPU/VRAM entre ingestao e chat (processo Streamlit unico)."""

from __future__ import annotations

import threading
from contextlib import contextmanager

import torch

_gpu_lock = threading.Lock()
_ingest_active = threading.Event()


def is_ingest_active() -> bool:
    return _ingest_active.is_set()


def release_cuda_cache() -> None:
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


@contextmanager
def ingest_gpu_slot():
    """Exclusao mutua: ingestao bloqueia outra ingest e sinaliza chat."""
    acquired = _gpu_lock.acquire(blocking=True, timeout=3600)
    if not acquired:
        raise RuntimeError("Timeout aguardando slot de GPU para ingestao.")
    _ingest_active.set()
    try:
        yield
    finally:
        _ingest_active.clear()
        _gpu_lock.release()


def chat_gpu_available() -> bool:
    """Chat pode rodar quando nenhuma ingestao global esta ativa."""
    return not _ingest_active.is_set()
