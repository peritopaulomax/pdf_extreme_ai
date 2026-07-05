"""
Credenciais de serviço externo (padrão GEP / Fernet por máquina).

N/A para Ollama local — stub documentado. Use quando houver API com usuário/senha.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from auth.store import ensure_auth_dir


def _credentials_path() -> Path:
    return ensure_auth_dir() / "service_credentials.enc"


def is_configured() -> bool:
    return _credentials_path().exists()


def save_credentials(usuario: str, senha: str) -> None:
    """Persiste credenciais criptografadas (implementação completa em lote futuro)."""
    ensure_auth_dir()
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            "Pacote cryptography necessário para credenciais de serviço"
        ) from exc

    # Derivação simplificada por host — ver AUTH_SPEC.md para detalhes
    import hashlib
    import platform

    host = platform.node() + platform.system() + platform.machine()
    salt = hashlib.sha256(host.encode()).digest()[:16]
    key = hashlib.pbkdf2_hmac("sha256", b"pdf-extreme-ai-v2", salt, 100_000, dklen=32)
    import base64

    fernet = Fernet(base64.urlsafe_b64encode(key))
    payload = json.dumps({"usuario": usuario, "senha": senha}).encode("utf-8")
    path = _credentials_path()
    path.write_bytes(fernet.encrypt(payload))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def clear_credentials() -> None:
    p = _credentials_path()
    if p.exists():
        p.unlink()
