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


def _load_or_create_key() -> bytes:
    """Carrega ou gera chave Fernet. Prioridade: SERVICE_CREDENTIALS_KEY > arquivo .key > geracao aleatoria."""
    ensure_auth_dir()
    key_env = os.environ.get("SERVICE_CREDENTIALS_KEY", "").strip()
    if key_env:
        return key_env.encode("utf-8")

    key_path = ensure_auth_dir() / "service_credentials.key"
    if key_path.exists():
        return key_path.read_bytes()

    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    key_path.write_bytes(key)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return key


def save_credentials(usuario: str, senha: str) -> None:
    """Persiste credenciais criptografadas (implementação completa em lote futuro)."""
    ensure_auth_dir()
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            "Pacote cryptography necessário para credenciais de serviço"
        ) from exc

    key = _load_or_create_key()
    fernet = Fernet(key)
    payload = json.dumps({"usuario": usuario, "senha": senha}).encode("utf-8")
    path = _credentials_path()
    path.write_bytes(fernet.encrypt(payload))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_credentials() -> dict[str, str]:
    """Carrega credenciais previamente salvas."""
    path = _credentials_path()
    if not path.exists():
        raise FileNotFoundError("Credenciais de servico nao configuradas")
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError("Pacote cryptography necessário para credenciais de serviço") from exc

    key = _load_or_create_key()
    fernet = Fernet(key)
    payload = fernet.decrypt(path.read_bytes())
    data = json.loads(payload.decode("utf-8"))
    return {"usuario": str(data.get("usuario", "")), "senha": str(data.get("senha", ""))}


def clear_credentials() -> None:
    p = _credentials_path()
    if p.exists():
        p.unlink()
