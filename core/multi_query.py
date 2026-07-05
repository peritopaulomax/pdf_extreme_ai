from __future__ import annotations

from typing import Iterable


def build_multi_queries(query: str, *, intent: str = "", max_queries: int = 4) -> list[str]:
    base = (query or "").strip()
    if not base:
        return []

    variants: list[str] = [base]
    lowered = base.lower()
    if intent in ("analitico", "padrao", "historico_documental", "tese_acusacao_defesa"):
        variants.extend(
            [
                f"{base} histórico cronologia sequência documental",
                f"{base} ofício despacho informação manifestação resposta",
                f"{base} banco contrato e-mail diligência perícia",
            ]
        )
    elif intent in ("literal_exaustivo", "auditoria_exaustiva"):
        variants.extend(
            [
                f"{base} ocorrências páginas trechos literais",
                f"{base} documento página fls ocorrência",
            ]
        )
    elif "oficio" in lowered or "ofício" in lowered or "despacho" in lowered:
        variants.extend(
            [
                f"{base} ofício despacho informação",
                f"{base} resposta banco correio eletrônico",
            ]
        )

    out: list[str] = []
    seen: set[str] = set()
    for item in variants:
        normalized = " ".join(item.split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
        if len(out) >= max_queries:
            break
    return out


def fuse_query_lists(base_query: str, alternatives: Iterable[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in [base_query, *alternatives]:
        normalized = " ".join((item or "").split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged

