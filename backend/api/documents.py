from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.schemas import DocumentReprocessBody, DocumentSelectionBody
from auth.dependencies import require_auth
from services.documents_service import remove_docs_from_indexes
from services.ingest_runner import run_ingest_job, stream_ingest_sse
from services.project_access import require_project

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])


def _normalize_file_ids(file_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for file_id in file_ids:
        item = str(file_id or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _selected_docs(project, file_ids: list[str]) -> list[dict]:
    normalized = _normalize_file_ids(file_ids)
    if not normalized:
        raise HTTPException(400, "Selecione ao menos um documento")
    docs_by_id = {str(doc.get("file_id")): doc for doc in project.documents}
    missing = [file_id for file_id in normalized if file_id not in docs_by_id]
    if missing:
        joined = ", ".join(missing)
        raise HTTPException(404, f"Documentos nao encontrados: {joined}")
    return [docs_by_id[file_id] for file_id in normalized]


def _build_ingest_entry(doc: dict, path: Path, file_id: str, sha256: str) -> dict:
    storage_name = str(doc.get("storage_name") or path.name)
    return {
        "file_id": file_id,
        "display_name": doc.get("display_name", storage_name),
        "storage_name": storage_name,
        "sha256": doc.get("sha256") or sha256,
        "size_mb": doc.get("size_mb"),
        "status": "pending",
    }


def _prepare_reprocess_selection(project_id: str, project, file_ids: list[str]) -> tuple[list[dict], list[Path], list[dict], list[str]]:
    from project_store import file_sha256, project_uploads_dir

    docs = _selected_docs(project, file_ids)
    paths: list[Path] = []
    entries: list[dict] = []
    normalized_ids: list[str] = []
    for doc in docs:
        file_id = str(doc["file_id"])
        storage_name = str(doc.get("storage_name") or doc.get("display_name") or "")
        path = project_uploads_dir(project_id) / storage_name
        if not path.exists():
            raise HTTPException(404, f"Arquivo nao encontrado no disco: {storage_name}")
        paths.append(path)
        entries.append(_build_ingest_entry(doc, path, file_id, file_sha256(path)))
        normalized_ids.append(file_id)
    return docs, paths, entries, normalized_ids


@router.get("")
def list_documents(project_id: str, user: dict = Depends(require_auth)):
    _, project, _ = require_project(user["usuario"], project_id)
    return {"documents": list(project.documents or [])}


@router.post("/remove")
def delete_documents_selected(
    project_id: str,
    body: DocumentSelectionBody,
    user: dict = Depends(require_auth),
):
    store, project, settings = require_project(user["usuario"], project_id)
    docs = _selected_docs(project, body.file_ids)
    file_ids = [str(doc["file_id"]) for doc in docs]
    remove_docs_from_indexes(settings, docs)
    store.remove_documents(project_id, file_ids)
    return {"deleted": True, "file_ids": file_ids, "deleted_count": len(file_ids)}


@router.post("/reprocess")
def reprocess_documents_selected(
    project_id: str,
    body: DocumentReprocessBody,
    user: dict = Depends(require_auth),
):
    store, project, settings = require_project(user["usuario"], project_id)
    docs, paths, entries, file_ids = _prepare_reprocess_selection(
        project_id, project, body.file_ids
    )
    remove_docs_from_indexes(settings, docs)
    store.remove_documents(project_id, file_ids)

    summary = run_ingest_job(
        settings=settings,
        store=store,
        project_id=project_id,
        paths=paths,
        entries=entries,
        rebuild=False,
        reprocess_all=True,
        force_ocr=body.force_ocr,
    )
    summary.update({"reprocessed": True, "file_ids": file_ids, "reprocessed_count": len(file_ids)})
    return summary


@router.post("/reprocess/stream")
def reprocess_documents_selected_stream(
    project_id: str,
    body: DocumentReprocessBody,
    user: dict = Depends(require_auth),
):
    from services.sse import format_sse

    store, project, settings = require_project(user["usuario"], project_id)
    docs, paths, entries, file_ids = _prepare_reprocess_selection(
        project_id, project, body.file_ids
    )
    remove_docs_from_indexes(settings, docs)
    store.remove_documents(project_id, file_ids)

    def _stream():
        yield format_sse(
            "status",
            {"message": f"Reprocessando {len(file_ids)} arquivo(s) selecionado(s)..."},
        )
        yield from stream_ingest_sse(
            settings=settings,
            store=store,
            project_id=project_id,
            paths=paths,
            entries=entries,
            rebuild=False,
            reprocess_all=True,
            force_ocr=body.force_ocr,
        )

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{file_id}")
def delete_document(
    project_id: str,
    file_id: str,
    user: dict = Depends(require_auth),
):
    store, project, settings = require_project(user["usuario"], project_id)
    docs = [d for d in project.documents if str(d.get("file_id")) == file_id]
    if not docs:
        raise HTTPException(404, "Documento nao encontrado")
    remove_docs_from_indexes(settings, docs)
    store.remove_documents(project_id, [file_id])
    return {"deleted": True, "file_id": file_id}


@router.post("/{file_id}/reprocess")
def reprocess_document(
    project_id: str,
    file_id: str,
    force_ocr: bool = False,
    user: dict = Depends(require_auth),
):
    store, project, settings = require_project(user["usuario"], project_id)
    docs, paths, entries, _file_ids = _prepare_reprocess_selection(
        project_id, project, [file_id]
    )
    remove_docs_from_indexes(settings, docs)
    store.remove_documents(project_id, [file_id])
    run_ingest_job(
        settings=settings,
        store=store,
        project_id=project_id,
        paths=paths,
        entries=entries,
        rebuild=False,
        reprocess_all=True,
        force_ocr=force_ocr,
    )
    return {"reprocessed": True, "file_id": file_id}
