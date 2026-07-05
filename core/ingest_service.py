from __future__ import annotations
import http_proxy_bootstrap  # noqa: F401 — strip socks:// etc. before ollama/httpx import
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter, SentenceWindowNodeParser
from llama_index.core.schema import MetadataMode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from index_bootstrap import ensure_qdrant_collection
from pdf_extraction import extract_pdf_to_documents
from cross_doc_graph import build_graph_from_rows, load_graph, merge_graph, save_graph
from entity_timeline import extract_entities_from_text, load_entities, save_entities
from page_index import PageLexicalIndex
from retrieval_lexical import LexicalIndex, normalize_for_search
from gpu_runtime import ingest_gpu_slot, release_cuda_cache
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


def classify_chunk_document_metadata(text: str) -> dict[str, str]:
    sample = (text or "")[:600]
    patterns = (
        ("oficio", r"of[ií]cio\s*n[º°o]?\s*([0-9./-]+)"),
        ("despacho", r"despacho\s*n[º°o]?\s*([0-9./-]+)"),
        ("informacao", r"informa[cç][aã]o\s*n[º°o]?\s*([0-9./-]+)"),
        ("termo", r"termo de declara[cç][oõ]es\s*n[º°o]?\s*([0-9./-]+)"),
        ("email", r"(^de:\s|correio eletr[oô]nico)", re.IGNORECASE),
    )
    for entry in patterns:
        doc_type = entry[0]
        regex = entry[1]
        flags = entry[2] if len(entry) > 2 else re.IGNORECASE
        match = re.search(regex, sample, flags)
        if not match:
            continue
        payload = {"doc_type": doc_type}
        if match.groups():
            payload["doc_number"] = str(match.group(1)).strip()
        return payload
    return {}


def _prepare_models(settings: RuntimeSettings, emit: ProgressCallback | None = None) -> int:
    check_ollama_health(settings.ollama_host)
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


def _is_cuda_oom(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "out of memory" in msg and "cuda" in msg


def _index_nodes_with_oom_fallback(
    *,
    nodes,
    storage_context: StorageContext,
    settings: RuntimeSettings,
    emit: ProgressCallback | None = None,
) -> str:
    """Index nodes, retrying on CPU if CUDA OOM happens mid-ingest."""
    try:
        VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            show_progress=False,
        )
        return embedding_device()
    except Exception as exc:
        if not _is_cuda_oom(exc):
            raise
        _emit(
            emit,
            stage="indexing_vector_retry_cpu",
            message="OOM em CUDA durante indexacao; alternando embedding para CPU e repetindo.",
        )
        release_cuda_cache()
        Settings.embed_model = HuggingFaceEmbedding(
            model_name=settings.embedding_model_path,
            device="cpu",
        )
        VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            show_progress=False,
        )
        return "cpu"


def release_ingest_models() -> None:
    """Libera embedding de ingestao da VRAM (nao afeta reranker do chat)."""
    Settings.embed_model = None
    release_cuda_cache()


def run_ingest(
    *,
    settings: RuntimeSettings | None = None,
    data_dir: str | None = None,
    input_files: list[Path] | None = None,
    rebuild: bool = False,
    reprocess_all: bool = False,
    update_checkpoint: bool = True,
    progress_callback: ProgressCallback | None = None,
    project_id: str | None = None,
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

    with ingest_gpu_slot():
        return _run_ingest_locked(
            settings=settings,
            files=files,
            rebuild=rebuild,
            reprocess_all=reprocess_all,
            update_checkpoint=update_checkpoint,
            progress_callback=progress_callback,
            started=started,
            project_id=project_id,
        )


def _run_ingest_locked(
    *,
    settings: RuntimeSettings,
    files: list[Path],
    rebuild: bool,
    reprocess_all: bool,
    update_checkpoint: bool,
    progress_callback: ProgressCallback | None,
    started: float,
    project_id: str | None = None,
) -> IngestResult:
    try:
        _emit(progress_callback, stage="start", message=f"Iniciando ingest de {len(files)} arquivo(s).")
        embed_dim = _prepare_models(settings, progress_callback)
        _emit(progress_callback, stage="embedding_ready", message=f"Embedding dimension: {embed_dim}")

        client, connected_host = connect_qdrant(settings)
        _emit(
            progress_callback,
            stage="qdrant_connected",
            message=f"Qdrant conectado em {connected_host}:{settings.qdrant_port}",
        )
        ensure_qdrant_collection(client, settings, embed_dim, rebuild=rebuild)
        lexical_index = LexicalIndex(settings.lexical_db_path)
        page_index = PageLexicalIndex(settings.lexical_db_path)
        if rebuild:
            lexical_index.clear()
            page_index.clear()

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
                    docs, extractor, quality = extract_pdf_to_documents(
                        pdf_path,
                        ocr_quality_threshold=settings.ocr_quality_threshold,
                    )
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
                                "quality": round(float(quality), 4),
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
                                "quality": round(float(quality), 4),
                            }
                        )
                        files_processed += 1
                        continue
                    _emit(progress_callback, stage="indexing_vector", file=str(pdf_path), chunks=len(nodes))
                    for node in nodes:
                        plain_text = node.get_content(metadata_mode=MetadataMode.NONE)
                        window_text = str(node.metadata.get("window", plain_text))
                        doc_meta = classify_chunk_document_metadata(window_text or plain_text)
                        if doc_meta:
                            node.metadata.update(doc_meta)
                    used_embed_device = _index_nodes_with_oom_fallback(
                        nodes=nodes,
                        storage_context=storage_context,
                        settings=settings,
                        emit=progress_callback,
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
                                "doc_type": str(node.metadata.get("doc_type") or ""),
                                "doc_number": str(node.metadata.get("doc_number") or ""),
                            }
                        )
                    _emit(progress_callback, stage="indexing_lexical", file=str(pdf_path), rows=len(lexical_rows))
                    lexical_index.upsert_many(lexical_rows)
                    page_index.build_from_chunk_rows(lexical_rows)
                    if project_id:
                        bucket = load_entities(project_id)
                        seen = {(e.get("kind"), e.get("value"), e.get("source_file")) for e in bucket}
                        for row in lexical_rows:
                            for ent in extract_entities_from_text(
                                str(row.get("text") or ""),
                                source_file=str(row["source_file"]),
                                page=int(row["page"]),
                                max_hits=6,
                            ):
                                key = (ent.kind, ent.value, ent.source_file)
                                if key in seen:
                                    continue
                                seen.add(key)
                                bucket.append(
                                    {
                                        "kind": ent.kind,
                                        "value": ent.value,
                                        "source_file": ent.source_file,
                                        "page": ent.page,
                                    }
                                )
                        if bucket:
                            save_entities(project_id, bucket[-500:])
                        new_graph = build_graph_from_rows(lexical_rows)
                        if new_graph:
                            save_graph(project_id, merge_graph(load_graph(project_id), new_graph))
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
                            "embed_device": used_embed_device,
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
    finally:
        release_ingest_models()
