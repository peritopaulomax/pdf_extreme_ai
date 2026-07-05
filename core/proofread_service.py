"""Servico de correcao ortografica via LLM (JSON estruturado)."""

from __future__ import annotations

import html
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from typing import Any

from proofread_prompts import PROOFREAD_SYSTEM_PROMPT, build_proofread_user_message


@dataclass
class ProofreadBlock:
    index: int
    total: int
    text: str


def _extract_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _normalize_result(data: dict[str, Any], original: str) -> dict[str, Any]:
    corrected = str(data.get("corrected_text") or original).strip()
    changes_raw = data.get("changes") or []
    changes: list[dict[str, str]] = []
    if isinstance(changes_raw, list):
        for item in changes_raw:
            if not isinstance(item, dict):
                continue
            orig = str(item.get("original") or "").strip()
            corr = str(item.get("corrected") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if orig or corr:
                changes.append(
                    {"original": orig, "corrected": corr, "reason": reason or "—"}
                )
    return {
        "corrected_text": corrected or original,
        "source_text": original,
        "changes": changes,
        "raw_fallback": False,
    }


@contextmanager
def _proofread_generation_options(llm):
    inner = getattr(llm, "llm", llm)
    old_thinking = getattr(inner, "thinking", None)
    model_kwargs = getattr(inner, "_model_kwargs", None)
    old_option_values: dict[str, Any] = {}
    if old_thinking is not None:
        inner.thinking = False
    if isinstance(model_kwargs, dict):
        for key, value in {"temperature": 0.2, "top_p": 0.9}.items():
            old_option_values[key] = model_kwargs.get(key)
            model_kwargs.setdefault(key, value)
    try:
        yield
    finally:
        if old_thinking is not None:
            inner.thinking = old_thinking
        if isinstance(model_kwargs, dict):
            for key, value in old_option_values.items():
                if value is None:
                    model_kwargs.pop(key, None)
                else:
                    model_kwargs[key] = value


def split_proofread_blocks(text: str, *, max_block_chars: int = 2500) -> list[ProofreadBlock]:
    source = (text or "").strip()
    if not source:
        return []
    parts = [p.strip() for p in re.split(r"\n\s*\n", source) if p.strip()]
    if not parts:
        parts = [source]

    blocks: list[str] = []
    current = ""
    for part in parts:
        if len(part) > max_block_chars:
            if current:
                blocks.append(current)
                current = ""
            sentences = re.split(r"(?<=[.!?;:])\s+", part)
            chunk = ""
            for sentence in sentences:
                if chunk and len(chunk) + 1 + len(sentence) > max_block_chars:
                    blocks.append(chunk.strip())
                    chunk = sentence
                else:
                    chunk = f"{chunk} {sentence}".strip()
            if chunk:
                blocks.append(chunk.strip())
            continue
        candidate = f"{current}\n\n{part}".strip() if current else part
        if current and len(candidate) > max_block_chars:
            blocks.append(current)
            current = part
        else:
            current = candidate
    if current:
        blocks.append(current)
    total = len(blocks)
    return [ProofreadBlock(index=i + 1, total=total, text=block) for i, block in enumerate(blocks)]


def _run_proofread_block(llm, text: str) -> dict[str, Any]:
    source = (text or "").strip()
    from llama_index.core.llms import ChatMessage, MessageRole

    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=PROOFREAD_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=build_proofread_user_message(source)),
    ]
    try:
        with _proofread_generation_options(llm):
            resp = llm.chat(messages)
        raw = ""
        if hasattr(resp, "message"):
            msg = resp.message
            content = getattr(msg, "content", None)
            if content is not None:
                raw = str(content)
            else:
                blocks = getattr(msg, "blocks", None)
                if blocks:
                    raw = "".join(
                        str(getattr(b, "text", b)) for b in blocks if getattr(b, "text", None)
                    )
                else:
                    raw = str(msg)
        else:
            raw = str(resp)
    except Exception as exc:
        return {
            "corrected_text": "",
            "changes": [],
            "error": f"Falha ao consultar o modelo: {exc}",
        }

    parsed = _extract_json(raw)
    if parsed:
        out = _normalize_result(parsed, source)
        out["error"] = None
        return out

    return {
        "corrected_text": source,
        "source_text": source,
        "changes": [],
        "error": None,
        "raw_fallback": True,
        "raw_response": raw,
    }


def run_proofread(llm, text: str, *, max_chars: int = 12000) -> dict[str, Any]:
    source = (text or "").strip()
    if not source:
        return {
            "corrected_text": "",
            "changes": [],
            "error": "Informe um texto para corrigir.",
        }
    if len(source) > max_chars:
        return {
            "corrected_text": "",
            "changes": [],
            "error": f"Texto excede o limite de {max_chars} caracteres.",
        }

    blocks = split_proofread_blocks(source)
    if len(blocks) <= 1:
        return _run_proofread_block(llm, source)

    corrected_parts: list[str] = []
    changes: list[dict[str, str]] = []
    raw_fallback = False
    raw_responses: list[str] = []
    for block in blocks:
        result = _run_proofread_block(llm, block.text)
        if result.get("error"):
            return result
        corrected_parts.append(str(result.get("corrected_text") or block.text))
        changes.extend(list(result.get("changes") or []))
        if result.get("raw_fallback"):
            raw_fallback = True
            if result.get("raw_response"):
                raw_responses.append(str(result.get("raw_response")))
    return {
        "corrected_text": "\n\n".join(corrected_parts),
        "source_text": source,
        "changes": changes,
        "error": None,
        "raw_fallback": raw_fallback,
        "raw_response": "\n\n".join(raw_responses) if raw_responses else None,
    }


def iter_proofread_blocks(llm, text: str, *, max_chars: int = 12000) -> Iterator[dict[str, Any]]:
    source = (text or "").strip()
    if not source:
        yield {
            "event": "error",
            "message": "Informe um texto para corrigir.",
        }
        return
    if len(source) > max_chars:
        yield {
            "event": "error",
            "message": f"Texto excede o limite de {max_chars} caracteres.",
        }
        return

    blocks = split_proofread_blocks(source)
    yield {"event": "start", "total_blocks": len(blocks)}
    for block in blocks:
        yield {
            "event": "status",
            "message": f"Corrigindo bloco {block.index}/{block.total}...",
            "block_index": block.index,
            "total_blocks": block.total,
        }
        result = _run_proofread_block(llm, block.text)
        if result.get("error"):
            yield {
                "event": "error",
                "message": str(result.get("error")),
                "block_index": block.index,
            }
            return
        yield {
            "event": "block",
            "block_index": block.index,
            "total_blocks": block.total,
            "source_text": block.text,
            "corrected_text": str(result.get("corrected_text") or block.text),
            "changes": list(result.get("changes") or []),
            "raw_fallback": bool(result.get("raw_fallback")),
            "raw_response": result.get("raw_response"),
        }
    yield {"event": "done"}


_HIGHLIGHT_CORRECTION = (
    '<span style="background-color:#fff59d;color:#000000;font-weight:700;">{inner}</span>'
)
_HIGHLIGHT_CONTEXT = '<span style="background-color:#fff59d;">{inner}</span>'
_WORD_RE = re.compile(r"\b[\wÀ-ÿ]+\b", re.UNICODE)


def _neighbor_words(text: str, start: int, end: int) -> tuple[str | None, str | None]:
    before = text[:start]
    after = text[end:]
    before_words = _WORD_RE.findall(before)
    after_words = _WORD_RE.findall(after)
    wb = before_words[-1] if before_words else None
    wa = after_words[0] if after_words else None
    return wb, wa


def _wrap_phrase_once(text: str, phrase: str, wrapper: str) -> str:
    if not phrase or phrase not in text:
        return text
    escaped = re.escape(phrase)
    return re.sub(escaped, wrapper.format(inner=phrase), text, count=1)


def _wrap_word_once(text: str, word: str, wrapper: str) -> str:
    if not word:
        return text
    pattern = rf"\b({re.escape(word)})\b"
    return re.sub(pattern, lambda m: wrapper.format(inner=m.group(1)), text, count=1)


def build_highlighted_html(
    corrected: str,
    source: str,
    changes: list[dict[str, str]],
) -> str:
    """
    Texto corrigido em HTML: correcoes em negrito + fundo amarelo.
    Supressoes: palavras imediatamente antes/depois no texto corrigido em amarelo.
    """
    text = html.escape(corrected or "")
    if not text:
        return ""

    corrections: list[str] = []
    context_words: list[str] = []

    for ch in changes:
        orig = str(ch.get("original") or "").strip()
        corr = str(ch.get("corrected") or "").strip()
        if corr:
            corrections.append(corr)
        elif orig and source:
            pos = source.find(orig)
            if pos < 0:
                pos = source.lower().find(orig.lower())
            if pos >= 0:
                wb, wa = _neighbor_words(source, pos, pos + len(orig))
                if wb:
                    context_words.append(wb)
                if wa:
                    context_words.append(wa)

    corrections.sort(key=len, reverse=True)
    context_words = sorted(set(context_words), key=len, reverse=True)

    for phrase in corrections:
        text = _wrap_phrase_once(text, html.escape(phrase), _HIGHLIGHT_CORRECTION)

    for word in context_words:
        text = _wrap_word_once(text, html.escape(word), _HIGHLIGHT_CONTEXT)

    return f'<div style="line-height:1.6;white-space:pre-wrap;">{text}</div>'
