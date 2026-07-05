"""Modos de workspace da UI (RAG, chat livre, corretor)."""

from __future__ import annotations

from typing import Literal

from index_bootstrap import project_index_empty
from query_planner import plan_query
from runtime_config import RuntimeSettings

AppWorkspace = Literal["rag", "free", "proofread"]

WORKSPACE_LABELS: dict[str, str] = {
    "rag": "Autos (RAG)",
    "free": "Chat livre",
    "proofread": "Corretor",
}

_LABEL_TO_WORKSPACE = {v: k for k, v in WORKSPACE_LABELS.items()}

_SUMMARY_BLOCK_WORDS = (
    "resumo do caso",
    "resumo geral",
    "explique o caso",
    "analise o caso",
    "analise geral",
    "sintese do caso",
    "síntese do caso",
    "descreva o caso",
    "panorama do caso",
)


def label_for_workspace(ws: AppWorkspace) -> str:
    return WORKSPACE_LABELS.get(ws, ws)


def workspace_from_label(label: str) -> AppWorkspace:
    return _LABEL_TO_WORKSPACE.get(label, "rag")  # type: ignore[return-value]


def chat_mode_for_workspace(ws: AppWorkspace) -> str:
    return "rag" if ws == "rag" else "general"


def rag_index_ready(settings: RuntimeSettings) -> bool:
    return not project_index_empty(settings)


def should_run_audit_synthesis(
    prompt: str,
    settings: RuntimeSettings,
    *,
    forced_profile: str | None,
    audit_mode_ui: bool,
) -> bool:
    """
    Map-reduce de auditoria apenas para buscas literais/exaustivas,
    nao para resumos ou analises gerais (mesmo com checkbox ligado).
    """
    plan = plan_query(prompt, settings, forced_profile=forced_profile)
    lowered = (prompt or "").lower()
    if any(w in lowered for w in _SUMMARY_BLOCK_WORDS):
        return False
    if plan.intent == "auditoria_exaustiva":
        return True
    if audit_mode_ui and plan.intent in (
        "literal_exaustivo",
        "cadeia_custodia",
        "forense_autenticidade",
    ):
        return True
    return False
