"""Sintese map-reduce para perguntas analiticas amplas (panorama, cronologia, resumo)."""

from __future__ import annotations

from llama_index.core.schema import MetadataMode, NodeWithScore

from query_planner import QueryPlan


_ANALYTICAL_INTENTS = (
    "analitico",
    "historico_documental",
    "tese_acusacao_defesa",
    "padrao",
)

_SUMMARY_MARKERS = (
    "resumo",
    "resume",
    "sintese",
    "síntese",
    "sintetize",
    "panorama",
    "visao geral",
    "visão geral",
    "linha do tempo",
    "cronologia",
    "historico",
    "histórico",
    "explique o caso",
    "analise o caso",
    "analise geral",
    "descreva o caso",
    "estruture",
    "panorama do caso",
)


def _has_summary_marker(query: str) -> bool:
    lowered = (query or "").strip().lower()
    return any(m in lowered for m in _SUMMARY_MARKERS)


def should_run_analytical_synthesis(
    prompt: str,
    plan: QueryPlan,
    *,
    enabled: bool = True,
) -> bool:
    """Map-reduce analitico para perguntas amplas (nao substitui auditoria literal)."""
    if not enabled:
        return False
    if plan.intent in ("literal_exaustivo", "auditoria_exaustiva"):
        return False
    if plan.intent in _ANALYTICAL_INTENTS or _has_summary_marker(prompt):
        return True
    return False


def _format_chunk(item: NodeWithScore, *, max_chars: int = 900) -> str:
    node = item.node
    meta = getattr(node, "metadata", None) or {}
    source = str(meta.get("display_name") or meta.get("source_file") or "?")
    page = meta.get("page", "?")
    text = node.get_content(metadata_mode=MetadataMode.NONE).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    return f"[{source}, fls./pag. {page}]\n{text}"


def _batch_nodes(nodes: list[NodeWithScore], batch_size: int) -> list[list[NodeWithScore]]:
    batches: list[list[NodeWithScore]] = []
    for i in range(0, len(nodes), batch_size):
        batches.append(nodes[i : i + batch_size])
    return batches


def _llm_complete(llm, prompt: str) -> str:
    resp = llm.complete(prompt)
    return str(getattr(resp, "text", resp) or "").strip()


def run_analytical_synthesis(
    llm,
    user_query: str,
    nodes: list[NodeWithScore],
    *,
    chunks_per_batch: int = 6,
    max_batches: int = 10,
    progress_callback=None,
) -> str:
    """Sintetiza lotes de trechos recuperados para perguntas analiticas amplas."""
    if not nodes:
        return (
            "Nao foram recuperados trechos relevantes nos documentos indexados para esta pergunta. "
            "Tente refinar o pedido (peca, periodo ou fls.) ou ative o perfil Pericial."
        )

    batches = _batch_nodes(nodes, max(1, chunks_per_batch))[:max_batches]
    partials: list[str] = []
    for i, batch in enumerate(batches, start=1):
        if progress_callback:
            progress_callback(i, len(batches), "lote")
        ctx = "\n\n---\n\n".join(_format_chunk(item) for item in batch)
        partial_prompt = (
            f"Pergunta do usuario: {user_query}\n\n"
            f"Lote {i}/{len(batches)} — trechos dos autos:\n{ctx}\n\n"
            "Extraia fatos deste lote com citacao [arquivo, fls./pag.] em cada afirmacao relevante. "
            "Nao generalize sem citar. Se o lote nao cobrir o tema, diga o que falta."
        )
        partials.append(_llm_complete(llm, partial_prompt))

    if progress_callback:
        progress_callback(len(batches), len(batches), "consolidacao")

    merge_prompt = (
        f"Pergunta: {user_query}\n\n"
        "Analises parciais por lote:\n"
        + "\n---\n".join(partials)
        + "\n\nConsolide em UMA resposta em portugues:\n"
        "- Use secoes claras (fatos, partes, cronologia, pericias, etc.) conforme o pedido.\n"
        "- TODA afirmacao relevante deve ter citacao [arquivo, fls./pag.].\n"
        "- Nao repita o mesmo fato; integre sem duplicar.\n"
        "- Se a cobertura for parcial, declare explicitamente as lacunas.\n"
        "- Nao invente conteudo fora dos lotes."
    )
    return _llm_complete(llm, merge_prompt)
