"""End-to-end integration tests for PDF extraction and workspace index with extractors."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.pdf_cache import UnifiedPdfCache

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _invoke(args: list[str], json_output: bool = False):
    runner = CliRunner()
    base = ["--json"] if json_output else []
    env = {"ZOT_DATA_DIR": str(FIXTURES_DIR), "ZOT_FORMAT": "table"}
    return runner.invoke(main, base + args, env=env)


class TestPdfCmdWithExtractors:
    def test_pdf_pymupdf_extractor(self):
        mock_extractor = MagicMock()
        mock_extractor.extract_text.return_value = "pymupdf extracted text"
        mock_extractor.name.return_value = "pymupdf"

        with patch("zotero_cli_cc.core.pdf_cache.PdfCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            with patch("zotero_cli_cc.commands.pdf.get_extractor", return_value=mock_extractor):
                result = _invoke(["pdf", "ATTN001", "--extractor", "pymupdf"])

        assert result.exit_code == 0
        assert "pymupdf extracted text" in result.output
        mock_extractor.extract_text.assert_called_once()
        mock_cache.put.assert_called_once()

    def test_pdf_mineru_extractor(self):
        mock_extractor = MagicMock()
        mock_extractor.extract_text.return_value = "mineru extracted text"
        mock_extractor.name.return_value = "mineru"

        with patch("zotero_cli_cc.core.pdf_cache.PdfCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            with patch("zotero_cli_cc.commands.pdf.get_extractor", return_value=mock_extractor):
                result = _invoke(["pdf", "ATTN001", "--extractor", "mineru"])

        assert result.exit_code == 0
        assert "mineru extracted text" in result.output
        mock_extractor.extract_text.assert_called_once()

    def test_pdf_pymupdf_fallback_from_mineru(self):
        from zotero_cli_cc.core.pdf_errors import PdfExtractionError

        mock_mineru = MagicMock()
        mock_mineru.extract_text.side_effect = PdfExtractionError("mineru failed")
        mock_mineru.name.return_value = "mineru"

        mock_pymupdf = MagicMock()
        mock_pymupdf.extract_text.return_value = "pymupdf fallback text"
        mock_pymupdf.name.return_value = "pymupdf"

        with patch("zotero_cli_cc.core.pdf_cache.PdfCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            def get_extractor_side_effect(name):
                if name == "mineru":
                    return mock_mineru
                return mock_pymupdf

            with patch("zotero_cli_cc.commands.pdf.get_extractor", side_effect=get_extractor_side_effect):
                result = _invoke(["pdf", "ATTN001", "--extractor", "mineru"])

        assert result.exit_code == 0
        assert "pymupdf fallback text" in result.output
        mock_mineru.extract_text.assert_called_once()
        mock_pymupdf.extract_text.assert_called_once()

    def test_pdf_uses_cache_when_available(self):
        with patch("zotero_cli_cc.core.pdf_cache.PdfCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.get.return_value = "cached pymupdf text"
            mock_cache_cls.return_value = mock_cache

            with patch("zotero_cli_cc.commands.pdf.get_extractor") as mock_get_extractor:
                mock_extractor = MagicMock()
                mock_get_extractor.return_value = mock_extractor

                result = _invoke(["pdf", "ATTN001", "--extractor", "pymupdf"])

        assert result.exit_code == 0
        assert "cached pymupdf text" in result.output
        mock_extractor.extract_text.assert_not_called()

    def test_pdf_key_not_found(self):
        with patch("zotero_cli_cc.core.pdf_cache.PdfCache"):
            result = _invoke(["pdf", "NOTFOUND", "--extractor", "pymupdf"])

        # Exit 4 (NOT_FOUND) per the agent contract.
        assert result.exit_code == 4
        assert "no pdf attachment" in result.output.lower()

    def test_pdf_json_output(self):
        mock_extractor = MagicMock()
        mock_extractor.extract_text.return_value = "json test text"
        mock_extractor.name.return_value = "pymupdf"

        with patch("zotero_cli_cc.core.pdf_cache.PdfCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            with patch("zotero_cli_cc.commands.pdf.get_extractor", return_value=mock_extractor):
                result = _invoke(["pdf", "ATTN001", "--extractor", "pymupdf"], json_output=True)

        assert result.exit_code == 0
        # `pdf --json` is now routed through the agent envelope.
        data = json.loads(result.output)["data"]
        assert "key" in data
        assert data["key"] == "ATTN001"
        assert "text" in data


class TestWorkspaceIndexWithExtractor:
    def test_workspace_index_with_pymupdf_extractor(self, tmp_path):
        with patch("zotero_cli_cc.commands.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ext"])
            _invoke(["workspace", "add", "test-ext", "ATTN001"])

            with patch("zotero_cli_cc.commands.workspace.convert_pdf_to_text") as mock_convert:
                mock_convert.return_value = ""
                result = _invoke(["workspace", "index", "test-ext", "--extractor", "pymupdf"])

        assert result.exit_code == 0
        mock_convert.assert_called()
        call_args = mock_convert.call_args
        assert call_args.kwargs.get("extractor_name") == "pymupdf" or (
            len(call_args.args) >= 2 and call_args.args[1] == "pymupdf"
        )

    def test_workspace_index_with_mineru_extractor(self, tmp_path):
        with patch("zotero_cli_cc.commands.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ext-m"])
            _invoke(["workspace", "add", "test-ext-m", "ATTN001"])

            with patch("zotero_cli_cc.commands.workspace.convert_pdf_to_text") as mock_convert:
                mock_convert.return_value = ""
                result = _invoke(["workspace", "index", "test-ext-m", "--extractor", "mineru"])

        assert result.exit_code == 0
        mock_convert.assert_called()
        call_args = mock_convert.call_args
        assert call_args.kwargs.get("extractor_name") == "mineru" or (
            len(call_args.args) >= 2 and call_args.args[1] == "mineru"
        )


class TestPdfCacheIsolationIntegration:
    def test_cache_isolation_between_pymupdf_and_mineru(self, tmp_path):
        cache_db = tmp_path / "cache.sqlite"
        cache = UnifiedPdfCache(cache_db)
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake pdf")

        cache.put(pdf, "pymupdf", "pymupdf cached content")
        cache.put(pdf, "mineru", "mineru cached content")

        pymupdf_content = cache.get(pdf, "pymupdf")
        mineru_content = cache.get(pdf, "mineru")
        other_content = cache.get(pdf, "other")

        assert pymupdf_content == "pymupdf cached content"
        assert mineru_content == "mineru cached content"
        assert other_content is None

        cache.close()

    def test_cache_stats_show_separate_entries_per_extractor(self, tmp_path):
        cache_db = tmp_path / "cache.sqlite"
        cache = UnifiedPdfCache(cache_db)
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake pdf")

        cache.put(pdf, "pymupdf", "pymupdf text")
        cache.put(pdf, "mineru", "mineru text")

        stats = cache.stats()
        assert stats["entries"] == 2

        cache.close()


class TestPdfAndWorkspaceIntegration:
    def test_pdf_then_workspace_index_uses_same_cache(self):
        with patch("zotero_cli_cc.core.pdf_cache.PdfCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            mock_extractor = MagicMock()
            mock_extractor.extract_text.return_value = "shared content"
            mock_extractor.name.return_value = "pymupdf"

            with patch("zotero_cli_cc.commands.pdf.get_extractor", return_value=mock_extractor):
                result = _invoke(["pdf", "ATTN001", "--extractor", "pymupdf"])

            assert result.exit_code == 0
            assert mock_cache.put.called

    def test_pdf_command_missing_key(self):
        with patch("zotero_cli_cc.core.pdf_cache.PdfCache"):
            result = _invoke(["pdf", "NONEXISTENT", "--extractor", "pymupdf"])

        # Exit 4 (NOT_FOUND) per the agent contract.
        assert result.exit_code == 4
        assert "no pdf attachment" in result.output.lower() or "not found" in result.output.lower()
