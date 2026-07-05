from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

# AUTH_DATA_DIR antes de importar store/main
_tmp = tempfile.mkdtemp(prefix="pdf_auth_test_")
os.environ["AUTH_DATA_DIR"] = _tmp
os.environ["SESSION_SECRET"] = "test-secret-key-for-pytest-only"

from auth import store  # noqa: E402
from auth.passwords import validar_senha  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_auth_dir():
    d = Path(_tmp)
    for name in ("admins.json", "usuarios_app.json"):
        p = d / name
        if p.exists():
            p.unlink()
    yield


def test_validar_senha():
    assert validar_senha("Abcdef1!")[0] is True
    assert validar_senha("short")[0] is False
    assert validar_senha("alllowercase1")[0] is False
    assert validar_senha("ALLUPPERCASE1")[0] is False
    assert validar_senha("NoNumbers")[0] is False


def test_cadastrar_e_verificar_senha():
    store.salvar_admins(["admin1"])
    store.adicionar_consultor("consultor1")
    store.cadastrar_senha_usuario("consultor1", "Senha1234")
    assert store.verificar_senha_usuario("consultor1", "Senha1234")
    assert not store.verificar_senha_usuario("consultor1", "wrong")


def test_primeiro_acesso_nao_autorizado():
    client = TestClient(app)
    r = client.post(
        "/auth/primeiro-acesso",
        json={
            "usuario": "x",
            "senha": "Senha1234",
            "senha_confirmacao": "Senha1234",
        },
    )
    assert r.status_code == 403


def test_primeiro_acesso_ja_tem_senha():
    store.salvar_admins(["u1"])
    store.cadastrar_senha_usuario("u1", "Senha1234")
    client = TestClient(app)
    r = client.post(
        "/auth/primeiro-acesso",
        json={
            "usuario": "u1",
            "senha": "Senha9999",
            "senha_confirmacao": "Senha9999",
        },
    )
    assert r.status_code == 409


def test_reset_e_login_falha_ate_novo_cadastro():
    store.salvar_admins(["admin"])
    store.adicionar_consultor("c1")
    store.cadastrar_senha_usuario("c1", "Senha1234")
    store.resetar_senha_usuario("c1")
    assert not store.usuario_tem_senha_cadastrada("c1")
    client = TestClient(app)
    r = client.post("/auth/login", json={"usuario": "c1", "senha": "Senha1234"})
    assert r.status_code == 403


def test_nao_remove_ultimo_admin():
    store.salvar_admins(["only"])
    with pytest.raises(ValueError, match="último"):
        store.remover_admin("only", self_user="only")


def test_api_projetos_sem_sessao_401():
    client = TestClient(app)
    r = client.get("/projects")
    assert r.status_code == 401


def test_login_admin_flow():
    store.salvar_admins(["admin"])
    store.cadastrar_senha_usuario("admin", "Admin1234")
    client = TestClient(app)
    r = client.post("/auth/login", json={"usuario": "admin", "senha": "Admin1234"})
    assert r.status_code == 200
    assert r.json()["perfil"] == "admin"
    r2 = client.get("/projects")
    assert r2.status_code == 200


def test_consultor_nao_acessa_admin_api():
    store.salvar_admins(["admin"])
    store.adicionar_consultor("cons")
    store.cadastrar_senha_usuario("admin", "Admin1234")
    store.cadastrar_senha_usuario("cons", "Cons12345")
    client = TestClient(app)
    client.post("/auth/login", json={"usuario": "cons", "senha": "Cons12345"})
    r = client.get("/auth/administradores")
    assert r.status_code == 403


def test_reset_consultor_admin():
    store.salvar_admins(["admin"])
    store.adicionar_consultor("cons")
    store.cadastrar_senha_usuario("admin", "Admin1234")
    store.cadastrar_senha_usuario("cons", "Cons12345")
    client = TestClient(app)
    client.post("/auth/login", json={"usuario": "admin", "senha": "Admin1234"})
    r = client.post("/auth/consultores/resetar-senha", json={"nome": "cons"})
    assert r.status_code == 200
    assert "resetada" in r.json()["message"].lower()
