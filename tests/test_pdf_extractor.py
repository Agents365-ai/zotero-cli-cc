from pathlib import Path

import pytest

from zotero_cli_cc.core.pdf_extractor import PyMuPdfExtractor

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_full_pdf():
    text = PyMuPdfExtractor().extract_text(FIXTURES / "test.pdf")
    assert "test PDF" in text


def test_extract_specific_pages():
    text = PyMuPdfExtractor().extract_text(FIXTURES / "test.pdf", pages=(1, 1))
    assert "test PDF" in text


def test_extract_nonexistent_pdf():
    with pytest.raises(FileNotFoundError):
        PyMuPdfExtractor().extract_text(FIXTURES / "nonexistent.pdf")
