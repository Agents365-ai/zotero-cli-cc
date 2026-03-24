"""Tests for PDF annotation extraction."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from zotero_cli_cc.core.pdf_extractor import extract_annotations


@pytest.fixture
def annotated_pdf(tmp_path) -> Path:
    """Create a test PDF with annotations."""
    pdf_path = tmp_path / "annotated.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    # Add text
    page.insert_text((72, 72), "This is a test document with annotations.")
    # Add highlight annotation
    rect = pymupdf.Rect(72, 60, 300, 80)
    annot = page.add_highlight_annot(rect)
    annot.set_info(content="Important highlight")
    annot.update()
    # Add text annotation (sticky note)
    note_point = pymupdf.Point(72, 100)
    annot2 = page.add_text_annot(note_point, "This is a sticky note")
    annot2.update()
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def no_annotation_pdf(tmp_path) -> Path:
    """Create a test PDF without annotations."""
    pdf_path = tmp_path / "plain.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Plain document.")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


class TestExtractAnnotations:
    def test_extract_highlights(self, annotated_pdf):
        annotations = extract_annotations(annotated_pdf)
        assert len(annotations) >= 1
        highlight = [a for a in annotations if a["type"] == "Highlight"]
        assert len(highlight) >= 1

    def test_extract_text_annotations(self, annotated_pdf):
        annotations = extract_annotations(annotated_pdf)
        text_annots = [a for a in annotations if a["type"] == "Text"]
        assert len(text_annots) >= 1
        assert "sticky note" in text_annots[0]["content"]

    def test_annotations_have_page_number(self, annotated_pdf):
        annotations = extract_annotations(annotated_pdf)
        assert all("page" in a for a in annotations)
        assert all(a["page"] >= 1 for a in annotations)

    def test_no_annotations(self, no_annotation_pdf):
        annotations = extract_annotations(no_annotation_pdf)
        assert annotations == []

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            extract_annotations(Path("/nonexistent.pdf"))

    def test_highlight_has_content(self, annotated_pdf):
        annotations = extract_annotations(annotated_pdf)
        highlight = [a for a in annotations if a["type"] == "Highlight"]
        assert highlight[0]["content"] == "Important highlight"
