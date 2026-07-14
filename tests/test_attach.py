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
        key, result = writer.upload_attachment("PARENT1", pdf)
        assert key == "ATT001"
        assert result == "created"
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
        key, result = writer.upload_attachment("PARENT1", pdf)
        assert key == "ATT001"
        assert result == "exists"

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
            mock_writer.upload_attachment.return_value = ("ATT001", "created")
            result = _handle_attach("PARENT1", "/tmp/test.pdf", via_bridge=False)
            assert result["key"] == "ATT001"
            assert result["stored"] == "cloud"
            assert result["result"] == "created"

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

    def test_handle_attach_group_via_bridge(self, tmp_path, monkeypatch):
        from zotero_cli_cc import mcp_server

        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 x")
        monkeypatch.setattr("zotero_cli_cc.core.local_bridge.ping", lambda *a, **k: {"bridge_version": "0.4.0"})
        captured: dict = {}

        def fake_import(parent, path, **kw):
            captured["group_id"] = kw.get("group_id")
            return {"attachment_key": "ATTG", "filename": "paper.pdf"}

        monkeypatch.setattr("zotero_cli_cc.core.local_bridge.import_file", fake_import)
        result = mcp_server._handle_attach("PARENT1", str(pdf), library="group:123", via_bridge=True)
        assert result["key"] == "ATTG"
        assert captured["group_id"] == 123


class TestResolveUseBridge:
    def test_explicit_true_skips_ping(self, monkeypatch):
        from zotero_cli_cc.core import local_bridge

        monkeypatch.setattr(local_bridge, "ping", lambda *a, **k: pytest.fail("ping must not run when forced on"))
        assert local_bridge.resolve_use_bridge(True) is True

    def test_explicit_false_skips_ping(self, monkeypatch):
        from zotero_cli_cc.core import local_bridge

        monkeypatch.setattr(local_bridge, "ping", lambda *a, **k: pytest.fail("ping must not run when forced off"))
        assert local_bridge.resolve_use_bridge(False) is False

    def test_auto_uses_bridge_when_reachable(self, monkeypatch):
        from zotero_cli_cc.core import local_bridge

        monkeypatch.setattr(local_bridge, "ping", lambda *a, **k: {"ok": True})
        assert local_bridge.resolve_use_bridge(None) is True

    def test_auto_falls_back_when_down(self, monkeypatch):
        from zotero_cli_cc.core import local_bridge

        def boom(*a, **k):
            raise LocalBridgeError("down", code="not_reachable", retryable=True)

        monkeypatch.setattr(local_bridge, "ping", boom)
        assert local_bridge.resolve_use_bridge(None) is False


class TestAttachWebResultCLI:
    @staticmethod
    def _pdf(tmp_path):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 x")
        return pdf

    def _mock_writer(self, monkeypatch, key, result):
        monkeypatch.setenv("ZOT_LIBRARY_ID", "123")
        monkeypatch.setenv("ZOT_API_KEY", "abc")
        writer = MagicMock()
        writer.upload_attachment.return_value = (key, result)
        monkeypatch.setattr("zotero_cli_cc.commands._helpers.ZoteroWriter", lambda **k: writer)

    def test_cloud_result_created(self, tmp_path, monkeypatch):
        pdf = self._pdf(tmp_path)
        self._mock_writer(monkeypatch, "ATTCLOUD", "created")
        result = CliRunner().invoke(main, ["--json", "attach", "P1", "--file", str(pdf), "--no-via-bridge"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["stored"] == "cloud"
        assert data["result"] == "created"

    def test_cloud_result_exists_human(self, tmp_path, monkeypatch):
        pdf = self._pdf(tmp_path)
        self._mock_writer(monkeypatch, "ATTCLOUD", "exists")
        result = CliRunner().invoke(main, ["attach", "P1", "--file", str(pdf), "--no-via-bridge"])
        assert result.exit_code == 0
        assert "already present" in result.output

    def test_auto_prefers_bridge_when_up(self, tmp_path, monkeypatch):
        pdf = self._pdf(tmp_path)
        monkeypatch.setattr("zotero_cli_cc.core.local_bridge.ping", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(
            "zotero_cli_cc.commands.attach.import_file",
            lambda *a, **k: {"imported": True, "attachment_key": "ATTL", "filename": "paper.pdf"},
        )
        result = CliRunner().invoke(main, ["--json", "attach", "P1", "--file", str(pdf)])
        assert result.exit_code == 0
        assert json.loads(result.output)["data"]["stored"] == "local"

    def test_auto_falls_back_to_cloud_when_down(self, tmp_path, monkeypatch):
        pdf = self._pdf(tmp_path)

        def boom(*a, **k):
            raise LocalBridgeError("down", code="not_reachable", retryable=True)

        monkeypatch.setattr("zotero_cli_cc.core.local_bridge.ping", boom)
        self._mock_writer(monkeypatch, "ATTCLOUD", "created")
        result = CliRunner().invoke(main, ["--json", "attach", "P1", "--file", str(pdf)])
        assert result.exit_code == 0
        assert json.loads(result.output)["data"]["stored"] == "cloud"


class TestGroupImportSupport:
    def test_import_file_sends_group_id(self, monkeypatch):
        from zotero_cli_cc.core import local_bridge

        captured: dict = {}

        def fake_post(url, **kw):
            captured["json"] = kw.get("json")
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {"ok": True, "attachment_key": "ATT1", "imported": True}
            r.text = "{}"
            return r

        monkeypatch.setattr(local_bridge.httpx, "post", fake_post)
        local_bridge.import_file("PARENT1", "/abs/p.pdf", group_id=123)
        assert captured["json"]["groupID"] == 123
        assert "libraryID" not in captured["json"]

    def test_ensure_ok_on_new_bridge(self, monkeypatch):
        from zotero_cli_cc.core import local_bridge

        monkeypatch.setattr(local_bridge, "ping", lambda *a, **k: {"bridge_version": "0.4.0"})
        local_bridge.ensure_group_import_supported()  # must not raise

    def test_ensure_raises_on_old_bridge(self, monkeypatch):
        from zotero_cli_cc.core import local_bridge

        monkeypatch.setattr(local_bridge, "ping", lambda *a, **k: {"bridge_version": "0.3.0"})
        with pytest.raises(LocalBridgeError) as ei:
            local_bridge.ensure_group_import_supported()
        assert ei.value.code == "bridge_missing"


class TestAttachGroupBridgeCLI:
    @staticmethod
    def _pdf(tmp_path):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 x")
        return pdf

    def test_group_import_passes_group_id(self, tmp_path, monkeypatch):
        pdf = self._pdf(tmp_path)
        monkeypatch.setattr("zotero_cli_cc.core.local_bridge.ping", lambda *a, **k: {"bridge_version": "0.4.0"})
        captured: dict = {}

        def fake_import(parent, path, **kw):
            captured.update(parent=parent, group_id=kw.get("group_id"))
            return {"imported": True, "attachment_key": "ATTG", "filename": "paper.pdf"}

        monkeypatch.setattr("zotero_cli_cc.commands.attach.import_file", fake_import)
        result = CliRunner().invoke(
            main, ["--json", "--library", "group:123", "attach", "P1", "--file", str(pdf), "--via-bridge"]
        )
        assert result.exit_code == 0
        assert captured["group_id"] == 123
        assert json.loads(result.output)["data"]["stored"] == "local"

    def test_group_import_old_bridge_exits_3(self, tmp_path, monkeypatch):
        pdf = self._pdf(tmp_path)
        monkeypatch.setattr("zotero_cli_cc.core.local_bridge.ping", lambda *a, **k: {"bridge_version": "0.3.0"})
        monkeypatch.setattr(
            "zotero_cli_cc.commands.attach.import_file",
            lambda *a, **k: pytest.fail("import_file must not run when the bridge is too old"),
        )
        result = CliRunner().invoke(
            main, ["--library", "group:123", "attach", "P1", "--file", str(pdf), "--via-bridge"]
        )
        assert result.exit_code == 3

    def test_user_import_does_not_check_version(self, tmp_path, monkeypatch):
        pdf = self._pdf(tmp_path)
        monkeypatch.setattr(
            "zotero_cli_cc.core.local_bridge.ping",
            lambda *a, **k: pytest.fail("user-library import must not version-check"),
        )
        captured: dict = {}

        def fake_import(parent, path, **kw):
            captured["group_id"] = kw.get("group_id")
            return {"imported": True, "attachment_key": "ATTU", "filename": "paper.pdf"}

        monkeypatch.setattr("zotero_cli_cc.commands.attach.import_file", fake_import)
        result = CliRunner().invoke(main, ["--json", "attach", "P1", "--file", str(pdf), "--via-bridge"])
        assert result.exit_code == 0
        assert captured["group_id"] is None
