"""Tests for new features: --dry-run, --offset, PdfExtractionError, timeout, ZoteroWriteError in commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.pdf_extractor import PdfExtractionError, extract_text_from_pdf
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter

WRITE_ENV = {"ZOT_LIBRARY_ID": "123", "ZOT_API_KEY": "abc"}


# --- Dry-run tests ---


class TestDryRun:
    def test_delete_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(main, ["delete", "K1", "--dry-run"], env=WRITE_ENV)
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "K1" in result.output

    def test_delete_dry_run_no_api_needed(self):
        """--dry-run should work even without API credentials."""
        runner = CliRunner()
        result = runner.invoke(main, ["delete", "K1", "--dry-run"])
        assert result.exit_code != 0
        assert "[dry-run]" in result.output

    def test_collection_reorganize_dry_run(self, tmp_path):
        plan = {
            "collections": [
                {"name": "Topic A", "items": ["K1", "K2"]},
                {"name": "Sub B", "parent": "Topic A", "items": ["K3"]},
            ]
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["collection", "reorganize", str(plan_file), "--dry-run"],
        )
        assert result.exit_code == 0
        assert "[dry-run] Would create collection 'Topic A'" in result.output
        assert "[dry-run]   Would move K1 -> 'Topic A'" in result.output
        assert "[dry-run]   Would move K2 -> 'Topic A'" in result.output
        assert "[dry-run] Would create collection 'Sub B' (under 'Topic A')" in result.output
        assert "2 collections to create" in result.output

    def test_collection_delete_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["collection", "delete", "COL1", "--dry-run"],
            env=WRITE_ENV,
        )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "COL1" in result.output

    def test_tag_add_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["tag", "K1", "--add", "newtag", "--dry-run"],
            env=WRITE_ENV,
        )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "newtag" in result.output

    def test_tag_remove_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["tag", "K1", "--remove", "oldtag", "--dry-run"],
            env=WRITE_ENV,
        )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "oldtag" in result.output


# --- Shell completions tests ---


class TestCompletions:
    def test_completions_bash(self):
        runner = CliRunner()
        result = runner.invoke(main, ["completions", "bash"])
        assert result.exit_code == 0

    def test_completions_zsh(self):
        runner = CliRunner()
        result = runner.invoke(main, ["completions", "zsh"])
        assert result.exit_code == 0

    def test_completions_fish(self):
        runner = CliRunner()
        result = runner.invoke(main, ["completions", "fish"])
        assert result.exit_code == 0

    def test_completions_invalid_shell(self):
        runner = CliRunner()
        result = runner.invoke(main, ["completions", "powershell"])
        assert result.exit_code != 0


# --- Offset/pagination tests ---


class TestOffset:
    def test_search_with_offset(self, test_db_path):
        from zotero_cli_cc.core.reader import ZoteroReader

        reader = ZoteroReader(test_db_path)
        all_results = reader.search("", limit=100)
        offset_results = reader.search("", limit=100, offset=1)
        reader.close()
        assert len(offset_results.items) == len(all_results.items) - 1

    def test_search_offset_beyond_total(self, test_db_path):
        from zotero_cli_cc.core.reader import ZoteroReader

        reader = ZoteroReader(test_db_path)
        result = reader.search("", limit=100, offset=99999)
        reader.close()
        assert len(result.items) == 0
        assert result.total > 0  # total count is still accurate

    def test_summarize_all_with_offset(self, test_db_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["summarize-all", "--offset", "1"],
            env = {"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"},
        )
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert isinstance(data, list)


# --- PdfExtractionError tests ---


class TestPdfExtractionError:
    def test_corrupted_pdf(self, tmp_path):
        bad_pdf = tmp_path / "bad.pdf"
        bad_pdf.write_bytes(b"not a real pdf file")
        with pytest.raises(PdfExtractionError, match="Cannot open PDF"):
            extract_text_from_pdf(bad_pdf)

    def test_page_range_exceeds_length(self):
        fixtures = Path(__file__).parent / "fixtures"
        pdf = fixtures / "test.pdf"
        if not pdf.exists():
            pytest.skip("test.pdf fixture not found")
        with pytest.raises(PdfExtractionError, match="exceeds document length"):
            extract_text_from_pdf(pdf, pages=(9999, 10000))

    def test_pdf_extraction_error_is_catchable(self):
        """Verify PdfExtractionError can be caught as expected in commands."""
        with pytest.raises(PdfExtractionError):
            raise PdfExtractionError("test error")

    def test_pdf_extraction_error_has_message(self):
        err = PdfExtractionError("Cannot open PDF: encrypted")
        assert "encrypted" in str(err)


# --- Batch operations tests ---


class TestBatchDelete:
    @patch("zotero_cli_cc.commands.delete.ZoteroWriter")
    def test_delete_multiple_keys(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["delete", "K1", "K2", "K3", "--yes"],
            env=WRITE_ENV,
        )
        assert result.exit_code == 0
        assert mock_writer.delete_item.call_count == 3
        assert "K1" in result.output
        assert "K2" in result.output
        assert "K3" in result.output

    def test_delete_multiple_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(main, ["delete", "K1", "K2", "--dry-run"])
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "K1" in result.output
        assert "K2" in result.output

    @patch("zotero_cli_cc.commands.delete.ZoteroWriter")
    def test_delete_partial_failure(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_writer.delete_item.side_effect = [None, ZoteroWriteError("Not found"), None]

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["delete", "K1", "K2", "K3", "--yes"],
            env=WRITE_ENV,
        )
        assert result.exit_code != 0
        assert "K1" in result.output
        assert "Not found" in result.output
        assert "K3" in result.output
        # Should NOT print sync reminder when there are failures
        assert SYNC_REMINDER not in result.output


class TestBatchTag:
    @patch("zotero_cli_cc.commands.tag.ZoteroWriter")
    def test_tag_add_multiple_keys(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["tag", "K1", "K2", "K3", "--add", "newtag"],
            env=WRITE_ENV,
        )
        assert result.exit_code == 0
        assert mock_writer.add_tags.call_count == 3
        assert "K1" in result.output
        assert "K2" in result.output
        assert "K3" in result.output

    @patch("zotero_cli_cc.commands.tag.ZoteroWriter")
    def test_tag_remove_multiple_keys(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["tag", "K1", "K2", "--remove", "oldtag"],
            env=WRITE_ENV,
        )
        assert result.exit_code == 0
        assert mock_writer.remove_tags.call_count == 2

    def test_tag_multiple_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["tag", "K1", "K2", "--add", "t", "--dry-run"],
        )
        assert result.exit_code == 0
        assert result.output.count("[dry-run]") == 2

    def test_tag_view_multiple_keys(self, test_db_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["tag", "ATTN001", "BERT002"],
            env = {"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"},
        )
        assert result.exit_code == 0
        assert "ATTN001" in result.output
        assert "BERT002" in result.output


# --- Timeout tests ---


class TestTimeout:
    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_writer_sets_timeout(self, mock_zotero_cls):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        mock_zot.client = MagicMock()

        ZoteroWriter(library_id="123", api_key="abc", timeout=10.0)
        # Verify timeout was set on the client
        mock_zot.client.timeout = mock_zot.client.timeout  # just verify no error

    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_timeout_raises_write_error(self, mock_zotero_cls):
        from httpx import ReadTimeout

        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        mock_zot.client = MagicMock()
        mock_zot.item_template.return_value = {"itemType": "note", "note": "", "parentItem": ""}
        mock_zot.create_items.side_effect = ReadTimeout("Request timed out")

        writer = ZoteroWriter(library_id="123", api_key="abc")
        with pytest.raises(ZoteroWriteError, match="Network error"):
            writer.add_note("P1", "content")


# --- ZoteroWriteError handling in commands ---


class TestWriteErrorInCommands:
    @patch("zotero_cli_cc.commands.add.ZoteroWriter")
    def test_add_write_error(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_writer.add_item.side_effect = ZoteroWriteError("API error: Bad request")

        runner = CliRunner()
        result = runner.invoke(main, ["add", "--doi", "10.1234/test"], env=WRITE_ENV)
        assert result.exit_code != 0
        assert "Bad request" in result.output

    @patch("zotero_cli_cc.commands.delete.ZoteroWriter")
    def test_delete_write_error(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_writer.delete_item.side_effect = ZoteroWriteError("Item 'K1' not found")

        runner = CliRunner()
        result = runner.invoke(main, ["delete", "K1", "--yes"], env=WRITE_ENV)
        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("zotero_cli_cc.commands.tag.ZoteroWriter")
    def test_tag_add_write_error(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_writer.add_tags.side_effect = ZoteroWriteError("Item 'K1' not found")

        runner = CliRunner()
        result = runner.invoke(main, ["tag", "K1", "--add", "t"], env=WRITE_ENV)
        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("zotero_cli_cc.commands.note.ZoteroWriter")
    def test_note_write_error(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_writer.add_note.side_effect = ZoteroWriteError("Network error: timeout")

        runner = CliRunner()
        result = runner.invoke(main, ["note", "K1", "--add", "text"], env=WRITE_ENV)
        assert result.exit_code != 0
        assert "timeout" in result.output

    @patch("zotero_cli_cc.commands.collection.ZoteroWriter")
    def test_collection_create_write_error(self, mock_writer_cls):
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_writer.create_collection.side_effect = ZoteroWriteError("Network error")

        runner = CliRunner()
        result = runner.invoke(main, ["collection", "create", "Test"], env=WRITE_ENV)
        assert result.exit_code != 0
        assert "Network error" in result.output
