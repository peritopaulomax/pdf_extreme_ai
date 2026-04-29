import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

import torch
from qdrant_client import QdrantClient


def normalize_proxy_env() -> None:
    """Normalize proxy env vars to schemes accepted by httpx/ollama."""
    proxy_keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    )
    for key in proxy_keys:
        raw = os.environ.get(key, "")
        value = raw.strip()
        if not value:
            continue
        if value.lower().startswith("socks://"):
            os.environ[key] = f"socks5://{value[len('socks://'):]}"


@dataclass
class RetrievalProfile:
    name: str
    semantic_top_k: int
    lexical_top_k: int
    reranker_candidate_k: int
    reranker_top_n: int
    lexical_weight: float
    semantic_weight: float
    validation_level: str


@dataclass
class RuntimeSettings:
    qdrant_collection: str
    qdrant_hosts: list[str]
    qdrant_port: int
    qdrant_timeout: float
    qdrant_hnsw_m: int
    qdrant_hnsw_ef_construct: int
    qdrant_hnsw_ef: int
    embedding_model_path: str
    reranker_model_path: str
    llm_model: str
    llm_models: list[str]
    llm_default_model: str
    llm_timeout_default: float
    llm_timeout_heavy: float
    ollama_host: str
    chunk_size: int
    chunk_overlap: int
    similarity_top_k: int
    use_reranker: bool
    reranker_top_n: int
    reranker_candidate_k: int
    ingest_batch_files: int
    checkpoint_path: str
    ingest_strategy: str
    sentence_window_size: int
    chat_memory_token_limit: int
    lexical_db_path: str
    planner_mode: str
    retrieval_profile_default: str
    retrieval_profiles: dict[str, RetrievalProfile]
    ui_ingest_max_files: int
    ui_ingest_max_file_mb: int
    projects_registry_path: str


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    return int(value)


def _float_env(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    return float(value)


def _csv_env(name: str, default_csv: str) -> list[str]:
    raw = os.environ.get(name, default_csv)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def _ingest_strategy() -> str:
    raw = os.environ.get("INGEST_STRATEGY", "sentence_window").strip().lower()
    if raw in ("chunks", "flat", "legacy", "simple"):
        return "chunks"
    if raw in ("sentence_window", "window", "janela"):
        return "sentence_window"
    return "sentence_window"


def _planner_mode() -> str:
    raw = os.environ.get("PLANNER_MODE", "auto").strip().lower()
    if raw in ("manual", "fixed"):
        return "manual"
    return "auto"


def _profile_name(raw: str) -> str:
    value = raw.strip().lower()
    if value in ("rapido", "preciso", "pericial"):
        return value
    return "preciso"


def _build_profiles() -> dict[str, RetrievalProfile]:
    rapido = RetrievalProfile(
        name="rapido",
        semantic_top_k=_int_env("PROFILE_RAPIDO_SEMANTIC_TOP_K", 8),
        lexical_top_k=_int_env("PROFILE_RAPIDO_LEXICAL_TOP_K", 10),
        reranker_candidate_k=_int_env("PROFILE_RAPIDO_RERANKER_CANDIDATE_K", 16),
        reranker_top_n=_int_env("PROFILE_RAPIDO_RERANKER_TOP_N", 6),
        lexical_weight=_float_env("PROFILE_RAPIDO_LEXICAL_WEIGHT", 0.30),
        semantic_weight=_float_env("PROFILE_RAPIDO_SEMANTIC_WEIGHT", 0.70),
        validation_level="none",
    )
    preciso = RetrievalProfile(
        name="preciso",
        semantic_top_k=_int_env("PROFILE_PRECISO_SEMANTIC_TOP_K", 14),
        lexical_top_k=_int_env("PROFILE_PRECISO_LEXICAL_TOP_K", 16),
        reranker_candidate_k=_int_env("PROFILE_PRECISO_RERANKER_CANDIDATE_K", 28),
        reranker_top_n=_int_env("PROFILE_PRECISO_RERANKER_TOP_N", 10),
        lexical_weight=_float_env("PROFILE_PRECISO_LEXICAL_WEIGHT", 0.45),
        semantic_weight=_float_env("PROFILE_PRECISO_SEMANTIC_WEIGHT", 0.55),
        validation_level="light",
    )
    pericial = RetrievalProfile(
        name="pericial",
        semantic_top_k=_int_env("PROFILE_PERICIAL_SEMANTIC_TOP_K", 24),
        lexical_top_k=_int_env("PROFILE_PERICIAL_LEXICAL_TOP_K", 40),
        reranker_candidate_k=_int_env("PROFILE_PERICIAL_RERANKER_CANDIDATE_K", 48),
        reranker_top_n=_int_env("PROFILE_PERICIAL_RERANKER_TOP_N", 16),
        lexical_weight=_float_env("PROFILE_PERICIAL_LEXICAL_WEIGHT", 0.60),
        semantic_weight=_float_env("PROFILE_PERICIAL_SEMANTIC_WEIGHT", 0.40),
        validation_level="strong",
    )
    return {"rapido": rapido, "preciso": preciso, "pericial": pericial}


def configure_runtime_env() -> RuntimeSettings:
    normalize_proxy_env()

    no_proxy_set = {"127.0.0.1", "localhost", "::1"}
    for key in ("NO_PROXY", "no_proxy"):
        existing = os.environ.get(key, "")
        if existing.strip():
            no_proxy_set.update(part.strip() for part in existing.split(",") if part.strip())
    no_proxy = ",".join(sorted(no_proxy_set))
    os.environ["NO_PROXY"] = no_proxy
    os.environ["no_proxy"] = no_proxy

    os.environ.setdefault("OMP_NUM_THREADS", "24")
    os.environ.setdefault("MKL_NUM_THREADS", "24")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "24")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "24")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "true")
    try:
        torch.set_num_threads(_int_env("TORCH_NUM_THREADS", 24))
    except RuntimeError:
        pass
    try:
        torch.set_num_interop_threads(_int_env("TORCH_NUM_INTEROP_THREADS", 8))
    except RuntimeError:
        pass

    explicit_host = os.environ.get("QDRANT_HOST", "").strip()
    hosts = [explicit_host] if explicit_host else ["127.0.0.1", "localhost"]

    os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:11434")
    default_model = os.environ.get("OLLAMA_MODEL_DEFAULT", "").strip()
    legacy_model = os.environ.get("OLLAMA_MODEL", "").strip()
    if not default_model:
        default_model = legacy_model or "qwen2.5:7b-instruct"

    model_list = _csv_env(
        "OLLAMA_MODELS",
        "gemma4:e4b,qwen2.5:7b-instruct,gemma4-pericia:latest,deepseek-r1:14b",
    )
    if default_model not in model_list:
        model_list = [default_model] + [model for model in model_list if model != default_model]

    profiles = _build_profiles()
    default_profile = _profile_name(os.environ.get("RETRIEVAL_PROFILE_DEFAULT", "preciso"))

    return RuntimeSettings(
        qdrant_collection=os.environ.get("QDRANT_COLLECTION", "massive_pdf"),
        qdrant_hosts=hosts,
        qdrant_port=_int_env("QDRANT_PORT", 6333),
        qdrant_timeout=_float_env("QDRANT_TIMEOUT", 20.0),
        qdrant_hnsw_m=_int_env("QDRANT_HNSW_M", 32),
        qdrant_hnsw_ef_construct=_int_env("QDRANT_HNSW_EF_CONSTRUCT", 200),
        qdrant_hnsw_ef=_int_env("QDRANT_HNSW_EF", 96),
        embedding_model_path=os.environ.get(
            "EMBEDDING_MODEL_PATH",
            "/home/paulopmgir/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181",
        ),
        reranker_model_path=os.environ.get(
            "RERANKER_MODEL_PATH",
            "/home/paulopmgir/.cache/huggingface/hub/models--BAAI--bge-reranker-base/snapshots/2cfc18c9415c912f9d8155881c133215df768a70",
        ),
        llm_model=default_model,
        llm_models=model_list,
        llm_default_model=default_model,
        llm_timeout_default=_float_env("OLLAMA_TIMEOUT_DEFAULT", 180.0),
        llm_timeout_heavy=_float_env("OLLAMA_TIMEOUT_HEAVY", 600.0),
        ollama_host=os.environ["OLLAMA_HOST"],
        chunk_size=_int_env("CHUNK_SIZE", 700),
        chunk_overlap=_int_env("CHUNK_OVERLAP", 120),
        similarity_top_k=_int_env("SIMILARITY_TOP_K", 14),
        use_reranker=_bool_env("ENABLE_RERANKER", True),
        reranker_top_n=_int_env("RERANKER_TOP_N", 10),
        reranker_candidate_k=_int_env("RERANKER_CANDIDATE_K", 22),
        ingest_batch_files=_int_env("INGEST_BATCH_FILES", 2),
        checkpoint_path=os.environ.get("INGEST_CHECKPOINT", ".ingest_checkpoint.json"),
        ingest_strategy=_ingest_strategy(),
        sentence_window_size=_int_env("SENTENCE_WINDOW_SIZE", 5),
        chat_memory_token_limit=_int_env("CHAT_MEMORY_TOKEN_LIMIT", 10000),
        lexical_db_path=os.environ.get("LEXICAL_DB_PATH", ".lexical_index.db"),
        planner_mode=_planner_mode(),
        retrieval_profile_default=default_profile,
        retrieval_profiles=profiles,
        ui_ingest_max_files=_int_env("UI_INGEST_MAX_FILES", 12),
        ui_ingest_max_file_mb=_int_env("UI_INGEST_MAX_FILE_MB", 512),
        projects_registry_path=os.environ.get("PROJECTS_REGISTRY_PATH", "projects_registry.json"),
    )


def embedding_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def llm_timeout_for_model(settings: RuntimeSettings, model_name: str) -> float:
    lowered = model_name.lower()
    heavy_markers = ("pericia", "26b", "31b", "14b", "32b", "70b")
    if any(marker in lowered for marker in heavy_markers):
        return settings.llm_timeout_heavy
    return settings.llm_timeout_default


def verify_data_dir(data_dir: str) -> list[Path]:
    base = Path(data_dir)
    if not base.exists():
        raise RuntimeError(f"Diretorio de dados nao encontrado: {base}")
    files = sorted(base.glob("*.pdf"))
    if not files:
        raise RuntimeError(f"Nenhum PDF encontrado em: {base}")
    return files


def check_ollama_health(base_url: str, timeout: float = 5.0) -> None:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        with urlopen(url, timeout=timeout) as response:
            if response.status >= 400:
                raise RuntimeError(f"Ollama indisponivel (HTTP {response.status})")
    except URLError as exc:
        raise RuntimeError(f"Nao foi possivel acessar Ollama em {url}: {exc}") from exc


def connect_qdrant(settings: RuntimeSettings) -> tuple[QdrantClient, str]:
    errors: list[str] = []
    for host in settings.qdrant_hosts:
        try:
            client = QdrantClient(
                host=host,
                port=settings.qdrant_port,
                trust_env=False,
                timeout=settings.qdrant_timeout,
            )
            client.get_collections()
            return client, host
        except Exception as exc:  # pragma: no cover
            errors.append(f"{host}:{settings.qdrant_port} -> {type(exc).__name__}: {exc}")
    joined = " | ".join(errors)
    raise RuntimeError(
        "Nao foi possivel conectar ao Qdrant. "
        f"Hosts testados: {settings.qdrant_hosts} porta {settings.qdrant_port}. "
        f"Tentativas: {joined}"
    )


def batched_paths(paths: Iterable[Path], batch_size: int) -> Iterable[list[Path]]:
    batch: list[Path] = []
    for item in paths:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
