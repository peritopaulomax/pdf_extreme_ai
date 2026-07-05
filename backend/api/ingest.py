from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from auth.dependencies import require_auth
from services.documents_service import validate_upload_batch
from services.ingest_runner import run_ingest_job, stream_ingest_sse
from services.project_access import require_project

router = APIRouter(prefix="/projects/{project_id}/ingest", tags=["ingest"])


def _project_for_user(username: str, project_id: str):
    from project_store import file_sha256, project_uploads_dir

    store, project, settings = require_project(username, project_id)
    return store, project, settings, project_uploads_dir, file_sha256


def persist_uploads(project, files: list[UploadFile], file_sha256_fn, uploads_dir_fn):
    upload_dir = uploads_dir_fn(project.project_id)
    existing = project.documents
    by_hash = {(d.get("sha256"), d.get("display_name")): d for d in existing}
    paths: list[Path] = []
    entries: list[dict] = []
    skipped: list[str] = []
    for up in files:
        suffix = Path(up.filename or "file.pdf").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            payload = up.file.read()
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        digest = file_sha256_fn(tmp_path)
        name = up.filename or "upload.pdf"
        key = (digest, name)
        if key in by_hash:
            skipped.append(name)
            tmp_path.unlink(missing_ok=True)
            continue
        file_id = hashlib.sha1(f"{name}:{digest}".encode("utf-8")).hexdigest()[:16]
        stored_name = f"{file_id}_{name}"
        dest = upload_dir / stored_name
        if dest.exists():
            dest.unlink(missing_ok=True)
        tmp_path.replace(dest)
        size_mb = round(len(payload) / (1024 * 1024), 3)
        paths.append(dest)
        entries.append(
            {
                "file_id": file_id,
                "display_name": name,
                "storage_name": stored_name,
                "path": str(dest),
                "sha256": digest,
                "size_mb": size_mb,
                "status": "pending",
            }
        )
    return paths, entries, skipped


@router.post("")
async def ingest_pdfs(
    project_id: str,
    files: Annotated[list[UploadFile], File(...)],
    rebuild: bool = Query(False),
    reprocess_all: bool = Query(True),
    force_ocr: bool = Query(False),
    user: dict = Depends(require_auth),
):
    store, project, settings, project_uploads_dir, file_sha256_fn = _project_for_user(
        user["usuario"], project_id
    )
    if not files:
        raise HTTPException(400, "Envie ao menos um arquivo PDF")
    validate_upload_batch(files, settings)

    paths, entries, skipped = persist_uploads(
        project, files, file_sha256_fn, project_uploads_dir
    )
    if not paths:
        return {"skipped": skipped, "message": "Nenhum arquivo novo para ingerir"}

    summary = run_ingest_job(
        settings=settings,
        store=store,
        project_id=project_id,
        paths=paths,
        entries=entries,
        rebuild=rebuild,
        reprocess_all=reprocess_all,
        force_ocr=force_ocr,
    )
    summary["skipped"] = skipped
    return summary


@router.post("/stream")
async def ingest_pdfs_stream(
    project_id: str,
    files: Annotated[list[UploadFile], File(...)],
    rebuild: bool = Query(False),
    reprocess_all: bool = Query(True),
    force_ocr: bool = Query(False),
    user: dict = Depends(require_auth),
):
    """SSE: eventos progress (percent, message) e done (resumo + per_file)."""
    store, project, settings, project_uploads_dir, file_sha256_fn = _project_for_user(
        user["usuario"], project_id
    )
    if not files:
        raise HTTPException(400, "Envie ao menos um arquivo PDF")
    validate_upload_batch(files, settings)

    paths, entries, skipped = persist_uploads(
        project, files, file_sha256_fn, project_uploads_dir
    )
    if not paths:
        from services.sse import format_sse

        def empty_done():
            yield format_sse(
                "done",
                {"message": "Nenhum arquivo novo", "skipped": skipped, "per_file": []},
            )

        return StreamingResponse(empty_done(), media_type="text/event-stream")

    return StreamingResponse(
        _stream_with_skipped(
            settings,
            store,
            project_id,
            paths,
            entries,
            rebuild,
            reprocess_all,
            force_ocr,
            skipped,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_with_skipped(
    settings, store, project_id, paths, entries, rebuild, reprocess_all, force_ocr, skipped
):
    from services.sse import format_sse

    if skipped:
        yield format_sse(
            "status", {"message": f"Ignorados (duplicados): {', '.join(skipped)}"}
        )
    yield from stream_ingest_sse(
        settings=settings,
        store=store,
        project_id=project_id,
        paths=paths,
        entries=entries,
        rebuild=rebuild,
        reprocess_all=reprocess_all,
        force_ocr=force_ocr,
    )
