"""Tests for MinerU -> PyMuPDF fallback logic."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.pdf_errors import PdfExtractionError


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _invoke(args):
    runner = CliRunner()
    env = {"ZOT_DATA_DIR": str(FIXTURES_DIR), "ZOT_FORMAT": "table"}
    return runner.invoke(main, args, env=env)


class TestMinerUFallback:
    def test_mineru_failure_triggers_pymupdf_fallback(self):
        mock_mineru = MagicMock()
        mock_mineru.extract_text.side_effect = PdfExtractionError("MinerU failed")

        mock_pymupdf = MagicMock()
        mock_pymupdf.extract_text.return_value = "fallback text from pymupdf"

        def get_extractor_side_effect(name):
            if name == "mineru":
                return mock_mineru
            return mock_pymupdf

        with patch("zotero_cli_cc.core.pdf_cache.PdfCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            with patch("zotero_cli_cc.commands.pdf.get_extractor", side_effect=get_extractor_side_effect):
                result = _invoke(["pdf", "ATTN001", "--extractor", "mineru"])

            assert result.exit_code == 0, result.output
            assert "fallback text from pymupdf" in result.output
            mock_pymupdf.extract_text.assert_called_once()

    def test_fallback_result_is_correct(self):
        expected_text = "pymupdf fallback text"

        mock_mineru = MagicMock()
        mock_mineru.extract_text.side_effect = PdfExtractionError("MinerU failed")

        mock_pymupdf = MagicMock()
        mock_pymupdf.extract_text.return_value = expected_text

        def get_extractor_side_effect(name):
            if name == "mineru":
                return mock_mineru
            return mock_pymupdf

        with patch("zotero_cli_cc.core.pdf_cache.PdfCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            with patch("zotero_cli_cc.commands.pdf.get_extractor", side_effect=get_extractor_side_effect):
                result = _invoke(["pdf", "ATTN001", "--extractor", "mineru"])

            assert result.exit_code == 0, result.output
            assert expected_text in result.output

    def test_fallback_uses_pymupdf_cache_key(self):
        mock_mineru = MagicMock()
        mock_mineru.extract_text.side_effect = PdfExtractionError("MinerU failed")

        mock_pymupdf = MagicMock()
        mock_pymupdf.extract_text.return_value = "pymupdf result"

        def get_extractor_side_effect(name):
            if name == "mineru":
                return mock_mineru
            return mock_pymupdf

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        with patch("zotero_cli_cc.core.pdf_cache.PdfCache", return_value=mock_cache):
            with patch("zotero_cli_cc.commands.pdf.get_extractor", side_effect=get_extractor_side_effect):
                result = _invoke(["pdf", "ATTN001", "--extractor", "mineru"])

            assert result.exit_code == 0, result.output
            assert result.output.rstrip("\n") == "pymupdf result"
            mock_pymupdf.extract_text.assert_called_once()
            mock_mineru.extract_text.assert_called_once()
            mock_cache.put.assert_called()

    def test_pymupdf_also_fails_exception_propagates(self):
        mock_mineru = MagicMock()
        mock_mineru.extract_text.side_effect = PdfExtractionError("MinerU failed")

        mock_pymupdf = MagicMock()
        mock_pymupdf.extract_text.side_effect = PdfExtractionError("pymupdf also failed")

        def get_extractor_side_effect(name):
            if name == "mineru":
                return mock_mineru
            return mock_pymupdf

        with patch("zotero_cli_cc.core.pdf_cache.PdfCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            with patch("zotero_cli_cc.commands.pdf.get_extractor", side_effect=get_extractor_side_effect):
                result = _invoke(["pdf", "ATTN001", "--extractor", "mineru"])

            assert result.exit_code == 0, result.output
            assert "pymupdf also failed" in result.output

    def test_fallback_with_page_range(self):
        mock_mineru = MagicMock()
        mock_mineru.extract_text.side_effect = PdfExtractionError("MinerU failed")

        mock_pymupdf = MagicMock()
        mock_pymupdf.extract_text.return_value = "pages 1-5 via pymupdf"

        def get_extractor_side_effect(name):
            if name == "mineru":
                return mock_mineru
            return mock_pymupdf

        with patch("zotero_cli_cc.core.pdf_cache.PdfCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            with patch("zotero_cli_cc.commands.pdf.get_extractor", side_effect=get_extractor_side_effect):
                result = _invoke(["pdf", "ATTN001", "--extractor", "mineru", "--pages", "1-5"])

            assert result.exit_code == 0, result.output
            assert "pages 1-5 via pymupdf" in result.output
            mock_pymupdf.extract_text.assert_called_once()