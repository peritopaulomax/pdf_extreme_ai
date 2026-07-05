"""Sintese map-reduce para modo auditoria (muitas paginas recuperadas)."""

from __future__ import annotations

from exhaustive_retrieval import PageOccurrence, format_audit_context


def _batch_pages(pages: list[PageOccurrence], batch_size: int) -> list[list[PageOccurrence]]:
    batches: list[list[PageOccurrence]] = []
    for i in range(0, len(pages), batch_size):
        batches.append(pages[i : i + batch_size])
    return batches


def _llm_complete(llm, prompt: str) -> str:
    resp = llm.complete(prompt)
    return str(getattr(resp, "text", resp) or "").strip()


def run_audit_synthesis(
    llm,
    user_query: str,
    pages: list[PageOccurrence],
    *,
    pages_per_batch: int = 12,
    max_batches: int = 8,
    progress_callback=None,
) -> str:
    """Resume lotes de paginas e produz resposta final com citacoes."""
    if not pages:
        return (
            "Nao foram encontradas ocorrencias lexicais para esta consulta nos documentos indexados."
        )
    batches = _batch_pages(pages, pages_per_batch)[:max_batches]
    partials: list[str] = []
    for i, batch in enumerate(batches, start=1):
        if progress_callback:
            progress_callback(i, len(batches), "lote")
        ctx = format_audit_context(batch, max_pages=len(batch))
        partial_prompt = (
            f"Pergunta do usuario: {user_query}\n\n"
            f"Lote {i}/{len(batches)} — ocorrencias por pagina:\n{ctx}\n\n"
            "Liste ocorrencias deste lote com [arquivo, pag] e trechos curtos. "
            "Inclua contagem por pagina quando possivel."
        )
        partials.append(_llm_complete(llm, partial_prompt))

    if progress_callback:
        progress_callback(len(batches), len(batches), "consolidacao")
    merge_prompt = (
        f"Pergunta: {user_query}\n\n"
        "Resumos parciais da varredura:\n"
        + "\n---\n".join(partials)
        + "\n\nConsolide em resposta unica: total estimado de paginas com ocorrencia, "
        "lista por documento/pagina, trechos literais curtos com [arquivo, pag]. "
        "Nao afirme ausencia se os lotes mostraram ocorrencias."
    )
    return _llm_complete(llm, merge_prompt)
