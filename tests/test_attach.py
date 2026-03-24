"""Tests for file attachment upload."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zotero_cli_cc.core.writer import ZoteroWriteError, ZoteroWriter


class TestAttachWriter:
    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_upload_attachment_success(self, mock_zotero_cls, tmp_path):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        mock_zot.attachment_simple.return_value = {
            "success": [{"key": "ATT001", "filename": "test.pdf"}],
            "failure": [],
            "unchanged": [],
        }
        writer = ZoteroWriter(library_id="123", api_key="abc")
        key = writer.upload_attachment("PARENT1", pdf)
        assert key == "ATT001"
        mock_zot.attachment_simple.assert_called_once()

    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_upload_attachment_unchanged(self, mock_zotero_cls, tmp_path):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        mock_zot.attachment_simple.return_value = {
            "success": [],
            "failure": [],
            "unchanged": [{"key": "ATT001"}],
        }
        writer = ZoteroWriter(library_id="123", api_key="abc")
        key = writer.upload_attachment("PARENT1", pdf)
        assert key == "ATT001"

    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_upload_attachment_failure(self, mock_zotero_cls, tmp_path):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        mock_zot.attachment_simple.return_value = {
            "success": [],
            "failure": [{"key": "", "message": "Upload failed"}],
            "unchanged": [],
        }
        writer = ZoteroWriter(library_id="123", api_key="abc")
        with pytest.raises(ZoteroWriteError, match="Upload failed"):
            writer.upload_attachment("PARENT1", pdf)

    def test_upload_attachment_file_not_found(self):
        with patch("zotero_cli_cc.core.writer.zotero.Zotero"):
            writer = ZoteroWriter(library_id="123", api_key="abc")
            with pytest.raises(ZoteroWriteError, match="not found"):
                writer.upload_attachment("PARENT1", Path("/nonexistent/file.pdf"))

    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_upload_attachment_empty_response(self, mock_zotero_cls, tmp_path):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        mock_zot.attachment_simple.return_value = {
            "success": [],
            "failure": [],
            "unchanged": [],
        }
        writer = ZoteroWriter(library_id="123", api_key="abc")
        with pytest.raises(ZoteroWriteError, match="Unexpected"):
            writer.upload_attachment("PARENT1", pdf)


class TestAttachMCP:
    def test_handle_attach(self):
        from zotero_cli_cc.mcp_server import _handle_attach

        with patch("zotero_cli_cc.mcp_server._get_writer") as mock_get:
            mock_writer = MagicMock()
            mock_get.return_value = mock_writer
            mock_writer.upload_attachment.return_value = "ATT001"
            result = _handle_attach("PARENT1", "/tmp/test.pdf")
            assert result["key"] == "ATT001"
