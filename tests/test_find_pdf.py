"""Tests for the local-bridge client and `zot find-pdf` CLI command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.local_bridge import LocalBridgeError, find_pdf, ping


def _mock_response(status: int, payload: dict | None = None, *, text: str | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = payload if payload is not None else {}
    if text is not None:
        resp.text = text
    elif payload is not None:
        import json as _json

        resp.text = _json.dumps(payload)
    else:
        resp.text = ""
    return resp


# ---------------------------------------------------------------------------
# core/local_bridge.py
# ---------------------------------------------------------------------------


class TestPing:
    @patch("zotero_cli_cc.core.local_bridge.httpx.get")
    def test_ok(self, mock_get):
        mock_get.return_value = _mock_response(200, {"ok": True, "bridge_version": "0.1.0", "zotero_version": "7.0.0"})
        info = ping()
        assert info["bridge_version"] == "0.1.0"
        assert info["zotero_version"] == "7.0.0"
        # UA must not start with Mozilla/ — Zotero blocks browser-origin requests.
        ua = mock_get.call_args.kwargs["headers"]["User-Agent"]
        assert not ua.startswith("Mozilla/")

    @patch("zotero_cli_cc.core.local_bridge.httpx.get")
    def test_zotero_not_running(self, mock_get):
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(LocalBridgeError) as exc:
            ping()
        assert exc.value.code == "not_reachable"
        assert exc.value.retryable is True

    @patch("zotero_cli_cc.core.local_bridge.httpx.get")
    def test_bridge_plugin_missing(self, mock_get):
        # Zotero is up, but the plugin isn't installed → /zot-cli/ping → 404
        mock_get.return_value = _mock_response(404)
        with pytest.raises(LocalBridgeError) as exc:
            ping()
        assert exc.value.code == "bridge_missing"
        assert exc.value.retryable is False


class TestFindPdf:
    @patch("zotero_cli_cc.core.local_bridge.httpx.post")
    def test_found(self, mock_post):
        mock_post.return_value = _mock_response(
            200,
            {
                "ok": True,
                "found": True,
                "key": "ABCD1234",
                "attachment_key": "ATT0001",
                "filename": "paper.pdf",
                "content_type": "application/pdf",
            },
        )
        result = find_pdf("ABCD1234")
        assert result["found"] is True
        assert result["attachment_key"] == "ATT0001"
        # Verify body and headers
        kwargs = mock_post.call_args.kwargs
        assert kwargs["json"] == {"key": "ABCD1234"}
        assert not kwargs["headers"]["User-Agent"].startswith("Mozilla/")

    @patch("zotero_cli_cc.core.local_bridge.httpx.post")
    def test_not_found_resolvers(self, mock_post):
        mock_post.return_value = _mock_response(
            200, {"ok": True, "found": False, "key": "ABCD1234", "message": "No PDF found"}
        )
        result = find_pdf("ABCD1234")
        assert result["found"] is False
        assert "No PDF" in result["message"]

    @patch("zotero_cli_cc.core.local_bridge.httpx.post")
    def test_item_not_found(self, mock_post):
        # 404 with body that disambiguates from "endpoint missing"
        mock_post.return_value = _mock_response(404, {"error": "item not found"})
        with pytest.raises(LocalBridgeError) as exc:
            find_pdf("MISSING")
        assert exc.value.code == "not_found"
        assert exc.value.retryable is False

    @patch("zotero_cli_cc.core.local_bridge.httpx.post")
    def test_endpoint_missing(self, mock_post):
        # 404 with empty body → endpoint not registered → plugin not installed
        mock_post.return_value = _mock_response(404)
        with pytest.raises(LocalBridgeError) as exc:
            find_pdf("ABCD1234")
        assert exc.value.code == "bridge_missing"

    @patch("zotero_cli_cc.core.local_bridge.httpx.post")
    def test_validation_error(self, mock_post):
        mock_post.return_value = _mock_response(400, {"error": "missing 'key'"})
        with pytest.raises(LocalBridgeError) as exc:
            find_pdf("")
        assert exc.value.code == "validation_error"

    @patch("zotero_cli_cc.core.local_bridge.httpx.post")
    def test_bridge_5xx_retryable(self, mock_post):
        mock_post.return_value = _mock_response(500, {"ok": False, "error": "boom"})
        with pytest.raises(LocalBridgeError) as exc:
            find_pdf("ABCD1234")
        assert exc.value.code == "bridge_error"
        assert exc.value.retryable is True

    @patch("zotero_cli_cc.core.local_bridge.httpx.post")
    def test_zotero_not_running(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(LocalBridgeError) as exc:
            find_pdf("ABCD1234")
        assert exc.value.code == "not_reachable"
        assert exc.value.retryable is True

    @patch("zotero_cli_cc.core.local_bridge.httpx.post")
    def test_timeout(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("read timed out")
        with pytest.raises(LocalBridgeError) as exc:
            find_pdf("ABCD1234", timeout=1.0)
        assert exc.value.code == "network_error"
        assert exc.value.retryable is True

    @patch("zotero_cli_cc.core.local_bridge.httpx.post")
    def test_library_id_forwarded(self, mock_post):
        mock_post.return_value = _mock_response(200, {"ok": True, "found": False})
        find_pdf("ABCD1234", library_id=42)
        assert mock_post.call_args.kwargs["json"] == {"key": "ABCD1234", "libraryID": 42}


# ---------------------------------------------------------------------------
# `zot find-pdf` CLI command
# ---------------------------------------------------------------------------


class TestFindPdfCli:
    @patch("zotero_cli_cc.commands.find_pdf.find_pdf")
    def test_found_human(self, mock_find):
        mock_find.return_value = {
            "ok": True,
            "found": True,
            "key": "ABCD1234",
            "attachment_key": "ATT0001",
            "filename": "paper.pdf",
            "content_type": "application/pdf",
        }
        runner = CliRunner()
        result = runner.invoke(main, ["find-pdf", "ABCD1234"])
        assert result.exit_code == 0
        assert "ATT0001" in result.output

    @patch("zotero_cli_cc.commands.find_pdf.find_pdf")
    def test_found_json_envelope(self, mock_find):
        mock_find.return_value = {
            "ok": True,
            "found": True,
            "key": "ABCD1234",
            "attachment_key": "ATT0001",
            "filename": "paper.pdf",
            "content_type": "application/pdf",
        }
        runner = CliRunner()
        result = runner.invoke(main, ["--json", "find-pdf", "ABCD1234"])
        assert result.exit_code == 0
        import json as _json

        env = _json.loads(result.output)
        assert env["ok"] is True
        assert env["data"]["found"] is True
        assert env["data"]["attachment_key"] == "ATT0001"
        assert env["data"]["sync_required"] is True

    @patch("zotero_cli_cc.commands.find_pdf.find_pdf")
    def test_not_found(self, mock_find):
        mock_find.return_value = {"ok": True, "found": False, "key": "ABCD1234", "message": "No PDF found"}
        runner = CliRunner()
        result = runner.invoke(main, ["--json", "find-pdf", "ABCD1234"])
        assert result.exit_code == 0
        import json as _json

        env = _json.loads(result.output)
        assert env["data"]["found"] is False
        assert env["data"]["sync_required"] is False

    @patch("zotero_cli_cc.commands.find_pdf.find_pdf")
    def test_bridge_missing_exit_code(self, mock_find):
        mock_find.side_effect = LocalBridgeError("plugin not installed", code="bridge_missing")
        runner = CliRunner()
        result = runner.invoke(main, ["find-pdf", "ABCD1234"])
        # bridge_missing maps to EXIT_VALIDATION (3) — it's a setup issue.
        assert result.exit_code == 3

    @patch("zotero_cli_cc.commands.find_pdf.find_pdf")
    def test_item_not_found_exit_code(self, mock_find):
        mock_find.side_effect = LocalBridgeError("Item 'X' not found", code="not_found")
        runner = CliRunner()
        result = runner.invoke(main, ["find-pdf", "X"])
        # `not_found` maps to EXIT_NOT_FOUND (4).
        assert result.exit_code == 4

    @patch("zotero_cli_cc.commands.find_pdf.ping")
    def test_dry_run_ping_only(self, mock_ping):
        mock_ping.return_value = {"bridge_version": "0.1.0", "zotero_version": "7.0.0"}
        runner = CliRunner()
        result = runner.invoke(main, ["find-pdf", "ABCD1234", "--dry-run"])
        assert result.exit_code == 0
        assert "7.0.0" in result.output

    @patch("zotero_cli_cc.commands.find_pdf.ping")
    def test_dry_run_bridge_not_reachable(self, mock_ping):
        mock_ping.side_effect = LocalBridgeError("not running", code="not_reachable", retryable=True)
        runner = CliRunner()
        result = runner.invoke(main, ["find-pdf", "ABCD1234", "--dry-run"])
        # not_reachable maps to EXIT_NETWORK (5).
        assert result.exit_code == 5
