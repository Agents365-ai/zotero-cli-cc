"""Tests for stats and open commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from zotero_cli_cc.cli import main


class TestStatsCmd:
    def test_stats_human(self, test_db_path: Path):
        runner = CliRunner()
        result = runner.invoke(main, ["stats"], env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"})
        assert result.exit_code == 0
        assert "Total items:" in result.output
        assert "Items by type:" in result.output
        assert "Collections" in result.output
        assert "Top tags" in result.output

    def test_stats_json(self, test_db_path: Path):
        runner = CliRunner()
        result = runner.invoke(
            main, ["--json", "stats"], env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"}
        )
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert "total_items" in data
        assert "by_type" in data
        assert "top_tags" in data
        assert "collections" in data
        assert "pdf_attachments" in data
        assert "notes" in data
        assert data["total_items"] > 0


class TestOpenCmd:
    def test_open_nonexistent_item(self, test_db_path: Path):
        runner = CliRunner()
        result = runner.invoke(
            main, ["open", "NONEXIST"], env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"}
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_open_no_pdf(self, test_db_path: Path):
        runner = CliRunner()
        result = runner.invoke(
            main, ["open", "DEEP003"], env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"}
        )
        assert result.exit_code != 0
        assert "No PDF" in result.output

    @patch("zotero_cli_cc.commands.open_cmd._open_path")
    def test_open_url(self, mock_open, test_db_path: Path):
        runner = CliRunner()
        result = runner.invoke(
            main, ["open", "--url", "ATTN001"], env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"}
        )
        assert result.exit_code == 0
        assert "Opening" in result.output
        mock_open.assert_called_once()

    def test_open_url_no_url(self, test_db_path: Path):
        runner = CliRunner()
        # DEEP003 is a book, might not have URL - test the error path
        result = runner.invoke(
            main, ["open", "--url", "DEEP003"], env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"}
        )
        assert result.exit_code != 0


class TestGetStats:
    def test_get_stats(self, test_db_path: Path):
        from zotero_cli_cc.core.reader import ZoteroReader

        reader = ZoteroReader(test_db_path)
        try:
            stats = reader.get_stats()
            assert stats["total_items"] > 0
            assert isinstance(stats["by_type"], dict)
            assert isinstance(stats["top_tags"], dict)
            assert isinstance(stats["collections"], dict)
            assert stats["pdf_attachments"] >= 0
            assert stats["notes"] >= 0
        finally:
            reader.close()
