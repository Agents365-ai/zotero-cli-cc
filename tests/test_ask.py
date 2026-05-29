"""Tests for `zot ask` — evidence-pack builder and the CLI command."""

from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.rag import build_evidence_pack

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _chunk(cid: int, key: str) -> dict:
    return {"id": cid, "item_key": key, "source": "metadata", "content": f"text {cid}"}


# ---------------------------------------------------------------------------
# build_evidence_pack
# ---------------------------------------------------------------------------


class TestBuildEvidencePack:
    def test_bm25_only(self):
        bm25 = [(1, 7.0, _chunk(1, "A")), (2, 3.0, _chunk(2, "B"))]
        pack = build_evidence_pack(bm25, [], "bm25", 5)
        assert [e["cite_key"] for e in pack] == ["A", "B"]
        assert pack[0]["scores"] == {"bm25": 7.0}
        assert pack[0]["text"] == "text 1"
        assert "rrf" not in pack[0]["scores"]

    def test_hybrid_fuses_and_keeps_both_scores(self):
        bm25 = [(1, 7.0, _chunk(1, "A"))]
        sem = [(1, 0.9, _chunk(1, "A"))]
        pack = build_evidence_pack(bm25, sem, "hybrid", 5)
        assert pack[0]["scores"]["bm25"] == 7.0
        assert pack[0]["scores"]["semantic"] == 0.9
        assert "rrf" in pack[0]["scores"]

    def test_semantic_only(self):
        sem = [(1, 0.5, _chunk(1, "A"))]
        pack = build_evidence_pack([], sem, "semantic", 5)
        assert pack[0]["scores"] == {"semantic": 0.5}

    def test_respects_k(self):
        bm25 = [(i, float(10 - i), _chunk(i, f"K{i}")) for i in range(5)]
        pack = build_evidence_pack(bm25, [], "bm25", 2)
        assert len(pack) == 2

    def test_empty(self):
        assert build_evidence_pack([], [], "hybrid", 5) == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _invoke(args: list[str], json_output: bool = False):
    runner = CliRunner()
    base = ["--json"] if json_output else []
    env = {"ZOT_DATA_DIR": str(FIXTURES_DIR), "ZOT_FORMAT": "table"}
    return runner.invoke(main, base + args, env=env)


def _envelope(output: str) -> dict:
    """`ask` emits NDJSON progress events before the final pretty-printed
    envelope; parse the trailing JSON document."""
    start = output.rfind("\n{\n")
    text = output[start + 1 :] if start >= 0 else output
    return json.loads(text)


def _patch_ws_dir(tmp_path):
    stack = ExitStack()
    stack.enter_context(patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path))
    stack.enter_context(patch("zotero_cli_cc.commands.workspace.workspaces_dir", return_value=tmp_path))
    stack.enter_context(patch("zotero_cli_cc.commands.ask.workspaces_dir", return_value=tmp_path))
    return stack


class TestAskCLI:
    def test_ask_table(self, tmp_path):
        with _patch_ws_dir(tmp_path):
            _invoke(["workspace", "new", "test-ask"])
            _invoke(["workspace", "add", "test-ask", "ATTN001"])
            _invoke(["workspace", "index", "test-ask"])
            result = _invoke(["ask", "attention", "--workspace", "test-ask"])
        assert result.exit_code == 0
        assert "ATTN001" in result.output
        assert "cite_key" in result.output or "ABCD1234" in result.output

    def test_ask_json_envelope(self, tmp_path):
        with _patch_ws_dir(tmp_path):
            _invoke(["workspace", "new", "test-ask"])
            _invoke(["workspace", "add", "test-ask", "ATTN001"])
            _invoke(["workspace", "index", "test-ask"])
            result = _invoke(["ask", "attention", "--workspace", "test-ask"], json_output=True)
        env = _envelope(result.output)
        assert env["ok"] is True
        data = env["data"]
        assert data["question"] == "attention"
        assert "answer_instructions" in data
        assert isinstance(data["evidence"], list) and len(data["evidence"]) > 0
        assert "cite_key" in data["evidence"][0]
        assert env["meta"]["retrieved"] == len(data["evidence"])

    def test_ask_evidence_k_caps(self, tmp_path):
        with _patch_ws_dir(tmp_path):
            _invoke(["workspace", "new", "test-ask"])
            _invoke(["workspace", "add", "test-ask", "ATTN001"])
            _invoke(["workspace", "index", "test-ask"])
            result = _invoke(["ask", "attention", "--workspace", "test-ask", "--evidence-k", "1"], json_output=True)
        data = _envelope(result.output)["data"]
        assert len(data["evidence"]) <= 1

    def test_ask_no_index(self, tmp_path):
        with _patch_ws_dir(tmp_path):
            _invoke(["workspace", "new", "test-ask"])
            result = _invoke(["ask", "x", "--workspace", "test-ask"])
        assert result.exit_code == 4
        assert "index" in result.output.lower()

    def test_ask_nonexistent_workspace(self, tmp_path):
        with _patch_ws_dir(tmp_path):
            result = _invoke(["ask", "x", "--workspace", "nope"])
        assert result.exit_code == 4
        assert "not found" in result.output.lower()
