"""Recuperacao lexical ampla para modo auditoria."""

from __future__ import annotations

from dataclasses import dataclass

from retrieval_lexical import LexicalHit, LexicalIndex


@dataclass
class PageOccurrence:
    source_file: str
    page: int
    hit_count: int
    snippets: list[str]
    max_score: float


def search_exhaustive(
    lexical_index: LexicalIndex,
    query: str,
    *,
    batch_size: int = 500,
    max_total: int = 2000,
    page_filter: int | None = None,
    page_range: tuple[int, int] | None = None,
    source_hint: str | None = None,
) -> tuple[list[LexicalHit], list[PageOccurrence]]:
    """Varre FTS em lotes e agrupa por pagina."""
    all_hits: list[LexicalHit] = []
    offset = 0
    while len(all_hits) < max_total:
        batch = lexical_index.search_paginated(
            query,
            limit=batch_size,
            offset=offset,
            page_filter=page_filter,
            page_range=page_range,
            source_hint=source_hint,
        )
        if not batch:
            break
        all_hits.extend(batch)
        if len(batch) < batch_size:
            break
        offset += batch_size
    all_hits = all_hits[:max_total]

    by_page: dict[tuple[str, int], PageOccurrence] = {}
    for hit in all_hits:
        key = (hit.source_file, hit.page)
        occ = by_page.get(key)
        snippet = (hit.window_text or hit.text or "")[:280]
        if occ is None:
            by_page[key] = PageOccurrence(
                source_file=hit.source_file,
                page=hit.page,
                hit_count=1,
                snippets=[snippet] if snippet else [],
                max_score=hit.score,
            )
        else:
            occ.hit_count += 1
            occ.max_score = max(occ.max_score, hit.score)
            if snippet and len(occ.snippets) < 3:
                occ.snippets.append(snippet)
    pages = sorted(by_page.values(), key=lambda p: (-p.hit_count, -p.max_score))
    return all_hits, pages


def format_audit_context(pages: list[PageOccurrence], *, max_pages: int = 40) -> str:
    lines: list[str] = []
    for occ in pages[:max_pages]:
        lines.append(
            f"- {occ.source_file} | pag. {occ.page} | ocorrencias={occ.hit_count} | score={occ.max_score:.3f}"
        )
        for snip in occ.snippets:
            lines.append(f"  > {snip}")
    if len(pages) > max_pages:
        lines.append(f"... (+{len(pages) - max_pages} paginas omitidas no resumo)")
    return "\n".join(lines)
