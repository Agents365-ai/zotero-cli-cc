"""Tests for file attachment upload."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.local_bridge import LocalBridgeError
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


class TestImportFileClient:
    @staticmethod
    def _resp(status: int, body: dict | None):
        r = MagicMock()
        r.status_code = status
        r.json.return_value = body if body is not None else {}
        r.text = json.dumps(body) if body is not None else ""
        return r

    def test_success_returns_payload(self, monkeypatch):
        from zotero_cli_cc.core import local_bridge

        monkeypatch.setattr(
            local_bridge.httpx,
            "post",
            lambda *a, **k: self._resp(200, {"ok": True, "attachment_key": "ATT1", "imported": True}),
        )
        out = local_bridge.import_file("PARENT1", "/abs/paper.pdf")
        assert out["attachment_key"] == "ATT1"

    def test_404_with_error_is_not_found(self, monkeypatch):
        from zotero_cli_cc.core import local_bridge

        monkeypatch.setattr(
            local_bridge.httpx,
            "post",
            lambda *a, **k: self._resp(404, {"ok": False, "error": "file not found on disk"}),
        )
        with pytest.raises(LocalBridgeError) as ei:
            local_bridge.import_file("PARENT1", "/abs/missing.pdf")
        assert ei.value.code == "not_found"

    def test_404_without_error_is_bridge_missing(self, monkeypatch):
        from zotero_cli_cc.core import local_bridge

        monkeypatch.setattr(local_bridge.httpx, "post", lambda *a, **k: self._resp(404, None))
        with pytest.raises(LocalBridgeError) as ei:
            local_bridge.import_file("PARENT1", "/abs/paper.pdf")
        assert ei.value.code == "bridge_missing"


class TestAttachViaBridgeCLI:
    def test_via_bridge_success(self, tmp_path, monkeypatch):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 x")
        captured: dict = {}

        def fake_import(parent_key, path, **kw):
            captured.update(parent=parent_key, path=path, title=kw.get("title"))
            return {"imported": True, "attachment_key": "ATTLOCAL", "filename": "paper.pdf"}

        monkeypatch.setattr("zotero_cli_cc.commands.attach.import_file", fake_import)
        result = CliRunner().invoke(main, ["--json", "attach", "PARENT1", "--file", str(pdf), "--via-bridge"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["attachment_key"] == "ATTLOCAL"
        assert data["stored"] == "local"
        assert captured == {"parent": "PARENT1", "path": str(pdf.resolve()), "title": "paper.pdf"}

    def test_via_bridge_missing_plugin_exits_3(self, tmp_path, monkeypatch):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 x")

        def boom(*a, **k):
            raise LocalBridgeError("no endpoint", code="bridge_missing", retryable=False)

        monkeypatch.setattr("zotero_cli_cc.commands.attach.import_file", boom)
        result = CliRunner().invoke(main, ["attach", "PARENT1", "--file", str(pdf), "--via-bridge"])
        assert result.exit_code == 3

    def test_via_bridge_not_reachable_exits_5(self, tmp_path, monkeypatch):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 x")

        def boom(*a, **k):
            raise LocalBridgeError("down", code="not_reachable", retryable=True)

        monkeypatch.setattr("zotero_cli_cc.commands.attach.import_file", boom)
        result = CliRunner().invoke(main, ["attach", "PARENT1", "--file", str(pdf), "--via-bridge"])
        assert result.exit_code == 5

    def test_via_bridge_dry_run_does_not_call(self, tmp_path, monkeypatch):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 x")
        monkeypatch.setattr(
            "zotero_cli_cc.commands.attach.import_file",
            lambda *a, **k: pytest.fail("import_file must not run on dry-run"),
        )
        result = CliRunner().invoke(main, ["attach", "PARENT1", "--file", str(pdf), "--via-bridge", "--dry-run"])
        assert result.exit_code == 0
        assert "local storage" in result.output


class TestAttachMCP:
    def test_handle_attach(self):
        from zotero_cli_cc.mcp_server import _handle_attach

        with patch("zotero_cli_cc.mcp_server._get_writer") as mock_get:
            mock_writer = MagicMock()
            mock_get.return_value = mock_writer
            mock_writer.upload_attachment.return_value = "ATT001"
            result = _handle_attach("PARENT1", "/tmp/test.pdf")
            assert result["key"] == "ATT001"
            assert result["stored"] == "cloud"

    def test_handle_attach_via_bridge(self, tmp_path):
        from zotero_cli_cc import mcp_server

        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 x")
        with patch("zotero_cli_cc.core.local_bridge.import_file") as mock_import:
            mock_import.return_value = {"attachment_key": "ATTLOCAL", "filename": "paper.pdf"}
            result = mcp_server._handle_attach("PARENT1", str(pdf), via_bridge=True)
            assert result["key"] == "ATTLOCAL"
            assert result["stored"] == "local"
            mock_import.assert_called_once()
