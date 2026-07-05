from __future__ import annotations

import re

from werkzeug.security import check_password_hash, generate_password_hash


def validar_senha(senha: str) -> tuple[bool, str]:
    if len(senha) < 8:
        return False, "A senha deve ter no mínimo 8 caracteres"
    if not re.search(r"[a-z]", senha):
        return False, "A senha deve conter pelo menos uma letra minúscula"
    if not re.search(r"[A-Z]", senha):
        return False, "A senha deve conter pelo menos uma letra maiúscula"
    if not re.search(r"[0-9]", senha):
        return False, "A senha deve conter pelo menos um número"
    return True, "Senha válida"


def hash_senha(senha: str) -> str:
    return generate_password_hash(senha)


def verificar_hash(senha: str, senha_hash: str | None) -> bool:
    if not senha_hash:
        return False
    return check_password_hash(senha_hash, senha)
