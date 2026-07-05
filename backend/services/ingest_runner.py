"""Execução de ingest com callback de progresso (SSE)."""

from __future__ import annotations

import os
import queue
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterator

from core.bootstrap import bootstrap_legacy
from services.sse import format_sse
from services.stack_manager import invalidate_stack_cache


ProgressCallback = Callable[[dict], None]


def run_ingest_job(
    *,
    settings,
    store,
    project_id: str,
    paths: list[Path],
    entries: list[dict],
    rebuild: bool,
    reprocess_all: bool,
    force_ocr: bool,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    bootstrap_legacy()
    from ingest_service import release_ingest_models, run_ingest
    from gpu_runtime import release_cuda_cache

    prev_ocr = os.environ.get("ENABLE_OCR", "")
    if force_ocr:
        os.environ["ENABLE_OCR"] = "true"
    try:
        result = run_ingest(
            settings=settings,
            input_files=paths,
            rebuild=rebuild,
            reprocess_all=reprocess_all,
            update_checkpoint=True,
            progress_callback=progress,
            project_id=project_id,
        )
    finally:
        if force_ocr:
            if prev_ocr:
                os.environ["ENABLE_OCR"] = prev_ocr
            else:
                os.environ.pop("ENABLE_OCR", None)

    by_source = {item.get("source_file"): item for item in result.per_file}
    for entry in entries:
        source = entry.get("storage_name", "")
        if source in by_source:
            info = by_source[source]
            entry["status"] = info.get("status", "indexed")
            entry["pages"] = int(info.get("pages", 0) or 0)
            entry["chunks"] = int(info.get("chunks", 0) or 0)
        else:
            entry["status"] = "indexed"
    if entries:
        store.add_documents(project_id, entries)

    release_ingest_models()
    invalidate_stack_cache()
    release_cuda_cache()

    return {
        "files_processed": result.files_processed,
        "files_total": result.files_total,
        "total_pages": result.total_pages,
        "total_chunks": result.total_chunks,
        "elapsed_s": result.elapsed_s,
        "errors": result.errors,
        "per_file": result.per_file,
    }


def stream_ingest_sse(
    *,
    settings,
    store,
    project_id: str,
    paths: list[Path],
    entries: list[dict],
    rebuild: bool,
    reprocess_all: bool,
    force_ocr: bool,
) -> Iterator[str]:
    q: queue.Queue = queue.Queue()
    logs: list[str] = []

    def _progress(event: dict) -> None:
        q.put(("progress", event))
        msg = str(event.get("message", event.get("stage", "")))
        if msg:
            logs.append(msg)

    def _worker() -> None:
        try:
            summary = run_ingest_job(
                settings=settings,
                store=store,
                project_id=project_id,
                paths=paths,
                entries=entries,
                rebuild=rebuild,
                reprocess_all=reprocess_all,
                force_ocr=force_ocr,
                progress=_progress,
            )
            summary["logs"] = logs[-80:]
            q.put(("done", summary))
        except Exception as exc:
            q.put(("error", str(exc)))

    threading.Thread(target=_worker, daemon=True).start()

    while True:
        kind, payload = q.get()
        if kind == "progress":
            ev = payload
            current = int(ev.get("current", 0) or 0)
            total = int(ev.get("total", 0) or 0)
            percent = min(100.0, (current / total) * 100.0) if total > 0 else None
            yield format_sse(
                "progress",
                {
                    "stage": ev.get("stage", ""),
                    "message": ev.get("message", ""),
                    "current": current,
                    "total": total,
                    "percent": percent,
                    "file": ev.get("file", ""),
                },
            )
        elif kind == "done":
            yield format_sse("done", payload)
            break
        elif kind == "error":
            yield format_sse("error", {"message": payload})
            break
