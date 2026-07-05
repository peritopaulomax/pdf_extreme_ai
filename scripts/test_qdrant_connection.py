#!/usr/bin/env python3
"""
Testes de rede para Qdrant com proxy corporativo (Squid).
Execute: conda activate pdfextreme && python scripts/test_qdrant_connection.py
"""
from __future__ import annotations

import os
import sys
import urllib.request


def print_proxy_env() -> None:
    for k in sorted(os.environ.keys()):
        kl = k.lower()
        if "proxy" in kl:
            print(f"  {k}={os.environ[k]!r}")


def clear_proxy_vars() -> None:
    for k in list(os.environ.keys()):
        lk = k.lower()
        if lk.endswith("_proxy") or lk == "all_proxy":
            os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]


def main() -> int:
    backup = {
        k: os.environ[k]
        for k in os.environ
        if k.lower().endswith("_proxy") or k.lower() == "all_proxy"
    }

    print("=== 1) Proxy no shell (antes de mexer no processo) ===")
    print_proxy_env() if any("proxy" in k.lower() for k in os.environ) else print("  (nenhuma)")

    print("\n=== 2) urllib → http://127.0.0.1:6333/ com env atual ===")
    try:
        with urllib.request.urlopen("http://127.0.0.1:6333/", timeout=8) as r:
            print(f"  OK HTTP {r.status}, início do corpo: {r.read(160)!r}")
    except Exception as e:
        print(f"  Falha: {type(e).__name__}: {e}")

    print("\n=== 3) Limpar *_proxy + NO_PROXY (como ingest.py deve fazer) ===")
    clear_proxy_vars()
    print_proxy_env()

    print("\n=== 4) urllib → http://127.0.0.1:6333/ depois da limpeza ===")
    try:
        with urllib.request.urlopen("http://127.0.0.1:6333/", timeout=8) as r:
            print(f"  OK HTTP {r.status}, início: {r.read(160)!r}")
    except Exception as e:
        print(f"  Falha: {type(e).__name__}: {e}")

    print("\n=== 5) qdrant_client QdrantClient(host=127.0.0.1, trust_env=False) ===")
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host="127.0.0.1", port=6333, trust_env=False)
        cols = client.get_collections()
        names = [x.name for x in cols.collections]
        print(f"  OK — coleções: {names}")
    except Exception as e:
        print(f"  Falha: {type(e).__name__}: {e}")
        return 1

    print("\n=== 6) Repor proxy do shell e testar trust_env=True (costuma falhar com Squid) ===")
    for k, v in backup.items():
        os.environ[k] = v
    print_proxy_env()
    try:
        from qdrant_client import QdrantClient

        client2 = QdrantClient(host="127.0.0.1", port=6333, trust_env=True)
        client2.get_collections()
        print("  OK (trust_env=True funcionou)")
    except Exception as e:
        print(f"  Falha esperada em redes com proxy: {type(e).__name__}: {e}")

    print("\nConclusão: use trust_env=False no QdrantClient se (6) falhar e (5) passar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
