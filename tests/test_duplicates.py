"""Tests for duplicate detection."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.reader import ZoteroReader

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _invoke(args: list[str], json_output: bool = False):
    runner = CliRunner()
    base = ["--json"] if json_output else []
    env = {"ZOT_DATA_DIR": str(FIXTURES_DIR)}
    return runner.invoke(main, base + args, env=env)


class TestDuplicateReader:
    def test_find_duplicates_doi(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            groups = reader.find_duplicates(strategy="doi")
            assert len(groups) >= 1
            doi_group = [g for g in groups if g.match_type == "doi"][0]
            keys = {i.key for i in doi_group.items}
            assert "ATTN001" in keys
            assert "DUPE008" in keys
            assert doi_group.score == 1.0
        finally:
            reader.close()

    def test_find_duplicates_title(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            groups = reader.find_duplicates(strategy="title", threshold=0.7)
            # ATTN001 and DUPE008 have very similar titles
            found = False
            for g in groups:
                keys = {i.key for i in g.items}
                if "ATTN001" in keys and "DUPE008" in keys:
                    found = True
                    assert g.match_type == "title"
                    assert g.score >= 0.7
            assert found
        finally:
            reader.close()

    def test_find_duplicates_both(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            groups = reader.find_duplicates(strategy="both")
            assert len(groups) >= 1
        finally:
            reader.close()

    def test_find_duplicates_no_matches(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            groups = reader.find_duplicates(strategy="doi", limit=0)
            assert len(groups) == 0
        finally:
            reader.close()

    def test_find_duplicates_respects_limit(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            groups = reader.find_duplicates(strategy="both", limit=1)
            assert len(groups) <= 1
        finally:
            reader.close()


class TestDuplicatesCLI:
    def test_duplicates_json(self):
        result = _invoke(["duplicates", "--by", "doi"], json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1
        assert data[0]["match_type"] == "doi"

    def test_duplicates_table(self):
        result = _invoke(["duplicates"])
        assert result.exit_code == 0
        assert "ATTN001" in result.output or "DUPE008" in result.output

    def test_duplicates_by_title(self):
        result = _invoke(["duplicates", "--by", "title"], json_output=True)
        assert result.exit_code == 0


class TestDuplicatesMCP:
    def test_handle_duplicates(self):
        from zotero_cli_cc.mcp_server import _handle_duplicates
        with patch("zotero_cli_cc.mcp_server._get_reader") as mock_get:
            mock_reader = MagicMock()
            mock_get.return_value = mock_reader
            mock_reader.find_duplicates.return_value = []
            result = _handle_duplicates(strategy="doi")
            assert result["groups"] == []
