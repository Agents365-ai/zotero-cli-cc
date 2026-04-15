"""Tests for trash management (list and restore)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import ZoteroWriteError, ZoteroWriter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _invoke(args: list[str], json_output: bool = False):
    runner = CliRunner()
    base = ["--json"] if json_output else []
    env = {"ZOT_DATA_DIR": str(FIXTURES_DIR), "ZOT_FORMAT": "table"}
    return runner.invoke(main, base + args, env=env)


class TestTrashReader:
    def test_get_trash_items_returns_trashed(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            items = reader.get_trash_items(limit=50)
            assert len(items) >= 1
            keys = [i.key for i in items]
            assert "TRSH007" in keys
        finally:
            reader.close()

    def test_get_trash_items_excludes_non_trashed(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            items = reader.get_trash_items(limit=50)
            keys = [i.key for i in items]
            assert "ATTN001" not in keys
        finally:
            reader.close()

    def test_get_trash_items_respects_limit(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            items = reader.get_trash_items(limit=0)
            assert len(items) == 0
        finally:
            reader.close()

    def test_get_trash_items_has_full_item_data(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            items = reader.get_trash_items(limit=50)
            trashed = [i for i in items if i.key == "TRSH007"][0]
            assert trashed.title == "Old Survey of Neural Networks"
            assert trashed.item_type == "journalArticle"
        finally:
            reader.close()


class TestTrashWriter:
    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_restore_from_trash(self, mock_zotero_cls):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        mock_zot.item.return_value = {"key": "K1", "data": {"deleted": 1}}
        writer = ZoteroWriter(library_id="123", api_key="abc")
        writer.restore_from_trash("K1")
        mock_zot.update_item.assert_called_once()
        call_args = mock_zot.update_item.call_args[0][0]
        assert call_args["data"]["deleted"] == 0

    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_restore_not_found(self, mock_zotero_cls):
        from pyzotero.zotero_errors import ResourceNotFoundError

        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        mock_zot.item.side_effect = ResourceNotFoundError("Not found")
        writer = ZoteroWriter(library_id="123", api_key="abc")
        with pytest.raises(ZoteroWriteError, match="not found"):
            writer.restore_from_trash("MISSING")


class TestTrashCLI:
    def test_trash_list(self):
        result = _invoke(["trash", "list"], json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        keys = [i["key"] for i in data]
        assert "TRSH007" in keys

    def test_trash_list_table(self):
        result = _invoke(["trash", "list"])
        assert result.exit_code == 0
        assert "TRSH007" in result.output


class TestTrashMCP:
    def test_handle_trash_list(self):
        from zotero_cli_cc.mcp_server import _handle_trash_list

        with patch("zotero_cli_cc.mcp_server._get_reader") as mock_get:
            mock_reader = MagicMock()
            mock_get.return_value = mock_reader
            mock_item = MagicMock()
            mock_item.key = "K1"
            mock_item.item_type = "journalArticle"
            mock_item.title = "Test"
            mock_item.creators = []
            mock_item.date = "2024"
            mock_item.abstract = None
            mock_item.url = None
            mock_item.doi = None
            mock_item.tags = []
            mock_item.collections = []
            mock_item.date_added = "2024-01-01"
            mock_item.date_modified = "2024-01-01"
            mock_item.extra = {}
            mock_reader.get_trash_items.return_value = [mock_item]
            result = _handle_trash_list(limit=50)
            assert len(result["items"]) == 1

    def test_handle_trash_restore(self):
        from zotero_cli_cc.mcp_server import _handle_trash_restore

        with patch("zotero_cli_cc.mcp_server._get_writer") as mock_get:
            mock_writer = MagicMock()
            mock_get.return_value = mock_writer
            result = _handle_trash_restore("K1")
            mock_writer.restore_from_trash.assert_called_once_with("K1")
            assert result["restored"] is True
