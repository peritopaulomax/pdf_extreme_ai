from __future__ import annotations

import re
from pathlib import Path

from llama_index.core.schema import Document


def _normalize_text(text: str) -> str:
    # Keep line breaks, but collapse noisy spaces/tabs.
    text = text.replace("\x00", " ").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _quality_score(text: str) -> float:
    if not text:
        return 0.0
    total = len(text)
    printable = sum(ch.isprintable() for ch in text)
    alpha = sum(ch.isalpha() for ch in text)
    weird = text.count("\ufffd") + text.count("�")
    # Simple heuristic: prefer printable/alphabetic text, penalize replacement chars.
    score = (printable / total) * 0.6 + (alpha / total) * 0.4 - (weird / total) * 2.0
    return max(0.0, min(1.0, score))


def _extract_with_pymupdf(pdf_path: Path) -> list[str]:
    import fitz

    page_texts: list[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            text = page.get_text("text") or ""
            text = _normalize_text(text)
            page_texts.append(text)
    return page_texts


def _extract_with_pypdf(pdf_path: Path) -> list[str]:
    from pypdf import PdfReader

    page_texts: list[str] = []
    reader = PdfReader(str(pdf_path))
    for page in reader.pages:
        text = page.extract_text() or ""
        text = _normalize_text(text)
        page_texts.append(text)
    return page_texts


def extract_pdf_to_documents(pdf_path: Path) -> tuple[list[Document], str, float]:
    """
    Best-effort extraction focused on text quality for legal PDFs.
    Returns: (documents, extractor_name, quality_score)
    """
    candidates: list[tuple[str, list[str]]] = []

    try:
        candidates.append(("pymupdf", _extract_with_pymupdf(pdf_path)))
    except Exception:
        pass

    try:
        candidates.append(("pypdf", _extract_with_pypdf(pdf_path)))
    except Exception:
        pass

    if not candidates:
        return [], "none", 0.0

    best_name = "none"
    best_pages: list[str] = []
    best_score = -1.0
    for name, pages in candidates:
        nonempty = [p for p in pages if p.strip()]
        joined = "\n\n".join(nonempty)
        score = _quality_score(joined)
        # Slightly prefer extractors that recover more non-empty pages.
        if pages:
            score += min(0.1, (len(nonempty) / len(pages)) * 0.1)
        if score > best_score:
            best_name = name
            best_pages = pages
            best_score = score

    if not best_pages:
        return [], best_name, max(best_score, 0.0)

    docs: list[Document] = []
    for idx, page_text in enumerate(best_pages, start=1):
        if not page_text.strip():
            continue
        docs.append(
            Document(
                text=page_text,
                metadata={
                    "source_file": str(pdf_path.name),
                    "extractor": best_name,
                    "text_quality": round(best_score, 4),
                    "page": idx,
                },
            )
        )
    return docs, best_name, max(best_score, 0.0)
