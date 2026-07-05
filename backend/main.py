"""PDF Extreme AI API — FastAPI sobre o motor core."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.bootstrap import bootstrap_legacy  # noqa: E402

bootstrap_legacy()

from core.logging_config import configure_logging  # noqa: E402

configure_logging()

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND.parent / ".env")

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from api import (  # noqa: E402
    auth,
    chat,
    chat_turns,
    config,
    conversations,
    documents,
    export,
    health,
    ingest,
    project_settings,
    projects,
    proofread,
)
from auth.dependencies import require_auth  # noqa: E402
from auth.store import ensure_auth_dir  # noqa: E402
from core.logging_config import get_logger  # noqa: E402

ensure_auth_dir()
logger = get_logger(__name__)

_ENV = (os.environ.get("ENVIRONMENT") or os.environ.get("ENV", "")).strip().lower()
_IS_PROD = _ENV in ("production", "prod")

_session_secret_raw = os.environ.get("SESSION_SECRET", "").strip()
if not _session_secret_raw:
    if _IS_PROD:
        raise RuntimeError(
            "SESSION_SECRET deve estar configurado em producao. "
            "Defina SESSION_SECRET no .env ou nas variaveis de ambiente."
        )
    _session_secret_raw = "dev-change-me-in-production"
    logger.warning(
        "SESSION_SECRET nao configurado; usando secret de desenvolvimento. "
        "Configure SESSION_SECRET antes de deployar em producao."
    )
_SESSION_SECRET = _session_secret_raw

_cors_origins_raw = os.environ.get("CORS_ORIGINS", "").strip()
if not _cors_origins_raw:
    if _IS_PROD:
        raise RuntimeError(
            "CORS_ORIGINS deve estar configurado em producao. "
            "Defina CORS_ORIGINS no .env ou nas variaveis de ambiente."
        )
    _cors_origins_raw = "http://127.0.0.1:5173,http://localhost:5173"
_CORS_ORIGINS = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app = FastAPI(
    title="PDF Extreme AI API",
    version="0.3.0",
    description="REST + SSE sobre o motor RAG (core/)",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=_SESSION_SECRET,
    session_cookie="pdf_extreme_session",
    max_age=14 * 24 * 3600,
    same_site="lax",
    https_only=os.environ.get("SESSION_HTTPS_ONLY", "").lower() in ("1", "true", "yes"),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_auth_dep = [Depends(require_auth)]

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(config.router, dependencies=_auth_dep)
app.include_router(projects.router, dependencies=_auth_dep)
app.include_router(project_settings.router, dependencies=_auth_dep)
app.include_router(documents.router, dependencies=_auth_dep)
app.include_router(conversations.router, dependencies=_auth_dep)
app.include_router(ingest.router, dependencies=_auth_dep)
app.include_router(chat.router, dependencies=_auth_dep)
app.include_router(chat_turns.router, dependencies=_auth_dep)
app.include_router(export.router, dependencies=_auth_dep)
app.include_router(proofread.router, dependencies=_auth_dep)
