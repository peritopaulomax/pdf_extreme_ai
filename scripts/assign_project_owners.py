#!/usr/bin/env python3
"""
Atribui owner_id a projetos antigos sem dono (migração única).

Uso:
  python scripts/assign_project_owners.py paulo.pmgir
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import bootstrap_paths

bootstrap_paths.setup()

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from runtime_config import configure_runtime_env  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Define owner_id em projetos sem dono no registry"
    )
    parser.add_argument("owner", help="Login do dono (ex.: paulo.pmgir)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas listar projetos que seriam atualizados",
    )
    args = parser.parse_args()
    owner = args.owner.strip().lower()
    if not owner:
        print("Erro: owner inválido")
        return 1

    settings = configure_runtime_env()
    reg_path = Path(settings.projects_registry_path)
    if not reg_path.exists():
        print(f"Registry não encontrado: {reg_path}")
        return 1

    data = json.loads(reg_path.read_text(encoding="utf-8"))
    updated = 0
    for p in data.get("projects", []):
        current = str(p.get("owner_id", "") or "").strip().lower()
        if current:
            continue
        pid = p.get("project_id", "?")
        if args.dry_run:
            print(f"  [dry-run] {pid} -> {owner}")
        else:
            p["owner_id"] = owner
            print(f"  {pid} -> {owner}")
        updated += 1

    if not updated:
        print("Nenhum projeto sem owner_id.")
        return 0

    if not args.dry_run:
        reg_path.write_text(
            json.dumps(data, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        print(f"Atualizados {updated} projeto(s) em {reg_path}")
    else:
        print(f"Seriam atualizados {updated} projeto(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
