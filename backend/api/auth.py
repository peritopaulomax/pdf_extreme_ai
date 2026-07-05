from __future__ import annotations

import threading
import time
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import store
from auth.dependencies import require_admin, require_auth
from auth.passwords import validar_senha

router = APIRouter(prefix="/auth", tags=["auth"])

# Rate limit login: 10 tentativas / 15 min por IP e por usuario.
# Nota: em deploy multi-worker recomenda-se Redis ou rate-limit no reverse-proxy/WAF.
_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_LOGIN_WINDOW_S = 15 * 60
_LOGIN_MAX = 10
_LOGIN_LOCK = threading.Lock()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _rate_limit_key(request: Request, username: str = "") -> str:
    parts = ["ip", _client_ip(request)]
    user = (username or "").strip().lower()
    if user:
        parts.extend(["user", user])
    return ":".join(parts)


def _check_rate_limit(request: Request, username: str = "") -> None:
    key = _rate_limit_key(request, username)
    now = time.time()
    with _LOGIN_LOCK:
        attempts = _LOGIN_ATTEMPTS[key]
        attempts[:] = [t for t in attempts if now - t < _LOGIN_WINDOW_S]
        if len(attempts) >= _LOGIN_MAX:
            raise HTTPException(
                status_code=429,
                detail={
                    "success": False,
                    "error": "Muitas tentativas de login. Tente novamente em alguns minutos.",
                },
            )


def _record_login_attempt(request: Request, username: str = "") -> None:
    key = _rate_limit_key(request, username)
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS[key].append(time.time())


def _err(status: int, error: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"success": False, "error": error})


class LoginBody(BaseModel):
    usuario: str = ""
    senha: str = ""


class PrimeiroAcessoBody(BaseModel):
    usuario: str = ""
    senha: str = ""
    senha_confirmacao: str = ""


class NomeBody(BaseModel):
    nome: str = ""


@router.post("/login")
def login(body: LoginBody, request: Request):
    username_lower = body.usuario.strip().lower()
    _check_rate_limit(request, username_lower)
    if not body.usuario.strip() or not body.senha:
        raise _err(400, "Preencha usuário e senha")

    if not store.usuario_autorizado(username_lower):
        _record_login_attempt(request, username_lower)
        raise _err(
            403,
            "Usuário não autorizado. Entre em contato com um administrador.",
        )

    if not store.usuario_tem_senha_cadastrada(username_lower):
        _record_login_attempt(request, username_lower)
        raise _err(
            403,
            'Usuário não cadastrado. Use o botão "Primeiro Acesso" para cadastrar sua senha.',
        )

    if not store.verificar_senha_usuario(username_lower, body.senha):
        _record_login_attempt(request, username_lower)
        raise _err(401, "Usuário ou senha incorretos")

    perfil = "admin" if store.eh_admin(username_lower) else "consultor"
    request.session["logado"] = True
    request.session["usuario"] = username_lower
    request.session["perfil"] = perfil

    return {
        "success": True,
        "usuario": username_lower,
        "perfil": perfil,
    }


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"success": True}


@router.get("/me")
def me(user: dict = Depends(require_auth)):
    return {
        "success": True,
        "usuario": user["usuario"],
        "perfil": user["perfil"],
    }


@router.get("/primeiro-acesso/check")
def check_primeiro_acesso(usuario: str = Query("")):
    username_lower = usuario.strip().lower()
    autorizado = store.usuario_autorizado(username_lower) if username_lower else False
    tem_senha = (
        store.usuario_tem_senha_cadastrada(username_lower) if username_lower else False
    )
    return {
        "autorizado": autorizado,
        "tem_senha": tem_senha,
    }


@router.post("/primeiro-acesso")
def primeiro_acesso(body: PrimeiroAcessoBody):
    if not body.usuario.strip() or not body.senha or not body.senha_confirmacao:
        raise _err(400, "Preencha todos os campos")

    username_lower = body.usuario.strip().lower()

    if not store.usuario_autorizado(username_lower):
        raise _err(403, "Usuário não cadastrado. Entre em contato com um administrador.")

    if store.usuario_tem_senha_cadastrada(username_lower):
        raise _err(409, "Usuário já possui senha cadastrada. Use a tela de login.")

    if body.senha != body.senha_confirmacao:
        raise _err(400, "As senhas não coincidem")

    ok, msg = validar_senha(body.senha)
    if not ok:
        raise _err(400, msg)

    store.cadastrar_senha_usuario(username_lower, body.senha)
    return {"success": True, "message": "Senha cadastrada com sucesso! Agora você pode fazer login."}


# --- Admin: administradores ---


@router.get("/administradores")
def listar_administradores(_: dict = Depends(require_admin)):
    return {"success": True, "administradores": store.carregar_admins()}


@router.post("/administradores")
def adicionar_administrador(body: NomeBody, user: dict = Depends(require_admin)):
    nome = body.nome.strip().lower()
    if not nome:
        raise _err(400, "Nome inválido")
    try:
        store.adicionar_admin(nome)
    except ValueError as exc:
        raise _err(400, str(exc)) from exc
    return {
        "success": True,
        "message": f'Administrador "{nome}" adicionado.',
    }


@router.delete("/administradores")
def remover_administrador(body: NomeBody, user: dict = Depends(require_admin)):
    nome = body.nome.strip().lower()
    if not nome:
        raise _err(400, "Nome inválido")
    try:
        store.remover_admin(nome, self_user=user["usuario"])
    except ValueError as exc:
        raise _err(400, str(exc)) from exc
    except LookupError as exc:
        raise _err(404, str(exc)) from exc
    return {
        "success": True,
        "message": f'Administrador "{nome}" removido.',
    }


# --- Admin: consultores ---


@router.get("/consultores")
def listar_consultores(_: dict = Depends(require_admin)):
    consultores = store.carregar_consultores()
    return {
        "success": True,
        "consultores": [
            {"nome": c, "tem_senha": store.consultor_tem_senha(c)} for c in consultores
        ],
    }


@router.post("/consultores")
def adicionar_consultor(body: NomeBody, _: dict = Depends(require_admin)):
    nome = body.nome.strip().lower()
    if not nome:
        raise _err(400, "Nome inválido")
    if store.eh_admin(nome):
        raise _err(400, "Administradores não podem ser cadastrados como consultores")
    try:
        store.adicionar_consultor(nome)
    except ValueError as exc:
        raise _err(400, str(exc)) from exc
    return {
        "success": True,
        "message": f'Consultor "{nome}" adicionado.',
    }


@router.delete("/consultores")
def remover_consultor(body: NomeBody, _: dict = Depends(require_admin)):
    nome = body.nome.strip().lower()
    if not nome:
        raise _err(400, "Nome inválido")
    try:
        store.remover_consultor(nome)
    except LookupError as exc:
        raise _err(404, str(exc)) from exc
    return {
        "success": True,
        "message": f'Consultor "{nome}" removido.',
    }


@router.post("/consultores/resetar-senha")
def resetar_senha_consultor(body: NomeBody, _: dict = Depends(require_admin)):
    nome = body.nome.strip().lower()
    if not nome:
        raise _err(400, "Nome inválido")
    if not store.eh_consultor(nome):
        raise _err(400, "Usuário não é consultor")
    try:
        store.resetar_senha_usuario(nome)
    except LookupError as exc:
        raise _err(404, str(exc)) from exc
    return {
        "success": True,
        "message": (
            f'Senha do consultor "{nome}" resetada. '
            "Ele poderá fazer novo primeiro acesso."
        ),
    }
