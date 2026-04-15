"""Tests for the recent command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.reader import ZoteroReader

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _invoke(args: list[str], json_output: bool = False):
    runner = CliRunner()
    base = ["--json"] if json_output else []
    env = {"ZOT_DATA_DIR": str(FIXTURES_DIR), "ZOT_FORMAT": "table"}
    return runner.invoke(main, base + args, env=env)


class TestRecent:
    def test_recent_default(self):
        """Recent with no args returns items sorted by dateAdded desc."""
        result = _invoke(["recent"], json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        # Default 7 days - test items from 2024 won't match
        assert isinstance(data, list)

    def test_recent_days_zero(self):
        """--days 0 returns nothing (test items are from 2024)."""
        result = _invoke(["recent", "--days", "0"], json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert len(data) == 0

    def test_recent_large_window(self):
        """--days 9999 returns all items."""
        result = _invoke(["recent", "--days", "9999"], json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert len(data) >= 3

    def test_recent_large_window_sorted(self):
        """Items returned sorted by dateAdded desc."""
        result = _invoke(["recent", "--days", "9999"], json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        dates = [i["date_added"] for i in data]
        assert dates == sorted(dates, reverse=True)

    def test_recent_modified(self):
        """--modified sorts by dateModified."""
        result = _invoke(["recent", "--modified", "--days", "9999"], json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        dates = [i["date_modified"] for i in data]
        assert dates == sorted(dates, reverse=True)

    def test_recent_table_output(self):
        result = _invoke(["recent", "--days", "9999"])
        assert result.exit_code == 0
        assert "ATTN001" in result.output or "BERT002" in result.output or "DEEP003" in result.output

    def test_recent_no_results_message(self):
        result = _invoke(["recent", "--days", "0"])
        assert result.exit_code == 0
        assert "No items" in result.output

    def test_reader_get_recent_items(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            items = reader.get_recent_items(since="2000-01-01", limit=50)
            assert len(items) >= 3
            dates = [i.date_added for i in items]
            assert dates == sorted(dates, reverse=True)
        finally:
            reader.close()
