"""Enriquecimento automatico da memoria do caso a partir de entidades extraidas na ingestao."""

from __future__ import annotations

from entity_timeline import load_entities


def build_auto_case_context(project_id: str, *, max_entities: int = 24) -> str:
    """Gera bloco compacto de entidades para ancorar retrieval e chat."""
    if not project_id:
        return ""
    entities = load_entities(project_id)
    if not entities:
        return ""

    by_kind: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for item in entities:
        kind = str(item.get("kind") or "outro").strip().lower()
        value = str(item.get("value") or "").strip()
        if not value or len(value) < 3:
            continue
        key = (kind, value.casefold())
        if key in seen:
            continue
        seen.add(key)
        by_kind.setdefault(kind, []).append(value)
        if sum(len(v) for v in by_kind.values()) >= max_entities:
            break

    if not by_kind:
        return ""

    lines = ["Contexto automatico do caso (extraido dos PDFs):"]
    kind_labels = {
        "nome": "Nomes/pessoas",
        "cpf": "CPFs",
        "cnpj": "CNPJs",
    }
    for kind, values in sorted(by_kind.items()):
        label = kind_labels.get(kind, kind.capitalize())
        sample = "; ".join(values[:8])
        if len(values) > 8:
            sample += f" (+{len(values) - 8})"
        lines.append(f"- {label}: {sample}")
    lines.append(
        "- Use como pistas de busca; em conflito com trechos recuperados, prevalecem os documentos."
    )
    return "\n".join(lines)


def enrich_project_memory(project_id: str, manual_text: str) -> str:
    """Combina memoria manual do usuario com contexto automatico de entidades."""
    manual = (manual_text or "").strip()
    auto = build_auto_case_context(project_id).strip()
    if manual and auto:
        return f"{manual}\n\n{auto}"
    return manual or auto
