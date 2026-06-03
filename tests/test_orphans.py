"""Tests for `zot orphans` — missing-file attachment detection and cleanup."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.reader import ZoteroReader


def _make_db(dir_path: Path, attachments: list[dict], *, with_sync_cols: bool = True) -> Path:
    """Build a minimal Zotero-like DB + storage tree.

    Each attachment dict: {key, path, present(bool), syncState?, storageHash?}.
    `present` controls whether the file actually exists under storage/<key>/.
    """
    db = dir_path / "zotero.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
    if with_sync_cols:
        con.execute(
            "CREATE TABLE itemAttachments (itemID INT, parentItemID INT, linkMode INT, "
            "contentType TEXT, path TEXT, syncState INT, storageHash TEXT)"
        )
    else:
        con.execute(
            "CREATE TABLE itemAttachments (itemID INT, parentItemID INT, linkMode INT, contentType TEXT, path TEXT)"
        )
    storage = dir_path / "storage"
    for i, a in enumerate(attachments, start=1):
        con.execute("INSERT INTO items (itemID, key) VALUES (?, ?)", (i, a["key"]))
        filename = a["path"].replace("storage:", "")
        if with_sync_cols:
            con.execute(
                "INSERT INTO itemAttachments VALUES (?, NULL, 0, ?, ?, ?, ?)",
                (i, a.get("content_type", "application/pdf"), a["path"], a.get("syncState", 0), a.get("storageHash")),
            )
        else:
            con.execute(
                "INSERT INTO itemAttachments VALUES (?, NULL, 0, ?, ?)",
                (i, a.get("content_type", "application/pdf"), a["path"]),
            )
        if a["present"]:
            (storage / a["key"]).mkdir(parents=True, exist_ok=True)
            (storage / a["key"] / filename).write_bytes(b"%PDF-1.4 x")
    con.commit()
    con.close()
    return db


class TestFindOrphanAttachments:
    def test_classification(self, tmp_path):
        db = _make_db(
            tmp_path,
            [
                {"key": "PRESENT01", "path": "storage:ok.pdf", "present": True},
                {"key": "DEAD0001", "path": "storage:gone.pdf", "present": False, "syncState": 0, "storageHash": None},
                {"key": "RECOV0001", "path": "storage:later.pdf", "present": False, "syncState": 1},
                {
                    "key": "RECOV0002",
                    "path": "storage:hash.pdf",
                    "present": False,
                    "syncState": 0,
                    "storageHash": "abc",
                },
            ],
        )
        orphans = ZoteroReader(db, library_id=1).find_orphan_attachments()
        by_key = {o.attachment_key: o.classification for o in orphans}
        assert "PRESENT01" not in by_key  # file exists locally -> not an orphan
        assert by_key == {"DEAD0001": "dead", "RECOV0001": "recoverable", "RECOV0002": "recoverable"}

    def test_filename_strips_storage_prefix(self, tmp_path):
        db = _make_db(tmp_path, [{"key": "D1", "path": "storage:WechatIMG.jpg", "present": False}])
        orphans = ZoteroReader(db, library_id=1).find_orphan_attachments()
        assert orphans[0].filename == "WechatIMG.jpg"

    def test_unknown_when_no_sync_columns(self, tmp_path):
        db = _make_db(tmp_path, [{"key": "X1", "path": "storage:gone.pdf", "present": False}], with_sync_cols=False)
        orphans = ZoteroReader(db, library_id=1).find_orphan_attachments()
        assert orphans[0].classification == "unknown"


def _invoke(args, data_dir: Path, json_out=True, **kw):
    base = ["--json"] if json_out else []
    env = {"ZOT_DATA_DIR": str(data_dir)}
    return CliRunner().invoke(main, base + args, env=env, **kw)


class TestOrphansListCLI:
    def test_list_reports_counts(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"key": "DEAD0001", "path": "storage:gone.pdf", "present": False, "syncState": 0},
                {"key": "RECOV0001", "path": "storage:later.pdf", "present": False, "syncState": 1},
            ],
        )
        result = _invoke(["orphans", "list"], tmp_path)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["total"] == 2
        assert data["counts"] == {"dead": 1, "recoverable": 1, "unknown": 0}

    def test_dead_only_filters(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"key": "DEAD0001", "path": "storage:gone.pdf", "present": False, "syncState": 0},
                {"key": "RECOV0001", "path": "storage:later.pdf", "present": False, "syncState": 1},
            ],
        )
        data = json.loads(_invoke(["orphans", "list", "--dead-only"], tmp_path).output)["data"]
        assert [o["attachment_key"] for o in data["orphans"]] == ["DEAD0001"]


class TestOrphansCleanCLI:
    def _two_orphans(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"key": "DEAD0001", "path": "storage:gone.pdf", "present": False, "syncState": 0},
                {"key": "RECOV0001", "path": "storage:later.pdf", "present": False, "syncState": 1},
            ],
        )

    def test_dry_run_targets_dead_only(self, tmp_path):
        self._two_orphans(tmp_path)
        data = json.loads(_invoke(["orphans", "clean", "--dry-run"], tmp_path).output)["data"]
        assert data["would_delete"] == ["DEAD0001"]
        assert data["count"] == 1

    def test_dry_run_include_recoverable(self, tmp_path):
        self._two_orphans(tmp_path)
        data = json.loads(_invoke(["orphans", "clean", "--dry-run", "--include-recoverable"], tmp_path).output)["data"]
        assert set(data["would_delete"]) == {"DEAD0001", "RECOV0001"}

    def test_clean_deletes_via_writer(self, tmp_path, monkeypatch):
        self._two_orphans(tmp_path)
        deleted: list[str] = []

        class FakeWriter:
            def __init__(self, *a, **k): ...
            def delete_item(self, key):
                deleted.append(key)

        monkeypatch.setattr("zotero_cli_cc.commands.orphans.ZoteroWriter", FakeWriter)
        env = {"ZOT_DATA_DIR": str(tmp_path), "ZOT_LIBRARY_ID": "123", "ZOT_API_KEY": "abc"}
        result = CliRunner().invoke(main, ["--json", "orphans", "clean", "--yes"], env=env)
        assert result.exit_code == 0
        assert deleted == ["DEAD0001"]
        data = json.loads(result.output)["data"]
        assert data["deleted"] == ["DEAD0001"]

    def test_clean_nothing_to_do(self, tmp_path):
        _make_db(tmp_path, [{"key": "RECOV0001", "path": "storage:later.pdf", "present": False, "syncState": 1}])
        env = {"ZOT_DATA_DIR": str(tmp_path), "ZOT_LIBRARY_ID": "123", "ZOT_API_KEY": "abc"}
        result = CliRunner().invoke(main, ["--json", "orphans", "clean", "--yes"], env=env)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["count"] == 0


class TestOrphansMCP:
    def test_handle_find_orphans(self, tmp_path, monkeypatch):
        from zotero_cli_cc import mcp_server

        db = _make_db(
            tmp_path,
            [
                {"key": "DEAD0001", "path": "storage:gone.pdf", "present": False, "syncState": 0},
                {"key": "RECOV0001", "path": "storage:later.pdf", "present": False, "syncState": 1},
            ],
        )
        monkeypatch.setattr(mcp_server, "_get_reader", lambda library="user": ZoteroReader(db, library_id=1))
        out = mcp_server._handle_find_orphans(dead_only=True)
        assert out["total"] == 1
        assert out["orphans"][0]["attachment_key"] == "DEAD0001"
