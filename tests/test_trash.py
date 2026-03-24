"""Tests for trash management (list and restore)."""

from __future__ import annotations

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
