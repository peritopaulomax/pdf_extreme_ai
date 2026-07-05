import re
from dataclasses import dataclass

from runtime_config import RuntimeSettings


@dataclass
class QueryPlan:
    intent: str
    profile: str
    needs_exhaustive: bool
    needs_literal_count: bool
    requested_page: int | None
    requested_page_range: tuple[int, int] | None
    requested_source_hint: str | None
    requested_section: str | None
    reason: str


AUDIT_TRIGGERS = (
    "varredura",
    "auditoria",
    "modo auditoria",
    "exaustivo",
    "exaustiva",
    "todas as ocorrencias",
    "todas as ocorrências",
)

NARRATIVE_TRIGGERS = (
    "historico",
    "histórico",
    "cronologia",
    "cronologico",
    "cronológico",
    "linha do tempo",
    "narrativa",
    "movimentacao",
    "movimentação",
    "desdobramento",
    "desdobramentos",
    "nexo causal",
    "nexos causais",
)

DOC_TRIGGERS = (
    "oficio",
    "ofício",
    "despacho",
    "informacao",
    "informação",
    "parecer",
    "termo de declaracoes",
    "termo de declarações",
    "manifestacao",
    "manifestação",
    "correio eletronico",
    "correio eletrônico",
    "e mail",
    "email",
)

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

FORENSIC_TRIGGERS = (
    "autenticidade",
    "autentico",
    "autêntico",
    "integridade",
    "originalidade",
    "original",
    "manipulacao",
    "manipulação",
    "adulteracao",
    "adulteração",
    "edicao",
    "edição",
    "deepfake",
    "audio",
    "áudio",
    "video",
    "vídeo",
    "imagem",
    "documento digital",
)

CUSTODY_TRIGGERS = (
    "cadeia de custodia",
    "cadeia de custódia",
    "quebra da cadeia",
    "lacre",
    "hash",
    "coleta",
    "preservacao",
    "preservação",
)

THESIS_TRIGGERS = (
    "acusacao",
    "acusação",
    "defesa",
    "alegacao",
    "alegação",
    "hipotese",
    "hipótese",
)

SECTION_HINTS: dict[str, tuple[str, ...]] = {
    "titulo": ("titulo", "título", "title", "capa", "autores", "keywords", "abstract", "resumo"),
    "metodologia": ("metodo", "método", "metodologia", "materiais e metodos", "materials and methods"),
    "conclusao": ("conclusao", "conclusão", "consideracoes finais", "considerações finais"),
    "introducao": ("introducao", "introdução", "contexto"),
    "cadeia_custodia": ("cadeia de custodia", "cadeia de custódia", "lacre", "hash"),
}


_PAGE_PATTERNS = (
    r"\bpag(?:ina|inas)?\.?\s*(\d{1,4})\b",
    r"\bp[aá]g(?:ina|inas)?\.?\s*(\d{1,4})\b",
    r"\bpage\s*(\d{1,4})\b",
    r"\bfls?\.?\s*(\d{1,4})\b",
)

_PAGE_RANGE_PATTERNS = (
    r"\b(?:pag(?:ina|inas)?|p[aá]g(?:ina|inas)?|page|fls?)\.?\s*(\d{1,4})\s*(?:-|a|ate|até)\s*(\d{1,4})\b",
)

_SOURCE_HINT_PATTERN = r"([a-z0-9][a-z0-9._-]*\.pdf)"


def _extract_requested_page(query: str) -> int | None:
    lowered = (query or "").strip().lower()
    for pattern in _PAGE_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            try:
                page = int(match.group(1))
                if page > 0:
                    return page
            except Exception:
                return None
    return None


def _extract_page_range(query: str) -> tuple[int, int] | None:
    lowered = (query or "").strip().lower()
    for pattern in _PAGE_RANGE_PATTERNS:
        match = re.search(pattern, lowered)
        if not match:
            continue
        try:
            start = int(match.group(1))
            end = int(match.group(2))
            if start <= 0 or end <= 0:
                continue
            if start > end:
                start, end = end, start
            return start, end
        except Exception:
            return None
    return None


def _extract_source_hint(query: str) -> str | None:
    lowered = (query or "").strip().lower()
    match = re.search(_SOURCE_HINT_PATTERN, lowered)
    if match:
        return match.group(1)
    return None


def _extract_section_hint(query: str) -> str | None:
    lowered = (query or "").strip().lower()
    for key, markers in SECTION_HINTS.items():
        if any(marker in lowered for marker in markers):
            return key
    return None


def plan_query(query: str, settings: RuntimeSettings, forced_profile: str | None = None) -> QueryPlan:
    lowered = (query or "").strip().lower()
    requested_page = _extract_requested_page(lowered)
    requested_page_range = _extract_page_range(lowered)
    requested_source_hint = _extract_source_hint(lowered)
    requested_section = _extract_section_hint(lowered)
    if requested_page_range and requested_page is None:
        requested_page = requested_page_range[0]
    if forced_profile in ("rapido", "preciso", "pericial"):
        profile = forced_profile
        intent = "manual"
    elif settings.planner_mode == "manual":
        profile = settings.retrieval_profile_default
        intent = "manual"
    elif any(t in lowered for t in CUSTODY_TRIGGERS):
        profile = "pericial"
        intent = "cadeia_custodia"
    elif any(t in lowered for t in FORENSIC_TRIGGERS):
        profile = "pericial"
        intent = "forense_autenticidade"
    elif any(t in lowered for t in THESIS_TRIGGERS):
        profile = "preciso"
        intent = "tese_acusacao_defesa"
    elif any(t in lowered for t in AUDIT_TRIGGERS):
        profile = "pericial"
        intent = "auditoria_exaustiva"
    elif any(t in lowered for t in NARRATIVE_TRIGGERS) and any(t in lowered for t in DOC_TRIGGERS):
        profile = "pericial"
        intent = "historico_documental"
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

    needs_literal_count = intent in (
        "literal_exaustivo",
        "auditoria_exaustiva",
        "cadeia_custodia",
        "forense_autenticidade",
    )
    needs_exhaustive = profile == "pericial" or needs_literal_count
    if requested_page_range is not None:
        needs_exhaustive = True
        if profile == "rapido":
            profile = "preciso"
    return QueryPlan(
        intent=intent,
        profile=profile,
        needs_exhaustive=needs_exhaustive,
        needs_literal_count=needs_literal_count,
        requested_page=requested_page,
        requested_page_range=requested_page_range,
        requested_source_hint=requested_source_hint,
        requested_section=requested_section,
        reason=(
            f"profile={profile}; intent={intent}; page={requested_page or '-'}; "
            f"range={requested_page_range or '-'}; source={requested_source_hint or '-'}; "
            f"section={requested_section or '-'}"
        ),
    )
