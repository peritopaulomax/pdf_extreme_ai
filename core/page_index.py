"""Indice lexical agregado por pagina (source_file, page)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from retrieval_lexical import LexicalIndex, normalize_for_search


@dataclass
class PageHit:
    source_file: str
    page: int
    text: str
    score: float
    doc_type: str = ""
    doc_number: str = ""


class PageLexicalIndex:
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
                CREATE TABLE IF NOT EXISTS page_nodes (
                    source_file TEXT NOT NULL,
                    page INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    doc_type TEXT NOT NULL DEFAULT '',
                    doc_number TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (source_file, page)
                )
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(page_nodes)").fetchall()
            }
            if "doc_type" not in columns:
                conn.execute("ALTER TABLE page_nodes ADD COLUMN doc_type TEXT NOT NULL DEFAULT ''")
            if "doc_number" not in columns:
                conn.execute("ALTER TABLE page_nodes ADD COLUMN doc_number TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS page_fts USING fts5(
                    source_file UNINDEXED,
                    page UNINDEXED,
                    text,
                    normalized_text,
                    tokenize='unicode61'
                )
                """
            )

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM page_nodes")
            conn.execute("DELETE FROM page_fts")

    def upsert_page(
        self,
        source_file: str,
        page: int,
        text: str,
        *,
        doc_type: str = "",
        doc_number: str = "",
    ) -> None:
        norm = normalize_for_search(text)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO page_nodes(source_file, page, text, normalized_text, doc_type, doc_number)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_file, page) DO UPDATE SET
                    text=excluded.text,
                    normalized_text=excluded.normalized_text,
                    doc_type=excluded.doc_type,
                    doc_number=excluded.doc_number
                """,
                (source_file, int(page), text, norm, doc_type, doc_number),
            )
            conn.execute(
                "DELETE FROM page_fts WHERE source_file = ? AND page = ?",
                (source_file, int(page)),
            )
            conn.execute(
                """
                INSERT INTO page_fts(source_file, page, text, normalized_text)
                VALUES (?, ?, ?, ?)
                """,
                (source_file, int(page), text, norm),
            )

    def build_from_chunk_rows(self, rows: list[dict]) -> None:
        """Agrega chunks por (source_file, page)."""
        buckets: dict[tuple[str, int], dict[str, object]] = {}
        for row in rows:
            key = (str(row["source_file"]), int(row["page"]))
            bucket = buckets.setdefault(
                key,
                {
                    "parts": [],
                    "doc_type": str(row.get("doc_type") or ""),
                    "doc_number": str(row.get("doc_number") or ""),
                },
            )
            bucket["parts"].append(str(row.get("window_text") or row.get("text") or ""))
            if not bucket.get("doc_type") and row.get("doc_type"):
                bucket["doc_type"] = str(row.get("doc_type"))
            if not bucket.get("doc_number") and row.get("doc_number"):
                bucket["doc_number"] = str(row.get("doc_number"))
        for (source, page), bucket in buckets.items():
            parts = list(bucket.get("parts") or [])
            merged = "\n\n".join(p.strip() for p in parts if p.strip())
            if merged:
                self.upsert_page(
                    source,
                    page,
                    merged,
                    doc_type=str(bucket.get("doc_type") or ""),
                    doc_number=str(bucket.get("doc_number") or ""),
                )

    def search(
        self,
        query: str,
        limit: int = 8,
        page_filter: int | None = None,
        page_range: tuple[int, int] | None = None,
        source_hint: str | None = None,
    ) -> list[PageHit]:
        if not query.strip():
            return []
        term = normalize_for_search(query)
        fts_query = " OR ".join(part for part in term.split() if part)
        if not fts_query:
            return []
        try:
            with self._connect() as conn:
                source_like = f"%{(source_hint or '').strip()}%"
                params: list = [fts_query]
                where = ["page_fts MATCH ?"]
                if page_filter is not None and page_filter > 0:
                    where.append("p.page = ?")
                    params.append(int(page_filter))
                elif page_range is not None:
                    where.append("p.page BETWEEN ? AND ?")
                    params.extend([int(page_range[0]), int(page_range[1])])
                where.append("(? = '%%' OR lower(p.source_file) LIKE ?)")
                params.extend([source_like, source_like])
                params.append(int(limit))
                sql = f"""
                    SELECT p.source_file, p.page, p.text, p.doc_type, p.doc_number, bm25(page_fts) AS bm25_score
                    FROM page_fts
                    JOIN page_nodes p ON p.source_file = page_fts.source_file AND p.page = page_fts.page
                    WHERE {' AND '.join(where)}
                    ORDER BY bm25_score ASC
                    LIMIT ?
                """
                rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []
        hits: list[PageHit] = []
        for row in rows:
            bm25 = float(row["bm25_score"]) if row["bm25_score"] is not None else 0.0
            hits.append(
                PageHit(
                    source_file=row["source_file"],
                    page=int(row["page"]),
                    text=row["text"],
                    score=1.0 / (1.0 + max(0.0, bm25)),
                    doc_type=str(row["doc_type"] or ""),
                    doc_number=str(row["doc_number"] or ""),
                )
            )
        return hits

    def get_pages(
        self,
        source_file: str,
        pages: list[int],
        *,
        max_chars: int = 4500,
    ) -> list[PageHit]:
        """Retorna paginas especificas para contexto pai/adjacente."""
        clean_pages = sorted({int(p) for p in pages if int(p) > 0})
        if not source_file or not clean_pages:
            return []
        placeholders = ",".join("?" for _ in clean_pages)
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT source_file, page, text, doc_type, doc_number
                    FROM page_nodes
                    WHERE source_file = ?
                      AND page IN ({placeholders})
                    ORDER BY page ASC
                    """,
                    [source_file, *clean_pages],
                ).fetchall()
        except sqlite3.OperationalError:
            return []
        hits: list[PageHit] = []
        for row in rows:
            text = str(row["text"] or "")
            if max_chars > 0 and len(text) > max_chars:
                text = text[: max_chars - 3].rstrip() + "..."
            hits.append(
                PageHit(
                    source_file=row["source_file"],
                    page=int(row["page"]),
                    text=text,
                    score=0.0,
                    doc_type=str(row["doc_type"] or ""),
                    doc_number=str(row["doc_number"] or ""),
                )
            )
        return hits
