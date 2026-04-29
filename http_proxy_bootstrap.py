"""Normalize or drop proxy env vars before httpx (used by ollama) reads them.

Corporate shells often set ALL_PROXY to socks://...; httpx only accepts http and
https unless optional SOCKS extras are installed. Clearing incompatible entries
lets local Ollama (127.0.0.1) work while NO_PROXY still applies.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

_ALLOWED_PROXY_SCHEMES = frozenset({"http", "https"})


def _first_proxy_url(raw: str) -> str:
    # e.g. "http://a,http://b" or single URL
    return raw.strip().split(",")[0].strip()


def proxy_url_scheme(raw: str) -> str | None:
    if not raw or not raw.strip():
        return None
    candidate = _first_proxy_url(raw)
    if not candidate:
        return None
    parsed = urlparse(candidate)
    scheme = (parsed.scheme or "").lower()
    return scheme or None


def strip_incompatible_httpx_proxies_from_environ() -> None:
    if os.environ.get("PDF_EXTREME_KEEP_SOCKS_PROXY", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    for key in list(os.environ.keys()):
        lk = key.lower()
        if lk == "no_proxy":
            continue
        if lk != "all_proxy" and not lk.endswith("_proxy"):
            continue
        value = os.environ.get(key, "")
        scheme = proxy_url_scheme(value)
        if scheme is None:
            continue
        if scheme not in _ALLOWED_PROXY_SCHEMES:
            del os.environ[key]


# Apply once on import so `import http_proxy_bootstrap` before ollama suffices.
strip_incompatible_httpx_proxies_from_environ()
