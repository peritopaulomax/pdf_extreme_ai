from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter, SentenceWindowNodeParser
from llama_index.core.schema import MetadataMode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client.models import Distance, HnswConfigDiff, VectorParams

from pdf_extraction import extract_pdf_to_documents
from retrieval_lexical import LexicalIndex, normalize_for_search
from runtime_config import (
    RuntimeSettings,
    batched_paths,
    check_ollama_health,
    configure_runtime_env,
    connect_qdrant,
    embedding_device,
    verify_data_dir,
)


ProgressCallback = Callable[[dict], None]


@dataclass
class IngestResult:
    files_total: int
    files_processed: int
    total_pages: int
    total_chunks: int
    elapsed_s: float
    errors: list[str]
    per_file: list[dict]


def _emit(cb: ProgressCallback | None, **payload) -> None:
    if cb:
        cb(payload)


def _load_checkpoint(path: str) -> dict:
    cp = Path(path)
    if not cp.exists():
        return {"processed_files": []}
    with cp.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_checkpoint(path: str, checkpoint: dict) -> None:
    cp = Path(path)
    cp.parent.mkdir(parents=True, exist_ok=True)
    with cp.open("w", encoding="utf-8") as handle:
        json.dump(checkpoint, handle, ensure_ascii=True, indent=2)


def _ensure_collection(client, settings: RuntimeSettings, embed_dim: int, rebuild: bool) -> None:
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


def _prepare_models(settings: RuntimeSettings, emit: ProgressCallback | None = None) -> int:
    check_ollama_health(settings.ollama_host)
    Settings.llm = Ollama(model=settings.llm_model, request_timeout=600.0)
    target_device = embedding_device()
    try:
        Settings.embed_model = HuggingFaceEmbedding(
            model_name=settings.embedding_model_path,
            device=target_device,
        )
    except Exception as exc:
        msg = str(exc).lower()
        if target_device == "cuda" and "out of memory" in msg:
            _emit(emit, stage="embedding_init", message="OOM em CUDA; fallback para CPU.")
            Settings.embed_model = HuggingFaceEmbedding(
                model_name=settings.embedding_model_path,
                device="cpu",
            )
        else:
            raise
    Settings.chunk_size = settings.chunk_size
    Settings.chunk_overlap = settings.chunk_overlap
    embed_dim = len(Settings.embed_model.get_text_embedding("validacao de dimensao"))
    return embed_dim


def run_ingest(
    *,
    settings: RuntimeSettings | None = None,
    data_dir: str | None = None,
    input_files: list[Path] | None = None,
    rebuild: bool = False,
    reprocess_all: bool = False,
    update_checkpoint: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> IngestResult:
    started = time.time()
    settings = settings or configure_runtime_env()
    files: list[Path]
    if input_files is not None:
        files = [Path(p) for p in input_files]
    else:
        files = verify_data_dir(data_dir or "./data")

    if not files:
        return IngestResult(0, 0, 0, 0, 0.0, [], [])

    _emit(progress_callback, stage="start", message=f"Iniciando ingest de {len(files)} arquivo(s).")
    embed_dim = _prepare_models(settings, progress_callback)
    _emit(progress_callback, stage="embedding_ready", message=f"Embedding dimension: {embed_dim}")

    client, connected_host = connect_qdrant(settings)
    _emit(
        progress_callback,
        stage="qdrant_connected",
        message=f"Qdrant conectado em {connected_host}:{settings.qdrant_port}",
    )
    _ensure_collection(client, settings, embed_dim, rebuild=rebuild)
    lexical_index = LexicalIndex(settings.lexical_db_path)
    if rebuild:
        lexical_index.clear()

    vector_store = QdrantVectorStore(client=client, collection_name=settings.qdrant_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    checkpoint = _load_checkpoint(settings.checkpoint_path) if update_checkpoint else {"processed_files": []}
    processed = set(checkpoint.get("processed_files", []))
    pending_files = list(files) if reprocess_all else [p for p in files if str(p.resolve()) not in processed]
    if not pending_files:
        _emit(progress_callback, stage="done", message="Nenhum arquivo pendente para ingestao.")
        return IngestResult(len(files), 0, 0, 0, time.time() - started, [], [])

    base_splitter = SentenceSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    def _split_chunks(text: str) -> list[str]:
        return base_splitter.split_text(text)

    if settings.ingest_strategy == "sentence_window":
        node_parser: SentenceSplitter | SentenceWindowNodeParser = SentenceWindowNodeParser(
            sentence_splitter=_split_chunks,
            window_size=max(1, settings.sentence_window_size),
            window_metadata_key="window",
            original_text_metadata_key="original_text",
        )
    else:
        node_parser = base_splitter

    errors: list[str] = []
    files_processed = 0
    total_pages = 0
    total_chunks = 0
    total_files = len(pending_files)
    file_counter = 0
    per_file: list[dict] = []

    for batch_idx, batch in enumerate(
        batched_paths(pending_files, max(1, settings.ingest_batch_files)),
        start=1,
    ):
        _emit(progress_callback, stage="batch_start", message=f"Lote {batch_idx}: {len(batch)} arquivo(s)")
        for pdf_path in batch:
            file_counter += 1
            _emit(
                progress_callback,
                stage="extracting",
                file=str(pdf_path),
                current=file_counter,
                total=total_files,
                message=f"Extraindo texto: {pdf_path.name}",
            )
            try:
                docs, extractor, quality = extract_pdf_to_documents(pdf_path)
                _emit(
                    progress_callback,
                    stage="extract_done",
                    file=str(pdf_path),
                    message=f"Extrator={extractor} qualidade={quality:.3f}",
                    pages=len(docs),
                )
                if not docs:
                    per_file.append(
                        {
                            "file": str(pdf_path),
                            "source_file": pdf_path.name,
                            "status": "empty",
                            "pages": 0,
                            "chunks": 0,
                        }
                    )
                    files_processed += 1
                    continue
                _emit(progress_callback, stage="chunking", file=str(pdf_path), pages=len(docs))
                nodes = node_parser.get_nodes_from_documents(docs, show_progress=False)
                if not nodes:
                    per_file.append(
                        {
                            "file": str(pdf_path),
                            "source_file": pdf_path.name,
                            "status": "empty_chunks",
                            "pages": len(docs),
                            "chunks": 0,
                        }
                    )
                    files_processed += 1
                    continue
                _emit(progress_callback, stage="indexing_vector", file=str(pdf_path), chunks=len(nodes))
                VectorStoreIndex(
                    nodes=nodes,
                    storage_context=storage_context,
                    show_progress=False,
                )
                lexical_rows = []
                for node in nodes:
                    source_file = str(node.metadata.get("source_file", pdf_path.name))
                    page = int(node.metadata.get("page", 0) or 0)
                    plain_text = node.get_content(metadata_mode=MetadataMode.NONE)
                    window_text = str(node.metadata.get("window", plain_text))
                    lexical_rows.append(
                        {
                            "node_id": str(getattr(node, "node_id", node.id_)),
                            "source_file": source_file,
                            "page": page,
                            "text": plain_text,
                            "window_text": window_text,
                            "normalized_text": normalize_for_search(plain_text),
                        }
                    )
                _emit(progress_callback, stage="indexing_lexical", file=str(pdf_path), rows=len(lexical_rows))
                lexical_index.upsert_many(lexical_rows)
                total_pages += len(docs)
                total_chunks += len(nodes)
                files_processed += 1
                per_file.append(
                    {
                        "file": str(pdf_path),
                        "source_file": pdf_path.name,
                        "status": "indexed",
                        "pages": len(docs),
                        "chunks": len(nodes),
                        "extractor": extractor,
                        "quality": round(float(quality), 4),
                    }
                )
                _emit(
                    progress_callback,
                    stage="file_done",
                    file=str(pdf_path),
                    pages=len(docs),
                    chunks=len(nodes),
                    current=file_counter,
                    total=total_files,
                )
                if update_checkpoint:
                    processed.add(str(pdf_path.resolve()))
                    checkpoint["processed_files"] = sorted(processed)
                    _save_checkpoint(settings.checkpoint_path, checkpoint)
            except Exception as exc:  # pragma: no cover - runtime ingest diagnostics
                errors.append(f"{pdf_path}: {type(exc).__name__}: {exc}")
                per_file.append(
                    {
                        "file": str(pdf_path),
                        "source_file": pdf_path.name,
                        "status": "error",
                        "error": str(exc),
                        "pages": 0,
                        "chunks": 0,
                    }
                )
                _emit(progress_callback, stage="file_error", file=str(pdf_path), message=str(exc))

    elapsed = time.time() - started
    _emit(
        progress_callback,
        stage="done",
        message=f"Ingest concluida em {elapsed:.1f}s",
        files_processed=files_processed,
        total_pages=total_pages,
        total_chunks=total_chunks,
        errors=len(errors),
    )
    return IngestResult(
        files_total=len(files),
        files_processed=files_processed,
        total_pages=total_pages,
        total_chunks=total_chunks,
        elapsed_s=elapsed,
        errors=errors,
        per_file=per_file,
    )
