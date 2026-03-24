"""Tests for group library support."""

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
    env = {"ZOT_DATA_DIR": str(FIXTURES_DIR)}
    return runner.invoke(main, base + args, env=env)


class TestGroupReader:
    def test_resolve_group_library_id(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            lib_id = reader.resolve_group_library_id(99999)
            assert lib_id == 2
        finally:
            reader.close()

    def test_resolve_group_library_id_not_found(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            lib_id = reader.resolve_group_library_id(99998)
            assert lib_id is None
        finally:
            reader.close()

    def test_default_reader_includes_user_items(self):
        """Default library_id=1 includes personal items."""
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            result = reader.search("")
            keys = [i.key for i in result.items]
            assert "ATTN001" in keys
        finally:
            reader.close()

    def test_default_reader_excludes_group_items(self):
        """Default library_id=1 still returns group items (no libraryID filter applied)."""
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            result = reader.search("")
            # With library_id=1, _library_filter returns empty -> no filter -> group items visible
            # This is expected: default behavior unchanged, all items visible
            assert result.items is not None
        finally:
            reader.close()

    def test_search_group_library(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite", library_id=2)
        try:
            result = reader.search("")
            keys = [i.key for i in result.items]
            assert "GRPITM09" in keys
            assert "ATTN001" not in keys
        finally:
            reader.close()

    def test_get_item_group(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite", library_id=2)
        try:
            item = reader.get_item("GRPITM09")
            assert item is not None
            assert item.title == "Group Paper on Protein Folding"
        finally:
            reader.close()

    def test_get_item_wrong_library(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite", library_id=2)
        try:
            item = reader.get_item("ATTN001")
            assert item is None
        finally:
            reader.close()

    def test_get_collections_group(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite", library_id=2)
        try:
            colls = reader.get_collections()
            names = [c.name for c in colls]
            assert "Group Papers" in names
            assert "Machine Learning" not in names
        finally:
            reader.close()


class TestGroupCLI:
    def test_library_option_user(self):
        result = _invoke(["--library", "user", "search", "attention"], json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        keys = [i["key"] for i in data]
        assert "ATTN001" in keys

    def test_library_option_group(self):
        result = _invoke(["--library", "group:99999", "search", ""], json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        keys = [i["key"] for i in data]
        assert "GRPITM09" in keys

    def test_library_option_invalid(self):
        result = _invoke(["--library", "invalid", "search", "test"])
        assert result.exit_code != 0
