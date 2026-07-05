"""Operações em documentos do projeto (paridade com app._remove_docs_from_indexes)."""

from __future__ import annotations

from pathlib import Path

from core.bootstrap import bootstrap_legacy


def remove_docs_from_indexes(settings, docs: list[dict]) -> tuple[int, int]:
    bootstrap_legacy()
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    from qdrant_client.models import FieldCondition, Filter, MatchValue, PointIdsList
    from retrieval_lexical import LexicalIndex
    from runtime_config import connect_qdrant

    source_files = [
        str(d.get("storage_name") or Path(str(d.get("path", ""))).name) for d in docs
    ]
    lexical_removed = LexicalIndex(settings.lexical_db_path).delete_by_source_files(
        source_files
    )
    client, _ = connect_qdrant(settings)
    deleted_points = 0
    for source in source_files:
        points, _ = client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="source_file", match=MatchValue(value=source))]
            ),
            with_payload=False,
            with_vectors=False,
            limit=10_000,
        )
        ids = [p.id for p in points if p.id is not None]
        if ids:
            client.delete(
                collection_name=settings.qdrant_collection,
                points_selector=PointIdsList(points=ids),
            )
            deleted_points += len(ids)
    return deleted_points, lexical_removed


def validate_upload_batch(files, settings) -> None:
    from fastapi import HTTPException

    max_files = settings.ui_ingest_max_files
    max_bytes = settings.ui_ingest_max_file_mb * 1024 * 1024
    if len(files) > max_files:
        raise HTTPException(
            400,
            detail=f"Limite excedido: maximo de {max_files} arquivos por lote.",
        )
    for up in files:
        name = up.filename or "arquivo"
        payload = up.file.read()
        up.file.seek(0)
        if len(payload) > max_bytes:
            raise HTTPException(
                413,
                detail=(
                    f"'{name}' excede {settings.ui_ingest_max_file_mb} MB "
                    f"({len(payload) / (1024 * 1024):.1f} MB)."
                ),
            )
        if not (name.lower().endswith(".pdf")):
            raise HTTPException(400, detail=f"'{name}' nao e PDF.")
