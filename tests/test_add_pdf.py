"""Tests for add-from-PDF feature."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zotero_cli_cc.core.pdf_extractor import extract_doi


class TestExtractDoi:
    def test_extract_doi_found(self, tmp_path):
        with patch("zotero_cli_cc.core.pdf_extractor.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "Some text with DOI 10.1038/s41586-023-06139-9 in it"
            result = extract_doi(tmp_path / "dummy.pdf")
            assert result == "10.1038/s41586-023-06139-9"

    def test_extract_doi_not_found(self, tmp_path):
        with patch("zotero_cli_cc.core.pdf_extractor.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "No DOI in this text"
            result = extract_doi(tmp_path / "dummy.pdf")
            assert result is None

    def test_extract_doi_strips_trailing_punctuation(self, tmp_path):
        with patch("zotero_cli_cc.core.pdf_extractor.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "DOI: 10.1234/test.paper)."
            result = extract_doi(tmp_path / "dummy.pdf")
            assert result == "10.1234/test.paper"

    def test_extract_doi_multiple_returns_first(self, tmp_path):
        with patch("zotero_cli_cc.core.pdf_extractor.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "10.1234/first and 10.5678/second"
            result = extract_doi(tmp_path / "dummy.pdf")
            assert result == "10.1234/first"


class TestAddPdfMCP:
    def test_handle_add_from_pdf_with_doi_override(self):
        from zotero_cli_cc.mcp_server import _handle_add_from_pdf
        with patch("zotero_cli_cc.mcp_server._get_writer") as mock_get:
            mock_writer = MagicMock()
            mock_get.return_value = mock_writer
            mock_writer.add_item.return_value = "NEW001"
            mock_writer.upload_attachment.return_value = "ATT001"
            result = _handle_add_from_pdf("/tmp/test.pdf", doi_override="10.1234/test")
            mock_writer.add_item.assert_called_once_with(doi="10.1234/test")
            assert result["item_key"] == "NEW001"
            assert result["attachment_key"] == "ATT001"

    def test_handle_add_from_pdf_no_doi_found(self):
        from zotero_cli_cc.mcp_server import _handle_add_from_pdf
        with patch("zotero_cli_cc.mcp_server._get_writer"), \
             patch("zotero_cli_cc.core.pdf_extractor.extract_doi", return_value=None):
            result = _handle_add_from_pdf("/tmp/test.pdf")
            assert "error" in result

    def test_handle_add_from_pdf_upload_fails(self):
        from zotero_cli_cc.mcp_server import _handle_add_from_pdf
        from zotero_cli_cc.core.writer import ZoteroWriteError
        with patch("zotero_cli_cc.mcp_server._get_writer") as mock_get, \
             patch("zotero_cli_cc.core.pdf_extractor.extract_doi", return_value="10.1234/test"):
            mock_writer = MagicMock()
            mock_get.return_value = mock_writer
            mock_writer.add_item.return_value = "NEW001"
            mock_writer.upload_attachment.side_effect = ZoteroWriteError("Upload failed")
            result = _handle_add_from_pdf("/tmp/test.pdf")
            assert result["item_key"] == "NEW001"
            assert "error" in result
            assert "Retry with" in result["error"]
