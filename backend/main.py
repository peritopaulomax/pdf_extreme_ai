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

ensure_auth_dir()

_SESSION_SECRET = os.environ.get("SESSION_SECRET", "").strip() or "dev-change-me-in-production"
_CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if o.strip()
]

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
