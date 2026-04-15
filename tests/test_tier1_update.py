"""Tests for the update command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.writer import ZoteroWriteError, ZoteroWriter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _invoke(args: list[str], json_output: bool = False):
    runner = CliRunner()
    base = ["--json"] if json_output else []
    env = {
        "ZOT_DATA_DIR": str(FIXTURES_DIR),
        "ZOT_LIBRARY_ID": "test_lib",
        "ZOT_API_KEY": "test_key",
        "ZOT_FORMAT": "table",
    }
    return runner.invoke(main, base + args, env=env)


class TestUpdateCommand:
    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_update_title(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        result = _invoke(["update", "ATTN001", "--title", "New Title"])
        assert result.exit_code == 0
        mock_writer.update_item.assert_called_once_with("ATTN001", {"title": "New Title"})
        assert "Updated" in result.output

    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_update_date(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        result = _invoke(["update", "ATTN001", "--date", "2025-01-01"])
        assert result.exit_code == 0
        mock_writer.update_item.assert_called_once_with("ATTN001", {"date": "2025-01-01"})

    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_update_multiple_fields(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        result = _invoke(
            [
                "update",
                "ATTN001",
                "--title",
                "New Title",
                "--date",
                "2025-01-01",
                "--field",
                "abstractNote=New abstract",
            ]
        )
        assert result.exit_code == 0
        mock_writer.update_item.assert_called_once_with(
            "ATTN001",
            {"title": "New Title", "date": "2025-01-01", "abstractNote": "New abstract"},
        )

    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_update_field_option(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        result = _invoke(["update", "ATTN001", "--field", "volume=42"])
        assert result.exit_code == 0
        mock_writer.update_item.assert_called_once_with("ATTN001", {"volume": "42"})

    def test_update_no_fields(self):
        result = _invoke(["update", "ATTN001"])
        assert result.exit_code != 0
        assert "No fields" in result.output

    def test_update_no_credentials(self):
        runner = CliRunner()
        env = {"ZOT_DATA_DIR": str(FIXTURES_DIR), "ZOT_LIBRARY_ID": "", "ZOT_API_KEY": "", "ZOT_FORMAT": "table"}
        result = runner.invoke(main, ["update", "ATTN001", "--title", "X"], env=env)
        assert result.exit_code != 0
        assert "credentials" in result.output.lower() or "config" in result.output.lower()

    def test_update_invalid_field_format(self):
        result = _invoke(["update", "ATTN001", "--field", "no_equals_sign"])
        assert result.exit_code != 0
        assert "Invalid" in result.output or "key=value" in result.output

    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_update_json_output(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        result = _invoke(["update", "ATTN001", "--title", "New"], json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["status"] == "updated"
        assert data["key"] == "ATTN001"

    @patch("zotero_cli_cc.commands.update.ZoteroWriter")
    def test_update_api_error(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_writer.update_item.side_effect = ZoteroWriteError("Item 'X' not found")
        result = _invoke(["update", "X", "--title", "Y"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestWriterUpdateItem:
    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_update_item_calls_api(self, mock_zotero_cls):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        mock_zot.client = None
        mock_zot.item.return_value = {
            "data": {"key": "ABC", "title": "Old", "version": 1},
            "version": 1,
        }
        writer = ZoteroWriter(library_id="test", api_key="key")
        writer.update_item("ABC", {"title": "New Title"})
        mock_zot.update_item.assert_called_once()
        call_arg = mock_zot.update_item.call_args[0][0]
        assert call_arg["data"]["title"] == "New Title"

    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_update_item_not_found(self, mock_zotero_cls):
        from pyzotero.zotero_errors import ResourceNotFoundError

        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        mock_zot.client = None
        mock_zot.item.side_effect = ResourceNotFoundError
        writer = ZoteroWriter(library_id="test", api_key="key")
        with pytest.raises(ZoteroWriteError, match="not found"):
            writer.update_item("MISSING", {"title": "X"})
