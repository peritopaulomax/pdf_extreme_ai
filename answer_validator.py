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
)


def _has_basic_citation(answer: str) -> bool:
    # Aceita formatos como [arquivo, fls./pag. X] ou pagina/pág no corpo.
    lowered = answer.lower()
    return "[" in answer and "]" in answer and ("pag" in lowered or "fls" in lowered)


def validate_answer(answer: str, diagnostics: RetrievalDiagnostics | None, validation_level: str) -> ValidationResult:
    issues: list[str] = []
    lowered = (answer or "").lower()
    has_citation = _has_basic_citation(answer)
    if validation_level in ("light", "strong") and not has_citation:
        issues.append("Resposta sem citacoes explicitas de pagina/arquivo.")

    if diagnostics is not None:
        if diagnostics.plan.needs_literal_count and diagnostics.literal_count > 0:
            if any(p in lowered for p in _NO_MENTION_PATTERNS):
                issues.append(
                    "Resposta disse que nao ha mencoes, mas a busca lexical encontrou ocorrencias."
                )

        if validation_level == "strong":
            if diagnostics.plan.needs_exhaustive and diagnostics.fused_count < 5:
                issues.append("Cobertura baixa para consulta exaustiva.")
            if diagnostics.plan.needs_literal_count and "total" not in lowered:
                issues.append("Consulta literal exaustiva sem total de ocorrencias no texto.")

    should_retry = bool(issues) and validation_level == "strong"
    hint = None
    if should_retry:
        hint = (
            "Refaca com foco exaustivo: liste total de ocorrencias, paginas e trechos "
            "curtos com citacao [arquivo, pag]."
        )
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
