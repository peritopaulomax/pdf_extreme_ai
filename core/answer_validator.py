from __future__ import annotations

from dataclasses import dataclass

from retrieval_pipeline import RetrievalDiagnostics


@dataclass
class ValidationResult:
    ok: bool
    level: str
    issues: list[str]
    should_retry: bool
    retry_hint: str | None


_NO_MENTION_PATTERNS = (
    "nao ha mencao",
    "não há menção",
    "nao foram encontradas mencoes",
    "não foram encontradas menções",
    "nao foi possivel determinar",
    "não foi possível determinar",
)

_PAGE_ABSENCE_PATTERNS = (
    "nao foi possivel encontrar",
    "não foi possível encontrar",
    "pagina nao encontrada",
    "página não encontrada",
    "nao encontrei",
    "não encontrei",
)


def _has_basic_citation(answer: str) -> bool:
    lowered = answer.lower()
    return "[" in answer and "]" in answer and ("pag" in lowered or "fls" in lowered)


def _answer_denies_mentions(lowered: str) -> bool:
    return any(p in lowered for p in _NO_MENTION_PATTERNS)


def _answer_denies_page(lowered: str) -> bool:
    return any(p in lowered for p in _PAGE_ABSENCE_PATTERNS)


def _build_retry_hint(diagnostics: RetrievalDiagnostics | None, issues: list[str]) -> str | None:
    if not issues:
        return None
    if diagnostics and diagnostics.requested_page is not None:
        return (
            f"Refaca com foco exaustivo na pagina {diagnostics.requested_page}: "
            "forneca trechos literais somente dessa pagina, com citacao [arquivo, pag]. "
            "Se nao houver trecho, diga explicitamente que nao houve hits dessa pagina."
        )
    if diagnostics and diagnostics.plan.intent in ("analitico", "padrao") and diagnostics.fused_count < 3:
        return (
            "A busca retornou poucos trechos (fused baixo). Reexamine o contexto recuperado, "
            "cite o que existir e indique lacunas sem afirmar ausencia total."
        )
    if any("nao citou" in i.lower() for i in issues):
        return (
            "Reformule com citacao obrigatoria: cada fato relevante deve ter [display_name ou source_file, fls./pag.]. "
            "Se o contexto for insuficiente, diga o que falta em vez de generalizar."
        )
    return (
        "Refaca com foco exaustivo: liste total de ocorrencias, paginas e trechos "
        "curtos com citacao [arquivo, pag]."
    )


_SUMMARY_QUERY_MARKERS = (
    "resumo",
    "resume",
    "sintese",
    "síntese",
    "sintetize",
    "sintetiza",
    "estruture",
    "estruturado",
    "panorama",
    "visao geral",
    "visão geral",
    "linha do tempo",
    "cronologia",
)


def _is_summary_query(user_query: str | None) -> bool:
    lowered = (user_query or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in _SUMMARY_QUERY_MARKERS)


def validate_answer(
    answer: str,
    diagnostics: RetrievalDiagnostics | None,
    validation_level: str,
    user_query: str | None = None,
) -> ValidationResult:
    issues: list[str] = []
    lowered = (answer or "").lower()
    has_citation = _has_basic_citation(answer)
    if validation_level in ("light", "strong") and not has_citation:
        issues.append("Resposta sem citacoes explicitas de pagina/arquivo.")
        if (
            diagnostics is not None
            and diagnostics.fused_count >= 3
            and diagnostics.plan.intent
            not in ("literal_exaustivo", "auditoria_exaustiva")
        ):
            issues.append(
                "Havia trechos recuperados (fused>=3), mas a resposta nao citou [arquivo, fls./pag.]."
            )

    if diagnostics is not None:
        literal_sensitive = (
            diagnostics.plan.needs_literal_count
            or diagnostics.plan.intent
            in (
                "forense_autenticidade",
                "cadeia_custodia",
                "literal_exaustivo",
                "auditoria_exaustiva",
            )
        )
        if diagnostics.literal_count > 0 and literal_sensitive:
            if _answer_denies_mentions(lowered):
                issues.append(
                    "Resposta disse que nao ha mencoes, mas a busca lexical encontrou ocorrencias."
                )
        if diagnostics.requested_page is not None and diagnostics.literal_count > 0:
            if _answer_denies_page(lowered):
                issues.append(
                    "Resposta negou conteudo da pagina solicitada, mas houve ocorrencias recuperadas nessa pagina."
                )

        if validation_level == "strong":
            if diagnostics.plan.needs_exhaustive and diagnostics.fused_count < 5:
                issues.append("Cobertura baixa para consulta exaustiva.")
            if (
                diagnostics.plan.needs_literal_count
                and "total" not in lowered
                and not _is_summary_query(user_query)
            ):
                issues.append("Consulta literal exaustiva sem total de ocorrencias no texto.")
            if diagnostics.requested_page_range is not None and diagnostics.literal_count == 0:
                issues.append("Consulta por faixa de paginas sem ocorrencias recuperadas.")

        if validation_level == "light":
            if diagnostics.literal_count > 0 and _answer_denies_mentions(lowered):
                if "Resposta disse que nao ha mencoes" not in " ".join(issues):
                    issues.append(
                        "Resposta disse que nao ha mencoes, mas a busca lexical encontrou ocorrencias."
                    )
            if diagnostics.plan.intent in ("analitico", "padrao") and diagnostics.fused_count < 3:
                issues.append("Cobertura baixa (fused < 3) para esta pergunta.")

    low_coverage_on_light = (
        validation_level == "light"
        and diagnostics is not None
        and diagnostics.plan.intent in ("analitico", "padrao", "historico_documental")
        and diagnostics.fused_count < 3
    )
    missing_citation_with_context = (
        validation_level in ("light", "strong")
        and not has_citation
        and diagnostics is not None
        and diagnostics.fused_count >= 3
        and diagnostics.plan.intent
        not in ("literal_exaustivo", "auditoria_exaustiva")
    )
    retry_on_light = validation_level == "light" and (
        any("nao ha mencoes" in i or "negou conteudo" in i for i in issues)
        or low_coverage_on_light
        or missing_citation_with_context
    )
    should_retry = bool(issues) and (
        validation_level == "strong" or retry_on_light
    )
    hint = _build_retry_hint(diagnostics, issues) if should_retry else None
    return ValidationResult(
        ok=not issues,
        level=validation_level,
        issues=issues,
        should_retry=should_retry,
        retry_hint=hint,
    )


def build_retry_prompt(user_query: str, validation: ValidationResult) -> str:
    if not validation.retry_hint:
        return user_query
    return (
        f"{user_query}\n\n"
        "INSTRUCAO EXTRA DE VALIDACAO:\n"
        f"- {validation.retry_hint}\n"
        "- Se houver ocorrencias, nao afirmar ausencia de mencao.\n"
    )
