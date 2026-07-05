from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
_ROOT = _BACKEND.parent
_tmp_auth = tempfile.mkdtemp(prefix="pdf_owner_auth_")
_tmp_reg = tempfile.mkdtemp(prefix="pdf_owner_reg_")

os.environ["PDF_EXTREME_AI_ROOT"] = str(_ROOT)
os.environ["AUTH_DATA_DIR"] = _tmp_auth
os.environ["SESSION_SECRET"] = "test-owner-secret"
os.environ["PROJECTS_REGISTRY_PATH"] = str(Path(_tmp_reg) / "projects_registry.json")

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(_ROOT / "core"))

from auth import store as auth_store  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from project_store import ProjectStore  # noqa: E402


@pytest.fixture
def clients():
    auth_store.salvar_admins(["alice", "bob"])
    auth_store.cadastrar_senha_usuario("alice", "Alice1234")
    auth_store.cadastrar_senha_usuario("bob", "Bob12345")

    reg = Path(os.environ["PROJECTS_REGISTRY_PATH"])
    reg.parent.mkdir(parents=True, exist_ok=True)
    ps = ProjectStore(str(reg))
    p_alice = ps.create_project("Projeto Alice", owner_id="alice")
    p_bob = ps.create_project("Projeto Bob", owner_id="bob")

    c_alice = TestClient(app)
    c_alice.post("/auth/login", json={"usuario": "alice", "senha": "Alice1234"})
    c_bob = TestClient(app)
    c_bob.post("/auth/login", json={"usuario": "bob", "senha": "Bob12345"})
    return c_alice, c_bob, p_alice, p_bob


def test_list_only_own_projects(clients):
    c_alice, c_bob, p_alice, p_bob = clients
    alice_ids = {p["project_id"] for p in c_alice.get("/projects").json()["projects"]}
    bob_ids = {p["project_id"] for p in c_bob.get("/projects").json()["projects"]}
    assert p_alice.project_id in alice_ids
    assert p_bob.project_id not in alice_ids
    assert p_bob.project_id in bob_ids
    assert p_alice.project_id not in bob_ids


def test_cannot_access_other_project(clients):
    c_alice, _, _, p_bob = clients
    r = c_alice.get(f"/projects/{p_bob.project_id}")
    assert r.status_code == 404


def test_create_sets_owner(clients):
    c_alice, _, _, _ = clients
    r = c_alice.post("/projects", json={"name": "Novo de Alice"})
    assert r.status_code == 200
    assert r.json()["owner_id"] == "alice"
