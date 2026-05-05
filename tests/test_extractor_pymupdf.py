from pathlib import Path

import pytest

from zotero_cli_cc.core.pdf_extractor import PyMuPdfExtractor

FIXTURES = Path(__file__).parent / "fixtures"


class TestPyMuPdfExtractor:
    def setup_method(self):
        self.extractor = PyMuPdfExtractor()

    def test_name(self):
        assert self.extractor.name() == "pymupdf"

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

    def test_extract_text_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            self.extractor.extract_text(FIXTURES / "nonexistent.pdf")

    def test_extract_annotations_returns_list(self):
        annotations = self.extractor.extract_annotations(FIXTURES / "test.pdf")
        assert isinstance(annotations, list)

    def test_extract_annotations_returns_list_of_dicts(self):
        annotations = self.extractor.extract_annotations(FIXTURES / "test.pdf")
        for ann in annotations:
            assert isinstance(ann, dict)

    def test_extract_annotations_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            self.extractor.extract_annotations(FIXTURES / "nonexistent.pdf")

    def test_extract_doi_returns_string_or_none(self):
        result = self.extractor.extract_doi(FIXTURES / "test.pdf")
        assert result is None or isinstance(result, str)

    def test_extract_doi_nonexistent_returns_none(self):
        result = self.extractor.extract_doi(FIXTURES / "nonexistent.pdf")
        assert result is None

    def test_pymupdf4llm_available_flag(self):
        result = self.extractor._check_pymupdf4llm()
        assert isinstance(result, bool)
