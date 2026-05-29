from pathlib import Path

import pytest

from zotero_cli_cc.core.pdf_extractor import (
    PdfExtractionError,
    PdfiumExtractor,
    PdfplumberExtractor,
    _select_pages,
    get_extractor,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestSelectPages:
    def test_none_returns_all(self):
        assert _select_pages([1, 2, 3], None) == [1, 2, 3]

    def test_inclusive_range(self):
        assert _select_pages([10, 20, 30, 40], (2, 3)) == [20, 30]

    def test_single_page(self):
        assert _select_pages([10, 20, 30], (1, 1)) == [10]

    def test_invalid_start_raises(self):
        with pytest.raises(PdfExtractionError):
            _select_pages([1, 2], (0, 1))


class TestPdfplumberExtractor:
    def setup_method(self):
        self.extractor = PdfplumberExtractor()

    def test_name(self):
        assert self.extractor.name() == "pdfplumber"

    def test_registered(self):
        assert isinstance(get_extractor("pdfplumber"), PdfplumberExtractor)

    def test_annotations_empty(self):
        assert self.extractor.extract_annotations(FIXTURES / "test.pdf") == []

    def test_extract_text_returns_string(self):
        assert isinstance(self.extractor.extract_text(FIXTURES / "test.pdf"), str)

    def test_extract_tables_returns_list(self):
        # The fixture has no real table; extraction should still yield a list.
        result = self.extractor.extract_tables(FIXTURES / "test.pdf")
        assert isinstance(result, list)
        for t in result:
            assert set(t) >= {"page", "index", "rows"}
            assert isinstance(t["rows"], list)

    def test_extract_tables_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            self.extractor.extract_tables(FIXTURES / "nonexistent.pdf")

    def test_extract_doi_returns_string_or_none(self):
        result = self.extractor.extract_doi(FIXTURES / "test.pdf")
        assert result is None or isinstance(result, str)


class TestTablesNotSupportedByOthers:
    def test_pdfium_tables_raise(self):
        with pytest.raises(PdfExtractionError):
            PdfiumExtractor().extract_tables(FIXTURES / "test.pdf")
