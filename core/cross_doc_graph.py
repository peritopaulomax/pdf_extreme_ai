from __future__ import annotations

import json
import re
from pathlib import Path

_REF_PATTERNS = (
    ("oficio", re.compile(r"of[ií]cio\s*n[º°o]?\s*([0-9./-]+)", re.IGNORECASE)),
    ("despacho", re.compile(r"despacho\s*n[º°o]?\s*([0-9./-]+)", re.IGNORECASE)),
    ("informacao", re.compile(r"informa[cç][aã]o\s*n[º°o]?\s*([0-9./-]+)", re.IGNORECASE)),
    ("termo", re.compile(r"termo de declara[cç][oõ]es\s*n[º°o]?\s*([0-9./-]+)", re.IGNORECASE)),
)


def graph_path(project_id: str) -> Path:
    import paths

    base = paths.project_dir(project_id)
    base.mkdir(parents=True, exist_ok=True)
    return base / "cross_doc_graph.json"


def _ref_key(kind: str, number: str) -> str:
    return f"{kind}:{(number or '').strip()}"


def extract_reference_keys(text: str) -> list[str]:
    sample = (text or "")[:4000]
    keys: list[str] = []
    seen: set[str] = set()
    for kind, pattern in _REF_PATTERNS:
        for match in pattern.finditer(sample):
            key = _ref_key(kind, match.group(1))
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def build_graph_from_rows(rows: list[dict]) -> dict[str, dict]:
    graph: dict[str, dict] = {}
    for row in rows:
        doc_type = str(row.get("doc_type") or "").strip().lower()
        doc_number = str(row.get("doc_number") or "").strip()
        if not doc_type or not doc_number:
            continue
        key = _ref_key(doc_type, doc_number)
        entry = graph.setdefault(
            key,
            {
                "kind": doc_type,
                "number": doc_number,
                "source_files": [],
                "pages": [],
                "references": [],
            },
        )
        source_file = str(row.get("source_file") or "")
        page = int(row.get("page", 0) or 0)
        if source_file and source_file not in entry["source_files"]:
            entry["source_files"].append(source_file)
        if page and page not in entry["pages"]:
            entry["pages"].append(page)
        refs = extract_reference_keys(str(row.get("window_text") or row.get("text") or ""))
        for ref in refs:
            if ref != key and ref not in entry["references"]:
                entry["references"].append(ref)
    return graph


def merge_graph(existing: dict[str, dict], new: dict[str, dict]) -> dict[str, dict]:
    merged = dict(existing or {})
    for key, entry in (new or {}).items():
        cur = merged.setdefault(
            key,
            {
                "kind": entry.get("kind", ""),
                "number": entry.get("number", ""),
                "source_files": [],
                "pages": [],
                "references": [],
            },
        )
        for field in ("source_files", "pages", "references"):
            seen = set(cur.get(field) or [])
            for item in entry.get(field) or []:
                if item in seen:
                    continue
                seen.add(item)
                cur.setdefault(field, []).append(item)
    return merged


def load_graph(project_id: str) -> dict[str, dict]:
    path = graph_path(project_id)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_graph(project_id: str, graph: dict[str, dict]) -> None:
    graph_path(project_id).write_text(
        json.dumps(graph or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

