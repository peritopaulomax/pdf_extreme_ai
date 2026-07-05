#!/usr/bin/env python3
"""Cria admins.json com um administrador se o arquivo estiver vazio ou ausente."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from auth import store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap administrador inicial")
    parser.add_argument(
        "usuario",
        nargs="?",
        default=os.environ.get("BOOTSTRAP_ADMIN_USER", "").strip(),
        help="Login do administrador (ou BOOTSTRAP_ADMIN_USER no .env)",
    )
    args = parser.parse_args()
    usuario = (args.usuario or "").strip().lower()
    if not usuario:
        print("Erro: informe o usuário admin (argumento ou BOOTSTRAP_ADMIN_USER).")
        return 1

    store.ensure_auth_dir()
    admins = store.carregar_admins()
    if admins:
        print(f"admins.json já existe com: {', '.join(admins)}")
        print("Use Primeiro Acesso na UI se ainda não cadastrou senha.")
        return 0

    store.salvar_admins([usuario])
    print(f'Administrador "{usuario}" criado em {store.ensure_auth_dir()}/admins.json')
    print("Execute Primeiro Acesso na UI com este usuário para definir a senha.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
