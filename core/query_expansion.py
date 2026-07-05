"""Expansao leve de consulta para recall (lexico forense + memoria do caso)."""

from __future__ import annotations

import re

_FORENSIC_EXTRA = (
    "pericia",
    "pericia digital",
    "informatica forense",
    "integridade",
    "autenticidade",
    "hash",
    "cadeia de custodia",
    "audio",
    "video",
    "imagem",
    "metadados",
    "deepfake",
    "manipulacao",
    "adulteracao",
    "laudo",
    "exame pericial",
)

_LEGAL_EXTRA = (
    "oficio",
    "despacho",
    "informacao",
    "manifestacao",
    "resposta",
    "documento",
    "historico",
    "cronologia",
    "diligencia",
    "banco",
    "contrato",
    "email",
)


def expand_query(
    query: str,
    *,
    project_memory: str = "",
    intent: str = "",
    max_extra_terms: int = 6,
) -> str:
    """Anexa termos relacionados quando a pergunta toca dominio forense/literal."""
    base = (query or "").strip()
    if not base:
        return base
    lowered = base.lower()
    forensic_intents = {
        "forense_autenticidade",
        "cadeia_custodia",
        "literal_exaustivo",
        "auditoria_exaustiva",
    }
    analytical_intents = {
        "analitico",
        "padrao",
        "tese_acusacao_defesa",
        "historico_documental",
    }
    should_expand = (
        any(t in lowered for t in _FORENSIC_EXTRA)
        or any(t in lowered for t in _LEGAL_EXTRA)
        or intent in forensic_intents
        or intent in analytical_intents
    )
    if not should_expand:
        return base

    extras: list[str] = []
    domain_terms = _FORENSIC_EXTRA if intent in forensic_intents else _LEGAL_EXTRA + _FORENSIC_EXTRA
    domain_cap = max(2, max_extra_terms // 2)
    for term in domain_terms:
        if term in lowered:
            continue
        if len(extras) >= domain_cap:
            break
        extras.append(term)

    if project_memory:
        for token in re.findall(r"[A-Za-zÀ-ÿ]{4,}", project_memory):
            tl = token.lower()
            if tl in lowered or len(extras) >= max_extra_terms:
                continue
            if len(token) > 5 and token[0].isupper():
                extras.append(token)
                if len(extras) >= max_extra_terms:
                    break

    if not extras:
        return base
    return base + " " + " ".join(extras)
