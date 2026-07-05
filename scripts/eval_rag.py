#!/usr/bin/env python3
"""Avaliacao offline simples: recall@k e presenca de citacao."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from answer_validator import _has_basic_citation
from llama_index.core.schema import QueryBundle
from query_planner import plan_query
from retrieval_lexical import LexicalIndex
from retrieval_pipeline import HybridRetriever
from runtime_config import configure_runtime_env, connect_qdrant, embedding_device
from index_bootstrap import ensure_qdrant_collection, embedding_vector_size
from llama_index.core import Settings, VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Eval RAG offline (gold_questions.json)")
    parser.add_argument(
        "--gold",
        default=str(ROOT / "eval" / "gold_questions.json"),
        help="Arquivo JSON com perguntas gold",
    )
    parser.add_argument("--k", type=int, default=10, help="Recall@k")
    args = parser.parse_args()

    settings = configure_runtime_env()
    gold_path = Path(args.gold)
    if not gold_path.is_file():
        print(f"Gold file not found: {gold_path}")
        return 1
    items = json.loads(gold_path.read_text(encoding="utf-8"))

    Settings.embed_model = HuggingFaceEmbedding(
        model_name=settings.embedding_model_path,
        device=embedding_device(),
    )
    client, _ = connect_qdrant(settings)
    embed_dim = embedding_vector_size(settings)
    ensure_qdrant_collection(client, settings, embed_dim, rebuild=False)
    vector_store = QdrantVectorStore(client=client, collection_name=settings.qdrant_collection)
    index = VectorStoreIndex.from_vector_store(vector_store)
    lexical_index = LexicalIndex(settings.lexical_db_path)
    retriever = HybridRetriever(
        index=index,
        settings=settings,
        lexical_index=lexical_index,
    )

    hits = 0
    cited = 0
    for item in items:
        q = str(item.get("question", ""))
        nodes = retriever.retrieve(QueryBundle(query_str=q))
        top = nodes[: args.k]
        plan = plan_query(q, settings)
        diag = retriever.last_diagnostics
        recall_ok = len(top) > 0
        if recall_ok:
            hits += 1
        fake_answer = f"Trecho em [{top[0].node.metadata.get('source_file', 'doc')}, pag. {top[0].node.metadata.get('page', 1)}]."
        if _has_basic_citation(fake_answer):
            cited += 1
        print(
            f"[{item.get('id', '?')}] recall@{args.k}={recall_ok} "
            f"fused={diag.fused_count if diag else 0} intent={plan.intent}"
        )

    n = max(1, len(items))
    print(f"Recall@{args.k}: {hits}/{len(items)} ({100 * hits / n:.1f}%)")
    print(f"Citation format OK (synthetic): {cited}/{len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
