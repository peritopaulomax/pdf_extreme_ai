"""Resumo rolante do historico de conversa para caber no token_limit da Memory."""

from __future__ import annotations

import re
from typing import Any

_SUMMARY_USER_PREFIX = "[Resumo da conversa anterior — use como contexto, nao repita verbatim]"
_SUMMARY_ASSISTANT_ACK = (
    "Entendido. Continuarei a partir desse resumo e das mensagens recentes abaixo."
)


def _count_turns(messages: list[dict[str, Any]]) -> int:
    return sum(1 for m in messages if str(m.get("role", "")).strip().lower() == "user")


def _split_recent(messages: list[dict[str, Any]], recent_turns: int) -> tuple[list[dict], list[dict]]:
    """Separa mensagens antigas das recent_turns ultimas rodadas (user+assistant)."""
    if recent_turns <= 0:
        return list(messages), []
    turns_seen = 0
    split_idx = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        if str(messages[i].get("role", "")).strip().lower() == "user":
            turns_seen += 1
            if turns_seen >= recent_turns:
                split_idx = i
                break
    return messages[:split_idx], messages[split_idx:]


def _format_turns_for_summary(messages: list[dict[str, Any]], *, max_chars: int = 12000) -> str:
    lines: list[str] = []
    used = 0
    for msg in messages:
        role = str(msg.get("role", "")).strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = re.sub(r"\s+", " ", str(msg.get("content", "") or "").strip())
        if not content:
            continue
        label = "Usuario" if role == "user" else "Assistente"
        chunk = f"{label}: {content[:1500]}"
        if used + len(chunk) > max_chars:
            lines.append("... [historico truncado]")
            break
        lines.append(chunk)
        used += len(chunk)
    return "\n".join(lines)


def _heuristic_summary(messages: list[dict[str, Any]]) -> str:
    body = _format_turns_for_summary(messages)
    if not body:
        return ""
    return (
        "Pontos discutidos anteriormente (resumo automatico):\n"
        f"{body}\n"
        "- Preserve numeros de processo, oficios, paginas e nomes citados acima.\n"
        "- Nas proximas respostas, foque no pedido novo sem repetir blocos longos ja entregues."
    )


def _llm_summarize(llm, messages: list[dict[str, Any]]) -> str:
    transcript = _format_turns_for_summary(messages, max_chars=14000)
    if not transcript:
        return ""
    prompt = (
        "Voce resume uma conversa juridica anterior em portugues do Brasil.\n"
        "Regras:\n"
        "- Maximo 12 bullet points objetivos.\n"
        "- Preserve LITERALMENTE: numeros de oficio, despacho, processo, datas, nomes, fls./paginas.\n"
        "- Nao invente fatos; so o que aparece no historico.\n"
        "- Indique temas ja respondidos para evitar repeticao.\n\n"
        f"Historico:\n{transcript}\n\n"
        "Resumo:"
    )
    try:
        resp = llm.complete(prompt)
        text = str(getattr(resp, "text", resp) or "").strip()
        return text or _heuristic_summary(messages)
    except Exception:
        return _heuristic_summary(messages)


def compress_messages_for_memory(
    messages: list[dict[str, Any]],
    *,
    recent_turns: int = 6,
    summarize_threshold_turns: int = 8,
    llm=None,
) -> list[dict[str, Any]]:
    """
    Mantem as ultimas `recent_turns` rodadas literais e resume o restante em um par sintetico.
    """
    if not messages:
        return []
    turns = _count_turns(messages)
    if turns <= summarize_threshold_turns:
        return list(messages)

    older, recent = _split_recent(messages, recent_turns)
    if not older:
        return list(messages)

    summary = _llm_summarize(llm, older) if llm is not None else _heuristic_summary(older)
    if not summary.strip():
        return list(messages)

    compressed = [
        {"role": "user", "content": f"{_SUMMARY_USER_PREFIX}\n{summary}"},
        {"role": "assistant", "content": _SUMMARY_ASSISTANT_ACK},
    ]
    return compressed + list(recent)
