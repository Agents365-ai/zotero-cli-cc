"""Tests for the agent-native CLI interface: envelope, TTY detect, exit codes, schema."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.exit_codes import (
    EXIT_AUTH,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_VALIDATION,
)
from zotero_cli_cc.formatter import envelope_error, envelope_ok, envelope_partial

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _run(args, env=None):
    """Invoke the CLI with TTY auto-detect active (no ZOT_FORMAT override)."""
    runner = CliRunner()
    # Explicitly clear conftest's ZOT_FORMAT=table so TTY auto-detect fires.
    base_env = {"ZOT_DATA_DIR": str(FIXTURES_DIR), "ZOT_FORMAT": ""}
    if env:
        base_env.update(env)
    return runner.invoke(main, args, env=base_env)


class TestEnvelopeShape:
    def test_envelope_ok_has_required_fields(self):
        env = envelope_ok({"x": 1})
        assert env["ok"] is True
        assert env["data"] == {"x": 1}
        assert env["meta"]["schema_version"]
        assert env["meta"]["cli_version"]

    def test_envelope_error_has_required_fields(self):
        env = envelope_error("not_found", "thing missing")
        assert env["ok"] is False
        assert env["error"]["code"] == "not_found"
        assert env["error"]["message"] == "thing missing"
        assert env["error"]["retryable"] is False
        assert env["meta"]["schema_version"]

    def test_envelope_partial_shape(self):
        env = envelope_partial([{"key": "A"}], [{"key": "B", "error": {"code": "x", "message": "y"}}])
        assert env["ok"] == "partial"
        assert env["data"]["succeeded"][0]["key"] == "A"
        assert env["data"]["failed"][0]["key"] == "B"


class TestTTYAutoDetect:
    def test_search_returns_json_when_stdout_not_tty(self):
        result = _run(["search", "attention"])
        assert result.exit_code == EXIT_OK
        env = json.loads(result.output)
        assert env["ok"] is True
        assert isinstance(env["data"], list)

    def test_explicit_json_flag_returns_envelope(self):
        result = _run(["--json", "search", "attention"])
        assert result.exit_code == EXIT_OK
        env = json.loads(result.output)
        assert env["ok"] is True

    def test_zot_format_table_forces_human_output(self):
        result = _run(["search", "attention"], env={"ZOT_FORMAT": "table"})
        assert result.exit_code == EXIT_OK
        # Rich table output includes column headers
        assert "Key" in result.output or "Title" in result.output
        # Should not be parseable JSON
        try:
            json.loads(result.output)
            is_json = True
        except ValueError:
            is_json = False
        assert not is_json


class TestExitCodes:
    def test_auth_missing_returns_exit_2(self):
        result = _run(["add", "--doi", "10.1/x"], env={"ZOT_LIBRARY_ID": "", "ZOT_API_KEY": ""})
        assert result.exit_code == EXIT_AUTH
        env = json.loads(result.output)
        assert env["error"]["code"] == "auth_missing"

    def test_validation_error_returns_exit_3(self):
        result = _run(["add"], env={"ZOT_LIBRARY_ID": "abc", "ZOT_API_KEY": "xyz"})
        assert result.exit_code == EXIT_VALIDATION
        env = json.loads(result.output)
        assert env["error"]["code"] == "validation_error"

    def test_not_found_returns_exit_4(self):
        result = _run(["read", "NONEXISTENT_KEY"])
        assert result.exit_code == EXIT_NOT_FOUND
        env = json.loads(result.output)
        assert env["error"]["code"] == "not_found"


class TestStderrRouting:
    def test_auth_error_envelope_on_stdout(self):
        # JSON envelope goes to stdout; prose goes to stderr when ZOT_FORMAT=table
        result = _run(["add", "--doi", "10.1/x"], env={"ZOT_LIBRARY_ID": "", "ZOT_API_KEY": ""})
        # default (non-TTY): JSON envelope on stdout
        assert result.output.strip().startswith("{")
        env = json.loads(result.output)
        assert env["ok"] is False

    def test_human_error_on_stderr_not_stdout(self):
        result = _run(
            ["add", "--doi", "10.1/x"],
            env={"ZOT_LIBRARY_ID": "", "ZOT_API_KEY": "", "ZOT_FORMAT": "table"},
        )
        # Human mode: prose on stderr, stdout empty
        assert "credentials" in (result.stderr or "").lower()


class TestSchemaCommand:
    def test_schema_lists_all_commands(self):
        result = _run(["schema"])
        assert result.exit_code == EXIT_OK
        env = json.loads(result.output)
        assert env["ok"] is True
        subs = env["data"]["subcommands"]
        assert "search" in subs
        assert "read" in subs
        assert "schema" in subs

    def test_schema_for_single_command(self):
        result = _run(["schema", "search"])
        assert result.exit_code == EXIT_OK
        env = json.loads(result.output)
        assert env["data"]["name"] == "search"
        param_names = [p["name"] for p in env["data"]["params"]]
        assert "query" in param_names
        assert "collection" in param_names
        assert "item_type" in param_names

    def test_schema_for_nested_command(self):
        result = _run(["schema", "collection", "list"])
        assert result.exit_code == EXIT_OK
        env = json.loads(result.output)
        assert "list" in env["data"]["name"]

    def test_schema_unknown_command_returns_not_found(self):
        result = _run(["schema", "does_not_exist"])
        assert result.exit_code == EXIT_NOT_FOUND
        env = json.loads(result.output)
        assert env["error"]["code"] == "not_found"

    def test_schema_envelope_has_version(self):
        result = _run(["schema", "search"])
        env = json.loads(result.output)
        assert env["meta"]["schema_version"]
        assert env["meta"]["cli_version"]


class TestDryRun:
    def test_delete_dry_run_json_envelope(self):
        result = _run(
            ["delete", "K1", "K2", "--dry-run"],
            env={"ZOT_LIBRARY_ID": "abc", "ZOT_API_KEY": "xyz"},
        )
        assert result.exit_code == EXIT_OK
        env = json.loads(result.output)
        assert env["ok"] is True
        assert env.get("dry_run") is True
        assert env["data"]["would_delete"] == ["K1", "K2"]
        assert env["data"]["count"] == 2


class TestConfirmationRequiredOnNonTTY:
    def test_delete_without_yes_on_noninteractive_returns_validation(self):
        # CliRunner stdin is non-TTY; no --yes, no --dry-run, no --no-interaction
        result = _run(["delete", "K1"], env={"ZOT_LIBRARY_ID": "abc", "ZOT_API_KEY": "xyz"})
        assert result.exit_code == EXIT_VALIDATION
        env = json.loads(result.output)
        assert env["error"]["code"] == "confirmation_required"
