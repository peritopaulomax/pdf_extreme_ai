from __future__ import annotations

import os
from urllib.parse import urlsplit


LOCAL_PROXY_BYPASS_HOSTS = ("127.0.0.1", "localhost", "::1")
PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}


def _append_no_proxy_hosts() -> None:
    no_proxy_set = set(LOCAL_PROXY_BYPASS_HOSTS)
    for key in ("NO_PROXY", "no_proxy"):
        existing = os.environ.get(key, "")
        if existing.strip():
            no_proxy_set.update(part.strip() for part in existing.split(",") if part.strip())

    no_proxy = ",".join(sorted(no_proxy_set))
    os.environ["NO_PROXY"] = no_proxy
    os.environ["no_proxy"] = no_proxy


def _proxy_scheme(value: str) -> str:
    try:
        return urlsplit(value).scheme.lower()
    except ValueError:
        return ""


def configure_proxy_env_for_local_services() -> None:
    """Keep local services off corporate proxies and drop proxy URLs httpx cannot parse."""
    _append_no_proxy_hosts()

    for key in PROXY_ENV_NAMES:
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        scheme = _proxy_scheme(value)
        if scheme and scheme not in SUPPORTED_PROXY_SCHEMES:
            os.environ.pop(key, None)
