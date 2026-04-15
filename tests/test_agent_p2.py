"""P2 tests: NDJSON streaming, structured stderr progress, schema metadata."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.exit_codes import EXIT_OK

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _run(args, env=None):
    runner = CliRunner()
    base_env = {"ZOT_DATA_DIR": str(FIXTURES_DIR), "ZOT_FORMAT": ""}
    if env:
        base_env.update(env)
    return runner.invoke(main, args, env=base_env)


def _parse_ndjson(s: str) -> list[dict]:
    return [json.loads(line) for line in s.strip().split("\n") if line.strip()]


class TestNDJSONStream:
    def test_search_stream_emits_ndjson(self):
        result = _run(["search", "attention", "--stream"])
        assert result.exit_code == EXIT_OK
        lines = _parse_ndjson(result.output)
        assert len(lines) >= 1
        # final line is the summary
        last = lines[-1]
        assert "summary" in last
        assert last["summary"]["has_more"] is False
        assert last["summary"]["count"] == len(lines) - 1

    def test_list_stream_emits_ndjson(self):
        result = _run(["list", "--stream"])
        assert result.exit_code == EXIT_OK
        lines = _parse_ndjson(result.output)
        last = lines[-1]
        assert "summary" in last
        for line in lines[:-1]:
            assert line["ok"] is True
            assert "data" in line

    def test_stream_summary_has_meta(self):
        result = _run(["list", "--stream", "--limit", "2"])
        lines = _parse_ndjson(result.output)
        last = lines[-1]
        assert "meta" in last
        assert "request_id" in last["meta"]


class TestSchemaMetadata:
    def test_schema_has_safety_tier(self):
        env = json.loads(_run(["schema", "delete"]).output)
        assert env["data"]["safety_tier"] == "destructive"

    def test_schema_read_cmd_tier(self):
        env = json.loads(_run(["schema", "search"]).output)
        assert env["data"]["safety_tier"] == "read"

    def test_schema_write_cmd_tier(self):
        env = json.loads(_run(["schema", "add"]).output)
        assert env["data"]["safety_tier"] == "write"

    def test_schema_since_and_deprecated_fields(self):
        env = json.loads(_run(["schema", "search"]).output)
        assert "since" in env["data"]
        assert "deprecated" in env["data"]
        assert env["data"]["deprecated"] is False


class TestEmitProgress:
    def test_emit_progress_writes_ndjson_to_stderr(self):
        from io import StringIO
        import sys

        from zotero_cli_cc.formatter import emit_progress, request_scope

        captured = StringIO()
        old = sys.stderr
        sys.stderr = captured
        try:
            with request_scope():
                emit_progress("start", phase="x", total=10)
                emit_progress("progress", phase="x", done=5, total=10)
                emit_progress("complete", phase="x", done=10, total=10)
        finally:
            sys.stderr = old
        lines = [json.loads(line) for line in captured.getvalue().strip().split("\n")]
        assert len(lines) == 3
        assert lines[0]["event"] == "start"
        assert lines[1]["done"] == 5
        assert lines[2]["event"] == "complete"
        # All carry the same request_id
        rids = {line["request_id"] for line in lines}
        assert len(rids) == 1
        # elapsed_ms is monotonically non-decreasing
        elapsed = [line["elapsed_ms"] for line in lines]
        assert elapsed == sorted(elapsed)
