from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auth.passwords import hash_senha, verificar_hash

_V2_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_AUTH_DIR = _V2_ROOT / "data" / "auth"


def _auth_dir() -> Path:
    raw = os.environ.get("AUTH_DATA_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_AUTH_DIR.resolve()


def _admins_path() -> Path:
    return _auth_dir() / "admins.json"


def _usuarios_path() -> Path:
    return _auth_dir() / "usuarios_app.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _norm_user(username: str) -> str:
    return (username or "").strip().lower()


def ensure_auth_dir() -> Path:
    d = _auth_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- admins.json ---


def carregar_admins() -> list[str]:
    path = _admins_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    admins = data.get("administradores") or []
    return [str(a).strip().lower() for a in admins if str(a).strip()]


def salvar_admins(admins: list[str]) -> None:
    ensure_auth_dir()
    normalized = sorted({_norm_user(a) for a in admins if _norm_user(a)})
    _write_json(
        _admins_path(),
        {
            "administradores": normalized,
            "ultima_atualizacao": _now_iso(),
        },
    )


def eh_admin(username: str) -> bool:
    u = _norm_user(username)
    return u in carregar_admins()


# --- usuarios_app.json ---


def _load_usuarios_doc() -> dict[str, Any]:
    path = _usuarios_path()
    if not path.exists():
        return {"usuarios": {}, "consultores": [], "ultima_atualizacao": _now_iso()}
    data = json.loads(path.read_text(encoding="utf-8"))
    if "usuarios" not in data or not isinstance(data["usuarios"], dict):
        data["usuarios"] = {}
    if "consultores" not in data or not isinstance(data["consultores"], list):
        data["consultores"] = []
    return data


def carregar_usuarios() -> dict[str, Any]:
    return dict(_load_usuarios_doc().get("usuarios") or {})


def carregar_consultores() -> list[str]:
    doc = _load_usuarios_doc()
    return [_norm_user(c) for c in doc.get("consultores") or [] if _norm_user(c)]


def salvar_usuarios(
    usuarios: dict[str, Any],
    consultores: list[str] | None = None,
) -> None:
    ensure_auth_dir()
    doc = _load_usuarios_doc()
    doc["usuarios"] = usuarios
    if consultores is not None:
        doc["consultores"] = sorted({_norm_user(c) for c in consultores if _norm_user(c)})
    doc["ultima_atualizacao"] = _now_iso()
    _write_json(_usuarios_path(), doc)


def eh_consultor(username: str) -> bool:
    return _norm_user(username) in carregar_consultores()


def adicionar_consultor(username: str) -> None:
    u = _norm_user(username)
    if not u:
        raise ValueError("Nome de consultor inválido")
    consultores = carregar_consultores()
    if u in consultores:
        raise ValueError(f'Consultor "{u}" já existe')
    consultores.append(u)
    salvar_usuarios(carregar_usuarios(), consultores=consultores)


def remover_consultor(username: str) -> None:
    u = _norm_user(username)
    consultores = carregar_consultores()
    if u not in consultores:
        raise LookupError(f'Consultor "{u}" não encontrado')
    consultores = [c for c in consultores if c != u]
    salvar_usuarios(carregar_usuarios(), consultores=consultores)


def usuario_autorizado(username: str) -> bool:
    u = _norm_user(username)
    return eh_admin(u) or eh_consultor(u)


def usuario_tem_senha_cadastrada(username: str) -> bool:
    u = _norm_user(username)
    usuarios = carregar_usuarios()
    rec = usuarios.get(u)
    if not rec:
        return False
    return bool(rec.get("senha_hash"))


def cadastrar_senha_usuario(username: str, senha: str) -> None:
    u = _norm_user(username)
    if not usuario_autorizado(u):
        raise PermissionError("Usuário não autorizado")
    usuarios = carregar_usuarios()
    tipo = "admin" if eh_admin(u) else "consultor"
    usuarios[u] = {
        "senha_hash": hash_senha(senha),
        "tipo": tipo,
        "primeiro_acesso": False,
        "ultima_atualizacao": _now_iso(),
    }
    salvar_usuarios(usuarios)


def verificar_senha_usuario(username: str, senha: str) -> bool:
    u = _norm_user(username)
    usuarios = carregar_usuarios()
    rec = usuarios.get(u)
    if not rec:
        return False
    return verificar_hash(senha, rec.get("senha_hash"))


def resetar_senha_usuario(username: str) -> None:
    u = _norm_user(username)
    usuarios = carregar_usuarios()
    if u not in usuarios:
        raise LookupError(f'Usuário "{u}" não encontrado')
    rec = dict(usuarios[u])
    rec["senha_hash"] = None
    rec["primeiro_acesso"] = True
    rec["ultima_atualizacao"] = _now_iso()
    usuarios[u] = rec
    salvar_usuarios(usuarios)


def consultor_tem_senha(username: str) -> bool:
    return usuario_tem_senha_cadastrada(username)


def adicionar_admin(username: str) -> None:
    u = _norm_user(username)
    if not u:
        raise ValueError("Nome inválido")
    admins = carregar_admins()
    if u in admins:
        raise ValueError(f'Administrador "{u}" já existe')
    admins.append(u)
    salvar_admins(admins)


def remover_admin(username: str, *, self_user: str | None = None) -> None:
    u = _norm_user(username)
    admins = carregar_admins()
    if u not in admins:
        raise LookupError(f'Administrador "{u}" não encontrado')
    if len(admins) <= 1:
        raise ValueError("Não é possível remover o último administrador")
    if self_user and _norm_user(self_user) == u:
        raise ValueError("Você não pode remover a si mesmo")
    admins = [a for a in admins if a != u]
    salvar_admins(admins)
