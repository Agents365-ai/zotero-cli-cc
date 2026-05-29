from pathlib import Path

import pytest

from zotero_cli_cc.core.pdf_extractor import PdfiumExtractor, get_extractor

FIXTURES = Path(__file__).parent / "fixtures"


class TestPdfiumExtractor:
    def setup_method(self):
        self.extractor = PdfiumExtractor()

    def test_is_default_extractor(self):
        # The permissively-licensed pdfium backend is the default (no AGPL).
        assert get_extractor().name() == "pdfium"

    def test_name(self):
        assert self.extractor.name() == "pdfium"

    def test_extract_text_returns_string(self):
        text = self.extractor.extract_text(FIXTURES / "test.pdf")
        assert isinstance(text, str)

    def test_extract_text_contains_content(self):
        text = self.extractor.extract_text(FIXTURES / "test.pdf")
        assert "test PDF" in text

    def test_extract_text_with_pages(self):
        text = self.extractor.extract_text(FIXTURES / "test.pdf", pages=(1, 1))
        assert isinstance(text, str)
        assert len(text) > 0

    def test_extract_text_accepts_progress_callback(self):
        calls: list[tuple] = []
        text = self.extractor.extract_text(
            FIXTURES / "test.pdf",
            progress_callback=lambda *a: calls.append(a),
        )
        assert isinstance(text, str)
        assert calls  # at least one page reported

    def test_extract_text_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            self.extractor.extract_text(FIXTURES / "nonexistent.pdf")

    def test_extract_annotations_empty(self):
        # Annotation extraction needs the optional pymupdf backend.
        assert self.extractor.extract_annotations(FIXTURES / "test.pdf") == []

    def test_extract_doi_returns_string_or_none(self):
        result = self.extractor.extract_doi(FIXTURES / "test.pdf")
        assert result is None or isinstance(result, str)

    def test_extract_doi_nonexistent_returns_none(self):
        assert self.extractor.extract_doi(FIXTURES / "nonexistent.pdf") is None
