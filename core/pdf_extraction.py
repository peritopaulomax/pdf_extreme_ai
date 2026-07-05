from __future__ import annotations

import os
import re
from pathlib import Path

from llama_index.core.schema import Document

from display_name import human_source_label


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


def _ocr_page_text(pdf_path: Path, page_index: int) -> str:
    """OCR opcional (Tesseract via pymupdf). Requer ENABLE_OCR=true e dependencias instaladas."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    try:
        with fitz.open(str(pdf_path)) as doc:
            page = doc[page_index]
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang="por+eng")
            return _normalize_text(text)
    except Exception:
        return ""


def _maybe_ocr_pages(
    pdf_path: Path,
    pages: list[str],
    *,
    quality: float,
    threshold: float,
) -> tuple[list[str], bool]:
    enable = os.environ.get("ENABLE_OCR", "").strip().lower() in ("1", "true", "yes", "on")
    if not enable or quality >= threshold:
        return pages, False
    improved: list[str] = []
    used = False
    for idx, page_text in enumerate(pages):
        if page_text.strip() and _quality_score(page_text) >= threshold:
            improved.append(page_text)
            continue
        ocr_text = _ocr_page_text(pdf_path, idx)
        if ocr_text.strip():
            improved.append(ocr_text)
            used = True
        else:
            improved.append(page_text)
    return improved, used


def _extract_with_pypdf(pdf_path: Path) -> list[str]:
    from pypdf import PdfReader

    page_texts: list[str] = []
    reader = PdfReader(str(pdf_path))
    for page in reader.pages:
        text = page.extract_text() or ""
        text = _normalize_text(text)
        page_texts.append(text)
    return page_texts


def extract_pdf_to_documents(
    pdf_path: Path,
    *,
    ocr_quality_threshold: float | None = None,
) -> tuple[list[Document], str, float]:
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

    threshold = ocr_quality_threshold
    if threshold is None:
        raw = os.environ.get("OCR_QUALITY_THRESHOLD", "0.35").strip()
        try:
            threshold = float(raw)
        except ValueError:
            threshold = 0.35
    best_pages, ocr_used = _maybe_ocr_pages(
        pdf_path, best_pages, quality=best_score, threshold=threshold
    )
    if ocr_used:
        joined = "\n\n".join(p for p in best_pages if p.strip())
        best_score = max(best_score, _quality_score(joined))
        best_name = f"{best_name}+ocr"

    docs: list[Document] = []
    for idx, page_text in enumerate(best_pages, start=1):
        if not page_text.strip():
            continue
        stored = str(pdf_path.name)
        docs.append(
            Document(
                text=page_text,
                metadata={
                    "source_file": stored,
                    "display_name": human_source_label(stored),
                    "extractor": best_name,
                    "text_quality": round(best_score, 4),
                    "page": idx,
                },
            )
        )
    return docs, best_name, max(best_score, 0.0)
