"""Helpers para estado do indice (Qdrant + lexical) por projeto."""

from __future__ import annotations

import os

from qdrant_client.models import Distance, HnswConfigDiff, VectorParams

from retrieval_lexical import LexicalIndex
from runtime_config import RuntimeSettings, connect_qdrant


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    return int(value)


def embedding_vector_size(_settings: RuntimeSettings | None = None) -> int:
    return _int_env("EMBEDDING_DIM", 1024)


def project_index_counts(settings: RuntimeSettings) -> tuple[int, int]:
    lexical_nodes = LexicalIndex(settings.lexical_db_path).count_nodes()
    vector_points = 0
    try:
        client, _ = connect_qdrant(settings)
        if client.collection_exists(settings.qdrant_collection):
            count_res = client.count(collection_name=settings.qdrant_collection, exact=False)
            vector_points = int(getattr(count_res, "count", 0) or 0)
    except Exception:
        vector_points = 0
    return lexical_nodes, vector_points


def project_index_empty(settings: RuntimeSettings) -> bool:
    lexical_nodes, vector_points = project_index_counts(settings)
    return lexical_nodes == 0 and vector_points == 0


def ensure_qdrant_collection(
    client,
    settings: RuntimeSettings,
    embed_dim: int,
    *,
    rebuild: bool = False,
) -> None:
    exists = client.collection_exists(settings.qdrant_collection)
    if rebuild:
        if exists:
            client.delete_collection(settings.qdrant_collection)
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=embed_dim, distance=Distance.COSINE),
            hnsw_config=HnswConfigDiff(
                m=settings.qdrant_hnsw_m,
                ef_construct=settings.qdrant_hnsw_ef_construct,
            ),
        )
        return
    if not exists:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=embed_dim, distance=Distance.COSINE),
            hnsw_config=HnswConfigDiff(
                m=settings.qdrant_hnsw_m,
                ef_construct=settings.qdrant_hnsw_ef_construct,
            ),
        )
        return
    info = client.get_collection(settings.qdrant_collection)
    configured_dim = info.config.params.vectors.size
    if configured_dim != embed_dim:
        raise RuntimeError(
            f"Dimensao da colecao ({configured_dim}) difere do embedding ({embed_dim}). "
            "Use --rebuild para recriar a colecao."
        )
