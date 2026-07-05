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
    doc_type: str = ""
    doc_number: str = ""


def normalize_for_search(text: str) -> str:
    lowered = (text or "").lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    no_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    simplified = re.sub(r"[^a-z0-9\s]", " ", no_accents)
    return " ".join(simplified.split())


def _fts_candidates(term: str) -> list[str]:
    parts = [part for part in term.split() if part]
    if not parts:
        return []
    if len(parts) == 1:
        return [parts[0]]
    phrase = '"' + " ".join(parts) + '"'
    conjunctive = " ".join(parts)
    disjunctive = " OR ".join(parts)
    return [phrase, conjunctive, disjunctive]


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
                    normalized_text TEXT NOT NULL,
                    doc_type TEXT NOT NULL DEFAULT '',
                    doc_number TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(lexical_nodes)").fetchall()
            }
            if "doc_type" not in columns:
                conn.execute("ALTER TABLE lexical_nodes ADD COLUMN doc_type TEXT NOT NULL DEFAULT ''")
            if "doc_number" not in columns:
                conn.execute("ALTER TABLE lexical_nodes ADD COLUMN doc_number TEXT NOT NULL DEFAULT ''")
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
                    INSERT INTO lexical_nodes(
                        node_id, source_file, page, text, window_text, normalized_text, doc_type, doc_number
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(node_id) DO UPDATE SET
                        source_file=excluded.source_file,
                        page=excluded.page,
                        text=excluded.text,
                        window_text=excluded.window_text,
                        normalized_text=excluded.normalized_text,
                        doc_type=excluded.doc_type,
                        doc_number=excluded.doc_number
                    """,
                    (
                        row["node_id"],
                        row["source_file"],
                        int(row["page"]),
                        row["text"],
                        row["window_text"],
                        row["normalized_text"],
                        str(row.get("doc_type") or ""),
                        str(row.get("doc_number") or ""),
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

    def search(
        self,
        query: str,
        limit: int,
        ignore_accents: bool = True,
        page_filter: int | None = None,
        page_range: tuple[int, int] | None = None,
        source_hint: str | None = None,
    ) -> list[LexicalHit]:
        if not query.strip():
            return []
        term = normalize_for_search(query) if ignore_accents else query.strip().lower()
        candidates = _fts_candidates(term)
        if not candidates:
            return []
        try:
            with self._connect() as conn:
                source_like = f"%{(source_hint or '').strip()}%"
                rows = []
                seen_ids: set[str] = set()
                for fts_query in candidates:
                    if page_filter is not None and page_filter > 0:
                        batch = conn.execute(
                            """
                            SELECT n.node_id, n.source_file, n.page, n.text, n.window_text, n.doc_type, n.doc_number,
                                   bm25(lexical_fts) AS bm25_score
                            FROM lexical_fts
                            JOIN lexical_nodes n ON n.node_id = lexical_fts.node_id
                            WHERE lexical_fts MATCH ?
                              AND n.page = ?
                              AND (? = '%%' OR lower(n.source_file) LIKE ?)
                            ORDER BY bm25_score ASC
                            LIMIT ?
                            """,
                            (fts_query, int(page_filter), source_like, source_like, int(limit)),
                        ).fetchall()
                    elif page_range is not None:
                        start, end = page_range
                        batch = conn.execute(
                            """
                            SELECT n.node_id, n.source_file, n.page, n.text, n.window_text, n.doc_type, n.doc_number,
                                   bm25(lexical_fts) AS bm25_score
                            FROM lexical_fts
                            JOIN lexical_nodes n ON n.node_id = lexical_fts.node_id
                            WHERE lexical_fts MATCH ?
                              AND n.page BETWEEN ? AND ?
                              AND (? = '%%' OR lower(n.source_file) LIKE ?)
                            ORDER BY bm25_score ASC
                            LIMIT ?
                            """,
                            (fts_query, int(start), int(end), source_like, source_like, int(limit)),
                        ).fetchall()
                    else:
                        batch = conn.execute(
                            """
                            SELECT n.node_id, n.source_file, n.page, n.text, n.window_text, n.doc_type, n.doc_number,
                                   bm25(lexical_fts) AS bm25_score
                            FROM lexical_fts
                            JOIN lexical_nodes n ON n.node_id = lexical_fts.node_id
                            WHERE lexical_fts MATCH ?
                              AND (? = '%%' OR lower(n.source_file) LIKE ?)
                            ORDER BY bm25_score ASC
                            LIMIT ?
                            """,
                            (fts_query, source_like, source_like, int(limit)),
                        ).fetchall()
                    for row in batch:
                        node_id = str(row["node_id"])
                        if node_id in seen_ids:
                            continue
                        seen_ids.add(node_id)
                        rows.append(row)
                        if len(rows) >= int(limit):
                            break
                    if rows:
                        break
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
                    doc_type=str(row["doc_type"] or ""),
                    doc_number=str(row["doc_number"] or ""),
                )
            )
        return hits

    def search_paginated(
        self,
        query: str,
        *,
        limit: int,
        offset: int = 0,
        ignore_accents: bool = True,
        page_filter: int | None = None,
        page_range: tuple[int, int] | None = None,
        source_hint: str | None = None,
    ) -> list[LexicalHit]:
        """Mesma busca que search(), com OFFSET para varredura exaustiva."""
        if not query.strip():
            return []
        term = normalize_for_search(query) if ignore_accents else query.strip().lower()
        candidates = _fts_candidates(term)
        if not candidates:
            return []
        try:
            with self._connect() as conn:
                source_like = f"%{(source_hint or '').strip()}%"
                rows = []
                for fts_query in candidates:
                    if page_filter is not None and page_filter > 0:
                        rows = conn.execute(
                            """
                            SELECT n.node_id, n.source_file, n.page, n.text, n.window_text, n.doc_type, n.doc_number,
                                   bm25(lexical_fts) AS bm25_score
                            FROM lexical_fts
                            JOIN lexical_nodes n ON n.node_id = lexical_fts.node_id
                            WHERE lexical_fts MATCH ?
                              AND n.page = ?
                              AND (? = '%%' OR lower(n.source_file) LIKE ?)
                            ORDER BY bm25_score ASC
                            LIMIT ? OFFSET ?
                            """,
                            (
                                fts_query,
                                int(page_filter),
                                source_like,
                                source_like,
                                int(limit),
                                int(offset),
                            ),
                        ).fetchall()
                    elif page_range is not None:
                        start, end = page_range
                        rows = conn.execute(
                            """
                            SELECT n.node_id, n.source_file, n.page, n.text, n.window_text, n.doc_type, n.doc_number,
                                   bm25(lexical_fts) AS bm25_score
                            FROM lexical_fts
                            JOIN lexical_nodes n ON n.node_id = lexical_fts.node_id
                            WHERE lexical_fts MATCH ?
                              AND n.page BETWEEN ? AND ?
                              AND (? = '%%' OR lower(n.source_file) LIKE ?)
                            ORDER BY bm25_score ASC
                            LIMIT ? OFFSET ?
                            """,
                            (
                                fts_query,
                                int(start),
                                int(end),
                                source_like,
                                source_like,
                                int(limit),
                                int(offset),
                            ),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            """
                            SELECT n.node_id, n.source_file, n.page, n.text, n.window_text, n.doc_type, n.doc_number,
                                   bm25(lexical_fts) AS bm25_score
                            FROM lexical_fts
                            JOIN lexical_nodes n ON n.node_id = lexical_fts.node_id
                            WHERE lexical_fts MATCH ?
                              AND (? = '%%' OR lower(n.source_file) LIKE ?)
                            ORDER BY bm25_score ASC
                            LIMIT ? OFFSET ?
                            """,
                            (
                                fts_query,
                                source_like,
                                source_like,
                                int(limit),
                                int(offset),
                            ),
                        ).fetchall()
                    if rows:
                        break
        except sqlite3.OperationalError:
            return []
        hits: list[LexicalHit] = []
        for row in rows:
            bm25 = float(row["bm25_score"]) if row["bm25_score"] is not None else 0.0
            score = 1.0 / (1.0 + max(0.0, bm25))
            hits.append(
                LexicalHit(
                    node_id=row["node_id"],
                    source_file=row["source_file"],
                    page=int(row["page"]),
                    text=row["text"],
                    window_text=row["window_text"],
                    score=score,
                    doc_type=str(row["doc_type"] or ""),
                    doc_number=str(row["doc_number"] or ""),
                )
            )
        return hits

    def search_by_doc_refs(self, refs: list[tuple[str, str]], *, limit: int = 6) -> list[LexicalHit]:
        pairs = [(str(kind or "").strip().lower(), str(number or "").strip()) for kind, number in refs if kind and number]
        if not pairs:
            return []
        hits: list[LexicalHit] = []
        seen_ids: set[str] = set()
        with self._connect() as conn:
            for kind, number in pairs:
                rows = conn.execute(
                    """
                    SELECT node_id, source_file, page, text, window_text, doc_type, doc_number
                    FROM lexical_nodes
                    WHERE lower(doc_type) = ? AND doc_number = ?
                    ORDER BY page ASC
                    LIMIT ?
                    """,
                    (kind, number, int(limit)),
                ).fetchall()
                for row in rows:
                    node_id = str(row["node_id"])
                    if node_id in seen_ids:
                        continue
                    seen_ids.add(node_id)
                    hits.append(
                        LexicalHit(
                            node_id=node_id,
                            source_file=row["source_file"],
                            page=int(row["page"]),
                            text=row["text"],
                            window_text=row["window_text"],
                            score=0.45,
                            doc_type=str(row["doc_type"] or ""),
                            doc_number=str(row["doc_number"] or ""),
                        )
                    )
                    if len(hits) >= limit:
                        return hits
        return hits

    def count_nodes(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM lexical_nodes").fetchone()
            return int(row["n"] if row and row["n"] is not None else 0)

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
