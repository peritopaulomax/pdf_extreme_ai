"""Testes de fumaça da API (sem subir servidor HTTP)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

os.environ.setdefault("PDF_EXTREME_AI_ROOT", str(ROOT))
os.environ.setdefault("AUTH_DATA_DIR", tempfile.mkdtemp(prefix="pdf_smoke_auth_"))
os.environ.setdefault("SESSION_SECRET", "smoke-test-session-secret")
for entry in (str(BACKEND), str(ROOT / "core"), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from core.bootstrap import bootstrap_legacy  # noqa: E402

bootstrap_legacy()

from auth import store  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402


@pytest.fixture
def client():
    store.salvar_admins(["smoke"])
    if not store.usuario_tem_senha_cadastrada("smoke"):
        store.cadastrar_senha_usuario("smoke", "Smoke1234")
    c = TestClient(app)
    r = c.post("/auth/login", json={"usuario": "smoke", "senha": "Smoke1234"})
    assert r.status_code == 200
    return c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["core_exists"] is True


def test_list_projects_only_owned_by_session_user(client):
    r = client.get("/projects")
    assert r.status_code == 200
    for p in r.json()["projects"]:
        assert p.get("owner_id") == "smoke"


def test_proofread_structure(client):
    r = client.post(
        "/proofread",
        json={"text": "O tribunal decidiu pelo merito da causa.", "max_chars": 500},
    )
    if r.status_code >= 500:
        pytest.skip(f"Ollama indisponivel: {r.text}")
    assert r.status_code == 200
    data = r.json()
    assert "corrected_text" in data
    assert "changes" in data
    assert isinstance(data["changes"], list)


def test_conversations_crud(client):
    projects = client.get("/projects").json()["projects"]
    if not projects:
        created = client.post("/projects", json={"name": "api-smoke-test"}).json()
        pid = created["project_id"]
        assert created.get("owner_id") == "smoke"
    else:
        pid = projects[0]["project_id"]

    c = client.post(
        f"/projects/{pid}/conversations",
        json={"title": "Smoke conv"},
    )
    assert c.status_code == 200
    cid = c.json()["conversation_id"]

    listed = client.get(f"/projects/{pid}/conversations")
    assert any(x["conversation_id"] == cid for x in listed.json()["conversations"])

    ren = client.patch(
        f"/projects/{pid}/conversations/{cid}",
        json={"title": "Renamed"},
    )
    assert ren.status_code == 200
    assert ren.json()["title"] == "Renamed"

    client.delete(f"/projects/{pid}/conversations/{cid}")
