from __future__ import annotations

import re
from pathlib import Path

import pymupdf


class PdfExtractionError(Exception):
    """Raised when PDF text extraction fails."""

    pass


def extract_text_from_pdf(
    pdf_path: Path,
    pages: tuple[int, int] | None = None,
) -> str:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as e:
        raise PdfExtractionError(f"Cannot open PDF: {e}") from e
    try:
        if pages:
            start, end = pages
            if start > len(doc):
                raise PdfExtractionError(f"Start page {start} exceeds document length ({len(doc)} pages)")
            page_range = range(start - 1, min(end, len(doc)))
        else:
            page_range = range(len(doc))
        texts = []
        for i in page_range:
            texts.append(doc[i].get_text())
        return "\n".join(texts)
    except PdfExtractionError:
        raise
    except Exception as e:
        raise PdfExtractionError(f"Failed to extract text: {e}") from e
    finally:
        doc.close()


def extract_annotations(pdf_path: Path) -> list[dict]:
    """Extract annotations (highlights, notes, comments) from a PDF.

    Returns list of dicts with keys: type, page, content, quote (for highlights).
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as e:
        raise PdfExtractionError(f"Cannot open PDF: {e}") from e
    annotations: list[dict] = []
    try:
        for page_num, page in enumerate(doc, start=1):  # type: ignore[var-annotated,arg-type]
            for annot in page.annots() or []:
                entry: dict = {
                    "type": annot.type[1],  # e.g. "Highlight", "Text", "Underline"
                    "page": page_num,
                    "content": annot.info.get("content", "") or "",
                }
                # For highlight/underline/squiggly/strikeout, extract quoted text
                if annot.type[0] in (8, 9, 10, 11):
                    try:
                        quads = annot.vertices
                        if quads:
                            quad_points = [pymupdf.Quad(quads[i : i + 4]) for i in range(0, len(quads), 4)]
                            text_parts = []
                            for q in quad_points:
                                text_parts.append(page.get_text("text", clip=q.rect).strip())
                            quoted = " ".join(t for t in text_parts if t)
                            if quoted:
                                entry["quote"] = quoted
                    except Exception:
                        pass
                annotations.append(entry)
    finally:
        doc.close()
    return annotations


def extract_doi(pdf_path: Path) -> str | None:
    """Extract DOI from first 2 pages of a PDF. Returns first match or None."""
    try:
        text = extract_text_from_pdf(pdf_path, pages=(1, 2))
    except (PdfExtractionError, FileNotFoundError):
        return None
    match = re.search(r"10\.\d{4,9}/[^\s]+", text)
    if match:
        return match.group(0).rstrip(".,;)]}>'\"")
    return None
