from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
_ROOT = _BACKEND.parent
_tmp_auth = tempfile.mkdtemp(prefix="pdf_docs_auth_")
_tmp_reg = tempfile.mkdtemp(prefix="pdf_docs_reg_")

os.environ["PDF_EXTREME_AI_ROOT"] = str(_ROOT)
os.environ["AUTH_DATA_DIR"] = _tmp_auth
os.environ["SESSION_SECRET"] = "test-docs-secret"
os.environ["PROJECTS_REGISTRY_PATH"] = str(Path(_tmp_reg) / "projects_registry.json")

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(_ROOT / "core"))

import api.documents as documents_api  # noqa: E402
from auth import store as auth_store  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from project_store import ProjectStore, project_uploads_dir  # noqa: E402


@pytest.fixture
def client():
    auth_store.salvar_admins(["alice"])
    auth_store.cadastrar_senha_usuario("alice", "Alice1234")

    reg = Path(os.environ["PROJECTS_REGISTRY_PATH"])
    reg.parent.mkdir(parents=True, exist_ok=True)
    ps = ProjectStore(str(reg))
    project = ps.create_project("Projeto Docs", owner_id="alice")
    uploads_dir = project_uploads_dir(project.project_id)
    (uploads_dir / "abcd1234_Teste.pdf").write_bytes(b"%PDF-1.4 teste 1")
    (uploads_dir / "efgh5678_Outro.pdf").write_bytes(b"%PDF-1.4 teste 2")
    ps.add_documents(
        project.project_id,
        [
            {
                "file_id": "doc-1",
                "display_name": "Teste.pdf",
                "storage_name": "abcd1234_Teste.pdf",
                "status": "indexed",
            },
            {
                "file_id": "doc-2",
                "display_name": "Outro.pdf",
                "storage_name": "efgh5678_Outro.pdf",
                "status": "indexed",
            },
        ],
    )

    client = TestClient(app)
    resp = client.post("/auth/login", json={"usuario": "alice", "senha": "Alice1234"})
    assert resp.status_code == 200
    return client, project.project_id


def test_delete_document_removes_registry_entry(client, monkeypatch):
    client, project_id = client
    calls: list[tuple[str, list[dict]]] = []

    def fake_remove(settings, docs):
        calls.append((settings.qdrant_collection, docs))
        return (0, 0)

    monkeypatch.setattr(documents_api, "remove_docs_from_indexes", fake_remove)

    resp = client.delete(f"/projects/{project_id}/documents/doc-1")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": True, "file_id": "doc-1"}
    assert len(calls) == 1
    assert [d["file_id"] for d in calls[0][1]] == ["doc-1"]

    listed = client.get(f"/projects/{project_id}/documents")
    assert listed.status_code == 200
    assert [doc["file_id"] for doc in listed.json()["documents"]] == ["doc-2"]


def test_delete_documents_selected_removes_only_marked_entries(client, monkeypatch):
    client, project_id = client
    calls: list[list[dict]] = []

    def fake_remove(settings, docs):
        calls.append(docs)
        return (0, 0)

    monkeypatch.setattr(documents_api, "remove_docs_from_indexes", fake_remove)

    resp = client.post(
        f"/projects/{project_id}/documents/remove",
        json={"file_ids": ["doc-1", "doc-2"]},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "deleted": True,
        "file_ids": ["doc-1", "doc-2"],
        "deleted_count": 2,
    }
    assert len(calls) == 1
    assert [doc["file_id"] for doc in calls[0]] == ["doc-1", "doc-2"]

    listed = client.get(f"/projects/{project_id}/documents")
    assert listed.status_code == 200
    assert listed.json()["documents"] == []


def test_reprocess_documents_selected_reingests_only_marked_entries(client, monkeypatch):
    client, project_id = client
    remove_calls: list[list[dict]] = []
    ingest_calls: list[dict] = []

    def fake_remove(settings, docs):
        remove_calls.append(docs)
        return (0, 0)

    def fake_ingest_job(**kwargs):
        ingest_calls.append(kwargs)
        return {
            "files_processed": 2,
            "files_total": 2,
            "total_pages": 12,
            "total_chunks": 48,
            "elapsed_s": 1.2,
            "errors": [],
            "per_file": [
                {"source_file": "abcd1234_Teste.pdf", "status": "indexed", "pages": 7, "chunks": 30},
                {"source_file": "efgh5678_Outro.pdf", "status": "indexed", "pages": 5, "chunks": 18},
            ],
        }

    monkeypatch.setattr(documents_api, "remove_docs_from_indexes", fake_remove)
    monkeypatch.setattr(documents_api, "run_ingest_job", fake_ingest_job)

    resp = client.post(
        f"/projects/{project_id}/documents/reprocess",
        json={"file_ids": ["doc-1", "doc-2"], "force_ocr": True},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["reprocessed"] is True
    assert payload["file_ids"] == ["doc-1", "doc-2"]
    assert payload["reprocessed_count"] == 2
    assert len(remove_calls) == 1
    assert [doc["file_id"] for doc in remove_calls[0]] == ["doc-1", "doc-2"]
    assert len(ingest_calls) == 1
    assert ingest_calls[0]["reprocess_all"] is True
    assert ingest_calls[0]["force_ocr"] is True
    assert [path.name for path in ingest_calls[0]["paths"]] == [
        "abcd1234_Teste.pdf",
        "efgh5678_Outro.pdf",
    ]


def test_reprocess_documents_selected_stream_emits_progress_and_done(client, monkeypatch):
    client, project_id = client

    monkeypatch.setattr(documents_api, "remove_docs_from_indexes", lambda settings, docs: (0, 0))

    def fake_stream_ingest_sse(**kwargs):
        yield 'event: progress\ndata: {"message":"Extraindo texto","current":1,"total":2,"percent":50}\n\n'
        yield 'event: done\ndata: {"files_processed":2,"files_total":2,"total_pages":9,"total_chunks":21,"elapsed_s":1.7,"per_file":[]}\n\n'

    monkeypatch.setattr(documents_api, "stream_ingest_sse", fake_stream_ingest_sse)

    with client.stream(
        "POST",
        f"/projects/{project_id}/documents/reprocess/stream",
        json={"file_ids": ["doc-1", "doc-2"], "force_ocr": True},
    ) as resp:
        body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in resp.iter_text())

    assert resp.status_code == 200
    assert "event: status" in body
    assert "Reprocessando 2 arquivo(s) selecionado(s)" in body
    assert "event: progress" in body
    assert "Extraindo texto" in body
    assert "event: done" in body


def test_reprocess_document_single_uses_forced_reingest(client, monkeypatch):
    client, project_id = client
    ingest_calls: list[dict] = []

    monkeypatch.setattr(documents_api, "remove_docs_from_indexes", lambda settings, docs: (0, 0))
    monkeypatch.setattr(
        documents_api,
        "run_ingest_job",
        lambda **kwargs: ingest_calls.append(kwargs) or {},
    )

    resp = client.post(f"/projects/{project_id}/documents/doc-1/reprocess")

    assert resp.status_code == 200
    assert resp.json() == {"reprocessed": True, "file_id": "doc-1"}
    assert len(ingest_calls) == 1
    assert ingest_calls[0]["reprocess_all"] is True
