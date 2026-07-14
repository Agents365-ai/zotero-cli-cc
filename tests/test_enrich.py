"""Tests for `zot enrich` — Extra-merge logic and the CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.enrich import (
    BLOCK_END,
    BLOCK_START,
    EnrichError,
    journal_of,
    load_journal_map,
    merge_extra,
    metrics_for,
    parse_set_pairs,
)
from zotero_cli_cc.models import Item


def _item(*, item_type="journalArticle", **extra) -> Item:
    return Item(
        key="ITEM0001",
        item_type=item_type,
        title="A Title",
        creators=[],
        abstract=None,
        date="2016",
        url=None,
        doi=None,
        tags=[],
        collections=[],
        date_added="2020-01-01",
        date_modified="2020-01-01",
        extra=extra,
    )


# ---------------------------------------------------------------------------
# pure logic
# ---------------------------------------------------------------------------


class TestParseSet:
    def test_basic(self):
        assert parse_set_pairs(("SCI IF=5.8", "JCR=Q1")) == {"SCI IF": "5.8", "JCR": "Q1"}

    def test_value_with_equals(self):
        assert parse_set_pairs(("note=a=b",)) == {"note": "a=b"}

    def test_missing_equals_raises(self):
        with pytest.raises(EnrichError):
            parse_set_pairs(("bad",))

    def test_empty_key_raises(self):
        with pytest.raises(EnrichError):
            parse_set_pairs(("=v",))


class TestJournalMap:
    def test_load_and_lookup(self, tmp_path: Path):
        p = tmp_path / "j.toml"
        p.write_text('["Bioinformatics"]\n"SCI IF" = 5.8\n"JCR" = "Q1"\n', encoding="utf-8")
        m = load_journal_map(p)
        assert m["bioinformatics"] == {"SCI IF": "5.8", "JCR": "Q1"}

    def test_bad_file_raises(self, tmp_path: Path):
        p = tmp_path / "bad.toml"
        p.write_text("not = = valid", encoding="utf-8")
        with pytest.raises(EnrichError):
            load_journal_map(p)


class TestJournalOf:
    def test_journal_article(self):
        assert journal_of(_item(publicationTitle="Nature")) == "Nature"

    def test_conference(self):
        assert journal_of(_item(item_type="conferencePaper", conferenceName="CVPR")) == "CVPR"


class TestMetricsFor:
    def test_map_lookup_case_insensitive(self):
        item = _item(publicationTitle="Nature")
        m = metrics_for(item, {"nature": {"JCR": "Q1"}}, {})
        assert m == {"JCR": "Q1"}

    def test_set_overrides_map(self):
        item = _item(publicationTitle="Nature")
        m = metrics_for(item, {"nature": {"JCR": "Q1"}}, {"JCR": "Q2"})
        assert m == {"JCR": "Q2"}

    def test_no_match_returns_set_only(self):
        item = _item(publicationTitle="Unknown")
        assert metrics_for(item, {"nature": {"JCR": "Q1"}}, {"IF": "1"}) == {"IF": "1"}

    def test_empty(self):
        assert metrics_for(_item(publicationTitle="Nature"), {}, {}) == {}


class TestMergeExtra:
    def test_empty_existing(self):
        out = merge_extra("", {"IF": "5"})
        assert out == f"{BLOCK_START}\nIF: 5\n{BLOCK_END}"

    def test_appends_preserving_existing(self):
        out = merge_extra("DOI: 10.x", {"IF": "5"})
        assert out.startswith("DOI: 10.x\n")
        assert "IF: 5" in out

    def test_replaces_block_idempotent(self):
        first = merge_extra("DOI: 10.x", {"IF": "5"})
        second = merge_extra(first, {"IF": "5"})
        assert first == second  # re-running is a no-op

    def test_replaces_block_updates_values(self):
        first = merge_extra("DOI: 10.x", {"IF": "5"})
        updated = merge_extra(first, {"IF": "6"})
        assert "DOI: 10.x" in updated
        assert "IF: 6" in updated
        assert "IF: 5" not in updated
        assert updated.count(BLOCK_START) == 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _invoke(args, test_db_path: Path, json_out=False, env_extra=None):
    runner = CliRunner()
    base = ["--json"] if json_out else []
    env = {"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"}
    if env_extra:
        env.update(env_extra)
    return runner.invoke(main, base + args, env=env)


class TestEnrichCLI:
    def test_dry_run_set(self, test_db_path):
        result = _invoke(["enrich", "ATTN001", "--set", "SCI IF=5.8", "--dry-run"], test_db_path, json_out=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["updated_count"] == 0
        r = data["results"][0]
        assert r["status"] == "dry-run"
        assert BLOCK_START in r["extra_preview"]
        assert "SCI IF: 5.8" in r["extra_preview"]

    def test_nothing_to_write_errors(self, test_db_path):
        result = _invoke(["enrich", "ATTN001"], test_db_path)
        assert result.exit_code == 3

    def test_bad_set_errors(self, test_db_path):
        result = _invoke(["enrich", "ATTN001", "--set", "bad"], test_db_path)
        assert result.exit_code == 3

    def test_item_not_found_recorded(self, test_db_path):
        result = _invoke(["enrich", "NOPE9999", "--set", "IF=5", "--dry-run"], test_db_path, json_out=True)
        assert result.exit_code == 0
        assert json.loads(result.output)["data"]["results"][0]["code"] == "not_found"

    def test_write_with_mocked_writer(self, test_db_path, monkeypatch):
        calls = {}

        class FakeWriter:
            def update_extra_metrics(self, key, metrics):
                calls[key] = metrics
                return "merged"

        monkeypatch.setattr("zotero_cli_cc.commands.enrich.build_writer", lambda *a, **k: FakeWriter())
        result = _invoke(["enrich", "ATTN001", "--set", "JCR=Q1"], test_db_path, json_out=True)
        assert result.exit_code == 0
        assert calls == {"ATTN001": {"JCR": "Q1"}}
        assert json.loads(result.output)["data"]["updated_count"] == 1

    def test_auth_missing_aborts(self, test_db_path):
        # Non-dry-run without credentials configured -> auth_missing (exit 2).
        result = _invoke(
            ["enrich", "ATTN001", "--set", "JCR=Q1"],
            test_db_path,
            env_extra={"ZOT_API_KEY": "", "ZOT_LIBRARY_ID": ""},
        )
        assert result.exit_code == 2
