from __future__ import annotations

from fastapi import HTTPException, Request


def _session_user(request: Request) -> dict | None:
    session = request.session
    if not session.get("logado"):
        return None
    usuario = (session.get("usuario") or "").strip().lower()
    perfil = session.get("perfil") or ""
    if not usuario:
        return None
    return {"usuario": usuario, "perfil": perfil}


def require_auth(request: Request) -> dict:
    user = _session_user(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"success": False, "error": "Não autenticado"},
        )
    return user


def require_admin(request: Request) -> dict:
    user = require_auth(request)
    if user.get("perfil") != "admin":
        raise HTTPException(
            status_code=403,
            detail={"success": False, "error": "Acesso restrito a administradores"},
        )
    return user
