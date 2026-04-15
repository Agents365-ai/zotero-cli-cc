"""P1 tests: dry-run coverage, idempotency, meta slot, safety tiers, next hints."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core import idempotency
from zotero_cli_cc.exit_codes import EXIT_OK

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _run(args, env=None):
    runner = CliRunner()
    base_env = {"ZOT_DATA_DIR": str(FIXTURES_DIR), "ZOT_FORMAT": ""}
    if env:
        base_env.update(env)
    return runner.invoke(main, args, env=base_env)


class TestDryRunCoverage:
    WRITE_ENV = {"ZOT_LIBRARY_ID": "abc", "ZOT_API_KEY": "xyz"}

    def test_add_dry_run(self):
        result = _run(["add", "--doi", "10.1/x", "--dry-run"], env=self.WRITE_ENV)
        assert result.exit_code == EXIT_OK
        env = json.loads(result.output)
        assert env["ok"] is True
        assert env.get("dry_run") is True
        assert env["data"]["would"]["doi"] == "10.1/x"

    def test_update_dry_run(self):
        result = _run(
            ["update", "ABC123", "--title", "New", "--dry-run"],
            env=self.WRITE_ENV,
        )
        assert result.exit_code == EXIT_OK
        env = json.loads(result.output)
        assert env.get("dry_run") is True
        assert env["data"]["would"]["key"] == "ABC123"
        assert env["data"]["would"]["fields"]["title"] == "New"

    def test_note_add_dry_run(self):
        result = _run(
            ["note", "ABC123", "--add", "hello world", "--dry-run"],
            env=self.WRITE_ENV,
        )
        assert result.exit_code == EXIT_OK
        env = json.loads(result.output)
        assert env.get("dry_run") is True
        assert env["data"]["would"]["parent"] == "ABC123"

    def test_attach_dry_run(self, tmp_path):
        f = tmp_path / "x.pdf"
        f.write_bytes(b"fake")
        result = _run(
            ["attach", "ABC123", "--file", str(f), "--dry-run"],
            env=self.WRITE_ENV,
        )
        assert result.exit_code == EXIT_OK
        env = json.loads(result.output)
        assert env.get("dry_run") is True
        assert env["data"]["would"]["parent"] == "ABC123"
        assert env["data"]["would"]["size_bytes"] == 4

    def test_delete_dry_run(self):
        result = _run(["delete", "A", "B", "--dry-run"], env=self.WRITE_ENV)
        env = json.loads(result.output)
        assert env["ok"] is True
        assert env.get("dry_run") is True
        assert env["data"]["would_delete"] == ["A", "B"]

    def test_trash_restore_dry_run(self):
        result = _run(["trash", "restore", "X", "--dry-run"], env=self.WRITE_ENV)
        env = json.loads(result.output)
        assert env["ok"] is True
        assert env.get("dry_run") is True
        assert env["data"]["would_restore"] == ["X"]


class TestMetaSlot:
    def test_success_envelope_has_request_id_and_latency(self):
        result = _run(["schema"])
        env = json.loads(result.output)
        assert "request_id" in env["meta"]
        assert isinstance(env["meta"]["request_id"], str)
        assert len(env["meta"]["request_id"]) >= 8
        assert "latency_ms" in env["meta"]
        assert isinstance(env["meta"]["latency_ms"], int)

    def test_error_envelope_has_request_id(self):
        result = _run(["read", "NOPE"])
        env = json.loads(result.output)
        assert env["ok"] is False
        assert "request_id" in env["meta"]

    def test_request_id_unique_per_invocation(self):
        a = json.loads(_run(["schema"]).output)
        b = json.loads(_run(["schema"]).output)
        assert a["meta"]["request_id"] != b["meta"]["request_id"]


class TestIdempotency:
    def setup_method(self, method):
        idempotency.clear()

    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_update_idempotency_returns_cached_envelope(self, mock_writer_cls):
        mock_writer_cls.return_value.update_item.return_value = None
        env = {"ZOT_LIBRARY_ID": "abc", "ZOT_API_KEY": "xyz"}
        args = ["update", "ABC", "--title", "T", "--idempotency-key", "k1"]
        first = _run(args, env=env)
        second = _run(args, env=env)
        # First call hits the writer; second call short-circuits.
        assert mock_writer_cls.return_value.update_item.call_count == 1
        env_first = json.loads(first.output)
        env_second = json.loads(second.output)
        # Cached envelope: request_id is the original one.
        assert env_second["meta"]["request_id"] == env_first["meta"]["request_id"]
        assert env_second["data"]["key"] == "ABC"

    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_update_without_idempotency_key_always_calls_writer(self, mock_writer_cls):
        mock_writer_cls.return_value.update_item.return_value = None
        env = {"ZOT_LIBRARY_ID": "abc", "ZOT_API_KEY": "xyz"}
        args = ["update", "ABC", "--title", "T"]
        _run(args, env=env)
        _run(args, env=env)
        assert mock_writer_cls.return_value.update_item.call_count == 2


class TestNextHints:
    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_update_success_has_next_hint(self, mock_writer_cls):
        idempotency.clear()
        mock_writer_cls.return_value.update_item.return_value = None
        env = {"ZOT_LIBRARY_ID": "abc", "ZOT_API_KEY": "xyz"}
        result = _run(["update", "ABC", "--title", "X"], env=env)
        data = json.loads(result.output)
        assert "next" in data
        assert any("zot read ABC" in hint for hint in data["next"])


class TestHelpTiers:
    def test_help_groups_commands_by_tier(self):
        result = _run(["--help"])
        assert result.exit_code == EXIT_OK
        out = result.output
        read_idx = out.find("Read commands")
        write_idx = out.find("Write commands")
        destructive_idx = out.find("Destructive commands")
        assert read_idx >= 0
        assert write_idx > read_idx
        assert destructive_idx > write_idx
        # Destructive names appear in the destructive section
        destructive_section = out[destructive_idx:]
        assert "delete" in destructive_section
        assert "update-status" in destructive_section

    def test_write_commands_marked_mutating(self):
        result = _run(["--help"])
        assert "MUTATES LIBRARY" in result.output

    def test_destructive_commands_help_carries_warning(self):
        result = _run(["delete", "--help"])
        assert "MUTATES LIBRARY" in result.output


class TestRetryableFlag:
    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_network_error_flagged_retryable(self, mock_writer_cls):
        from zotero_cli_cc.core.writer import ZoteroWriteError

        mock_writer_cls.return_value.update_item.side_effect = ZoteroWriteError(
            "Network error: boom", code="network_error", retryable=True
        )
        env = {"ZOT_LIBRARY_ID": "abc", "ZOT_API_KEY": "xyz"}
        result = _run(["update", "ABC", "--title", "X"], env=env)
        env_out = json.loads(result.output)
        assert env_out["ok"] is False
        assert env_out["error"]["code"] == "network_error"
        assert env_out["error"]["retryable"] is True

    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_not_found_flagged_not_retryable(self, mock_writer_cls):
        from zotero_cli_cc.core.writer import ZoteroWriteError

        mock_writer_cls.return_value.update_item.side_effect = ZoteroWriteError(
            "Item 'X' not found", code="not_found", retryable=False
        )
        env = {"ZOT_LIBRARY_ID": "abc", "ZOT_API_KEY": "xyz"}
        result = _run(["update", "X", "--title", "Y"], env=env)
        env_out = json.loads(result.output)
        assert env_out["error"]["code"] == "not_found"
        assert env_out["error"]["retryable"] is False
