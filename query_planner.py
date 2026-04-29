from dataclasses import dataclass

from runtime_config import RuntimeSettings


@dataclass
class QueryPlan:
    intent: str
    profile: str
    needs_exhaustive: bool
    needs_literal_count: bool
    reason: str


LITERAL_TRIGGERS = (
    "todas as mencoes",
    "todas as mencoes",
    "onde aparece",
    "quantas vezes",
    "liste todas",
    "listar todas",
    "ocorrencias",
    "ocorrências",
    "palavra",
    "termo exato",
)

ANALYTICAL_TRIGGERS = (
    "explique",
    "analise",
    "analisa",
    "hipotese",
    "hipótese",
    "conclusao",
    "conclusão",
    "defesa",
    "acusacao",
    "acusação",
)


def plan_query(query: str, settings: RuntimeSettings, forced_profile: str | None = None) -> QueryPlan:
    lowered = (query or "").strip().lower()
    if forced_profile in ("rapido", "preciso", "pericial"):
        profile = forced_profile
        intent = "manual"
    elif settings.planner_mode == "manual":
        profile = settings.retrieval_profile_default
        intent = "manual"
    elif any(t in lowered for t in LITERAL_TRIGGERS):
        profile = "pericial"
        intent = "literal_exaustivo"
    elif any(t in lowered for t in ANALYTICAL_TRIGGERS):
        profile = "preciso"
        intent = "analitico"
    elif len(lowered) <= 60:
        profile = "rapido"
        intent = "factual_curta"
    else:
        profile = settings.retrieval_profile_default
        intent = "padrao"

    needs_literal_count = intent == "literal_exaustivo"
    needs_exhaustive = profile == "pericial" or needs_literal_count
    return QueryPlan(
        intent=intent,
        profile=profile,
        needs_exhaustive=needs_exhaustive,
        needs_literal_count=needs_literal_count,
        reason=f"profile={profile}; intent={intent}",
    )
