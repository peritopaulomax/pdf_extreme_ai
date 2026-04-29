from __future__ import annotations

import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class LexicalHit:
    node_id: str
    source_file: str
    page: int
    text: str
    window_text: str
    score: float


def normalize_for_search(text: str) -> str:
    lowered = (text or "").lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    no_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    simplified = re.sub(r"[^a-z0-9\s]", " ", no_accents)
    return " ".join(simplified.split())


class LexicalIndex:
    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path))
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lexical_nodes (
                    node_id TEXT PRIMARY KEY,
                    source_file TEXT NOT NULL,
                    page INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    window_text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS lexical_fts USING fts5(
                    node_id UNINDEXED,
                    source_file UNINDEXED,
                    page UNINDEXED,
                    text,
                    normalized_text,
                    tokenize='unicode61'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lexical_nodes_page ON lexical_nodes(source_file, page)"
            )

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM lexical_nodes")
            conn.execute("DELETE FROM lexical_fts")

    def upsert_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        with self._connect() as conn:
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO lexical_nodes(node_id, source_file, page, text, window_text, normalized_text)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(node_id) DO UPDATE SET
                        source_file=excluded.source_file,
                        page=excluded.page,
                        text=excluded.text,
                        window_text=excluded.window_text,
                        normalized_text=excluded.normalized_text
                    """,
                    (
                        row["node_id"],
                        row["source_file"],
                        int(row["page"]),
                        row["text"],
                        row["window_text"],
                        row["normalized_text"],
                    ),
                )
            node_ids = [row["node_id"] for row in rows]
            conn.executemany("DELETE FROM lexical_fts WHERE node_id = ?", [(nid,) for nid in node_ids])
            conn.executemany(
                """
                INSERT INTO lexical_fts(node_id, source_file, page, text, normalized_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["node_id"],
                        row["source_file"],
                        int(row["page"]),
                        row["text"],
                        row["normalized_text"],
                    )
                    for row in rows
                ],
            )

    def search(self, query: str, limit: int, ignore_accents: bool = True) -> list[LexicalHit]:
        if not query.strip():
            return []
        term = normalize_for_search(query) if ignore_accents else query.strip().lower()
        fts_query = " OR ".join(part for part in term.split() if part)
        if not fts_query:
            return []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT n.node_id, n.source_file, n.page, n.text, n.window_text,
                           bm25(lexical_fts) AS bm25_score
                    FROM lexical_fts
                    JOIN lexical_nodes n ON n.node_id = lexical_fts.node_id
                    WHERE lexical_fts MATCH ?
                    ORDER BY bm25_score ASC
                    LIMIT ?
                    """,
                    (fts_query, int(limit)),
                ).fetchall()
        except sqlite3.OperationalError:
            return []
        hits: list[LexicalHit] = []
        for row in rows:
            bm25 = float(row["bm25_score"]) if row["bm25_score"] is not None else 0.0
            # bm25 menor e melhor; converter para score crescente.
            score = 1.0 / (1.0 + max(0.0, bm25))
            hits.append(
                LexicalHit(
                    node_id=row["node_id"],
                    source_file=row["source_file"],
                    page=int(row["page"]),
                    text=row["text"],
                    window_text=row["window_text"],
                    score=score,
                )
            )
        return hits

    def delete_by_source_files(self, source_files: list[str]) -> int:
        targets = [s for s in source_files if s]
        if not targets:
            return 0
        removed = 0
        with self._connect() as conn:
            for source in targets:
                ids = [
                    row["node_id"]
                    for row in conn.execute(
                        "SELECT node_id FROM lexical_nodes WHERE source_file = ?",
                        (source,),
                    ).fetchall()
                ]
                if ids:
                    conn.executemany(
                        "DELETE FROM lexical_fts WHERE node_id = ?",
                        [(nid,) for nid in ids],
                    )
                cur = conn.execute("DELETE FROM lexical_nodes WHERE source_file = ?", (source,))
                removed += int(cur.rowcount or 0)
        return removed
