# Tier 2 Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 features: trash management, duplicate detection, file attachment upload, add-from-PDF, and group library support.

**Architecture:** Each feature follows the existing pattern: reader method (SQLite) or writer method (pyzotero API) → CLI command (Click) → MCP tool (FastMCP handler + decorator). Tests use `CliRunner` with `ZOT_DATA_DIR` env var pointing to test fixtures.

**Tech Stack:** Python 3.10+, Click, pyzotero, pymupdf, FastMCP, SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-03-24-tier2-features-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/zotero_cli_cc/models.py` | Add `DuplicateGroup` dataclass |
| `src/zotero_cli_cc/core/reader.py` | Add `get_trash_items()`, `find_duplicates()`, `resolve_group_library_id()`, library_id filtering |
| `src/zotero_cli_cc/core/writer.py` | Add `restore_from_trash()`, `upload_attachment()`, `library_type` param |
| `src/zotero_cli_cc/core/pdf_extractor.py` | Add `extract_doi()` |
| `src/zotero_cli_cc/commands/trash.py` | New: `zot trash list/restore` |
| `src/zotero_cli_cc/commands/duplicates.py` | New: `zot duplicates` |
| `src/zotero_cli_cc/commands/attach.py` | New: `zot attach KEY --file` |
| `src/zotero_cli_cc/commands/add.py` | Extend with `--pdf` option |
| `src/zotero_cli_cc/cli.py` | Register new commands, add `--library` option |
| `src/zotero_cli_cc/formatter.py` | Add `format_duplicates()` |
| `src/zotero_cli_cc/mcp_server.py` | Add handlers + tools for trash, duplicates, attach, add_from_pdf |
| `tests/fixtures/create_test_db.py` | Add `deletedItems` table, duplicate items, group library fixtures |
| `tests/test_trash.py` | Tests for trash list/restore |
| `tests/test_duplicates.py` | Tests for duplicate detection |
| `tests/test_attach.py` | Tests for file attachment upload |
| `tests/test_add_pdf.py` | Tests for add-from-PDF |
| `tests/test_group_library.py` | Tests for group library support |

---

### Task 1: Trash Management — Test Fixture & Reader

**Files:**
- Modify: `tests/fixtures/create_test_db.py`
- Modify: `src/zotero_cli_cc/core/reader.py`
- Create: `tests/test_trash.py`

**Context:** The Zotero SQLite schema has a `deletedItems` table with `(itemID, dateDeleted)`. Items in trash are regular items that also have a row in `deletedItems`. The reader needs a method to query these.

- [ ] **Step 1: Add `deletedItems` table and test data to fixture**

In `tests/fixtures/create_test_db.py`, add after the `itemRelations`/`relationPredicates` CREATE statements (before the test data section):

```python
# Add to the executescript block:
CREATE TABLE deletedItems (
    itemID INTEGER PRIMARY KEY,
    dateDeleted DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (itemID) REFERENCES items(itemID) ON DELETE CASCADE
);
CREATE INDEX deletedItems_dateDeleted ON deletedItems(dateDeleted);
```

Then after all existing test data inserts, add a new trashed item:

```python
# Item 7: Trashed item "Old Survey Paper"
c.execute("INSERT INTO items VALUES (7, 2, '2023-06-01', '2023-06-02', '2023-06-02', 1, 'TRSH007')")
c.execute("INSERT INTO itemDataValues VALUES (15, 'Old Survey of Neural Networks')")
c.execute("INSERT INTO itemDataValues VALUES (16, '2010')")
c.execute("INSERT INTO itemData VALUES (7, 4, 15)")  # title
c.execute("INSERT INTO itemData VALUES (7, 14, 16)")  # date
c.execute("INSERT INTO creators VALUES (6, 'John', 'Smith')")
c.execute("INSERT INTO itemCreators VALUES (7, 6, 1, 0)")
c.execute("INSERT INTO deletedItems VALUES (7, '2024-03-01 12:00:00')")
```

Run: `python tests/fixtures/create_test_db.py` to regenerate.

- [ ] **Step 2: Write failing tests for `get_trash_items`**

Create `tests/test_trash.py`:

```python
"""Tests for trash management (list and restore)."""
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
```

Run: `pytest tests/test_trash.py -v`
Expected: FAIL — `ZoteroReader` has no `get_trash_items` method.

- [ ] **Step 3: Implement `get_trash_items` in reader**

In `src/zotero_cli_cc/core/reader.py`, add after `get_recent_items`:

```python
def get_trash_items(self, limit: int = 50) -> list[Item]:
    """Return items in the trash, ordered by deletion date (newest first)."""
    conn = self._connect()
    excl_sql, excl_params = self._excluded_filter()
    rows = conn.execute(
        f"SELECT i.itemID FROM items i "
        f"JOIN deletedItems d ON i.itemID = d.itemID "
        f"WHERE i.itemTypeID {excl_sql} "
        f"ORDER BY d.dateDeleted DESC LIMIT ?",
        (*excl_params, limit),
    ).fetchall()
    item_ids = [r["itemID"] for r in rows]
    return self._get_items_batch(conn, item_ids) if item_ids else []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_trash.py::TestTrashReader -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/create_test_db.py tests/fixtures/zotero.sqlite src/zotero_cli_cc/core/reader.py tests/test_trash.py
git commit -m "feat(trash): add get_trash_items reader method with fixture"
```

---

### Task 2: Trash Management — Writer & CLI & MCP

**Files:**
- Modify: `src/zotero_cli_cc/core/writer.py`
- Create: `src/zotero_cli_cc/commands/trash.py`
- Modify: `src/zotero_cli_cc/cli.py`
- Modify: `src/zotero_cli_cc/mcp_server.py`
- Modify: `tests/test_trash.py`

**Context:** Restoring from trash requires `pyzotero`: fetch item, set `item["data"]["deleted"] = 0`, call `update_item`. The CLI is a Click group with `list` and `restore` subcommands. MCP gets `trash_list` and `trash_restore` tools.

- [ ] **Step 1: Write failing tests for writer, CLI, and MCP**

Append to `tests/test_trash.py`:

```python
import pytest

from zotero_cli_cc.core.writer import ZoteroWriteError, ZoteroWriter


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
        data = json.loads(result.output)
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
```

Run: `pytest tests/test_trash.py -v`
Expected: FAIL — missing `restore_from_trash`, `trash` command, `_handle_trash_list/restore`.

- [ ] **Step 2: Implement writer method**

In `src/zotero_cli_cc/core/writer.py`, add after `update_item`:

```python
def restore_from_trash(self, key: str) -> None:
    """Restore an item from trash by clearing its deleted flag."""
    try:
        item = self._zot.item(key)
        item["data"]["deleted"] = 0
        self._zot.update_item(item)
    except ResourceNotFoundError:
        raise ZoteroWriteError(f"Item '{key}' not found")
    except (HttpxConnectError, HttpxTimeoutException) as e:
        raise ZoteroWriteError(f"Network error: {e}") from e
```

- [ ] **Step 3: Create CLI command**

Create `src/zotero_cli_cc/commands/trash.py`:

```python
from __future__ import annotations

import os

import click

from zotero_cli_cc.config import get_data_dir, load_config
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.formatter import format_error, format_items
from zotero_cli_cc.models import ErrorInfo


@click.group("trash")
def trash_group() -> None:
    """Manage trashed items (list, restore)."""
    pass


@trash_group.command("list")
@click.pass_context
def trash_list_cmd(ctx: click.Context) -> None:
    """List items in the trash.

    \b
    Examples:
      zot trash list
      zot --json trash list
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    reader = ZoteroReader(data_dir / "zotero.sqlite")
    try:
        limit = ctx.obj.get("limit", cfg.default_limit)
        items = reader.get_trash_items(limit=limit)
        if not items:
            if ctx.obj.get("json"):
                click.echo("[]")
            else:
                click.echo("Trash is empty.")
            return
        detail = ctx.obj.get("detail", "standard")
        click.echo(format_items(items, output_json=ctx.obj.get("json", False), detail=detail))
    finally:
        reader.close()


@trash_group.command("restore")
@click.argument("keys", nargs=-1, required=True)
@click.pass_context
def trash_restore_cmd(ctx: click.Context, keys: tuple[str, ...]) -> None:
    """Restore item(s) from trash.

    \b
    Examples:
      zot trash restore ABC123
      zot trash restore KEY1 KEY2 KEY3
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    if not library_id or not api_key:
        click.echo(
            format_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="trash restore",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        )
        return

    writer = ZoteroWriter(library_id=library_id, api_key=api_key)
    any_success = False
    for key in keys:
        try:
            writer.restore_from_trash(key)
            click.echo(f"Restored: {key}")
            any_success = True
        except ZoteroWriteError as e:
            click.echo(
                format_error(
                    ErrorInfo(message=str(e), context="trash restore", hint=f"Failed for key '{key}'"),
                    output_json=json_out,
                )
            )
    if any_success:
        click.echo(SYNC_REMINDER)
```

- [ ] **Step 4: Register in CLI**

In `src/zotero_cli_cc/cli.py`, add import:
```python
from zotero_cli_cc.commands.trash import trash_group
```
And registration:
```python
main.add_command(trash_group, "trash")
```

- [ ] **Step 5: Add MCP handlers and tools**

In `src/zotero_cli_cc/mcp_server.py`, add handler functions (after existing write handlers):

```python
def _handle_trash_list(limit: int = 50) -> dict:
    reader = _get_reader()
    items = reader.get_trash_items(limit=limit)
    return {"items": [_item_to_dict(i) for i in items], "total": len(items)}


def _handle_trash_restore(key: str) -> dict:
    try:
        writer = _get_writer()
        writer.restore_from_trash(key)
        return {"key": key, "restored": True}
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "trash_restore"}
```

And tool definitions (after existing tool definitions):

```python
@mcp.tool()
def trash_list(limit: int = 50) -> dict:
    """List items currently in the Zotero trash.

    Args:
        limit: Maximum number of trashed items to return (default 50).
    """
    return _handle_trash_list(limit)


@mcp.tool()
def trash_restore(key: str) -> dict:
    """Restore a trashed item back to the Zotero library.

    Args:
        key: The item key to restore from trash.
    """
    return _handle_trash_restore(key)
```

- [ ] **Step 6: Run all tests**

Run: `pytest tests/test_trash.py -v`
Expected: All tests PASS.

Run: `pytest tests/ -v --tb=short`
Expected: All existing tests still pass (no regressions).

- [ ] **Step 7: Lint and commit**

```bash
ruff check src/zotero_cli_cc/commands/trash.py src/zotero_cli_cc/core/writer.py src/zotero_cli_cc/mcp_server.py --fix
ruff format src/zotero_cli_cc/commands/trash.py src/zotero_cli_cc/core/writer.py src/zotero_cli_cc/mcp_server.py
git add src/zotero_cli_cc/commands/trash.py src/zotero_cli_cc/core/writer.py src/zotero_cli_cc/cli.py src/zotero_cli_cc/mcp_server.py tests/test_trash.py
git commit -m "feat(trash): add trash list and restore commands with MCP tools"
```

---

### Task 3: Duplicate Detection — Model, Reader & Formatter

**Files:**
- Modify: `src/zotero_cli_cc/models.py`
- Modify: `src/zotero_cli_cc/core/reader.py`
- Modify: `src/zotero_cli_cc/formatter.py`
- Modify: `tests/fixtures/create_test_db.py`
- Create: `tests/test_duplicates.py`

**Context:** Duplicate detection is read-only. It uses DOI exact match and/or fuzzy title comparison via `difflib.SequenceMatcher`. The reader loads items from SQLite, normalizes titles, and groups duplicates. Uses `_excluded_filter()` for type exclusion. Capped at 10k items to avoid O(n^2) blowup.

- [ ] **Step 1: Add duplicate item to test fixture**

In `tests/fixtures/create_test_db.py`, add another item with the same DOI as ATTN001 (`10.5555/attention`):

```python
# Item 8: Duplicate of ATTN001 (same DOI)
c.execute("INSERT INTO items VALUES (8, 2, '2024-05-01', '2024-05-02', '2024-05-02', 1, 'DUPE008')")
c.execute("INSERT INTO itemDataValues VALUES (17, 'Attention Is All You Need (duplicate)')")
c.execute("INSERT INTO itemDataValues VALUES (18, '10.5555/attention')")  # Same DOI as ATTN001
c.execute("INSERT INTO itemData VALUES (8, 4, 17)")  # title
c.execute("INSERT INTO itemData VALUES (8, 26, 18)")  # DOI
```

Run: `python tests/fixtures/create_test_db.py`

- [ ] **Step 2: Add `DuplicateGroup` model**

In `src/zotero_cli_cc/models.py`, add:

```python
@dataclass
class DuplicateGroup:
    items: list[Item]
    match_type: str  # "doi" | "title"
    score: float  # 1.0 for DOI exact match, 0.0-1.0 for title similarity
```

- [ ] **Step 3: Write failing tests**

Create `tests/test_duplicates.py`:

```python
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
```

Run: `pytest tests/test_duplicates.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement `find_duplicates` in reader**

In `src/zotero_cli_cc/core/reader.py`:
- Add imports at top: `import re` and `from difflib import SequenceMatcher`
- Add import: `from zotero_cli_cc.models import DuplicateGroup` (add to existing import line)
- Add method after `get_trash_items`:

```python
def find_duplicates(
    self,
    strategy: str = "both",
    threshold: float = 0.85,
    limit: int = 50,
) -> list[DuplicateGroup]:
    """Find potential duplicate items by DOI and/or title similarity.

    Args:
        strategy: "doi", "title", or "both"
        threshold: Minimum similarity for title matching (0.0–1.0)
        limit: Maximum number of duplicate groups to return
    """
    conn = self._connect()
    excl_sql, excl_params = self._excluded_filter()

    # Load items for comparison (cap at 10k most recent)
    rows = conn.execute(
        f"SELECT i.itemID, i.key FROM items i "
        f"WHERE i.itemTypeID {excl_sql} "
        f"ORDER BY i.dateAdded DESC LIMIT 10000",
        excl_params,
    ).fetchall()

    item_keys = {r["itemID"]: r["key"] for r in rows}
    item_ids = list(item_keys.keys())
    if not item_ids:
        return []

    groups: list[DuplicateGroup] = []
    seen_group_keys: set[frozenset[str]] = set()

    # --- DOI strategy ---
    if strategy in ("doi", "both"):
        ph = ",".join("?" * len(item_ids))
        doi_rows = conn.execute(
            f"SELECT id.itemID, iv.value FROM itemData id "
            f"JOIN fields f ON id.fieldID = f.fieldID "
            f"JOIN itemDataValues iv ON id.valueID = iv.valueID "
            f"WHERE f.fieldName = 'DOI' AND id.itemID IN ({ph}) AND iv.value != ''",
            item_ids,
        ).fetchall()

        doi_map: dict[str, list[int]] = {}
        for r in doi_rows:
            doi_map.setdefault(r["value"].strip().lower(), []).append(r["itemID"])

        for doi_val, ids in doi_map.items():
            if len(ids) < 2:
                continue
            group_key = frozenset(item_keys[i] for i in ids)
            if group_key in seen_group_keys:
                continue
            seen_group_keys.add(group_key)
            items = self._get_items_batch(conn, ids)
            if len(items) >= 2:
                groups.append(DuplicateGroup(items=items, match_type="doi", score=1.0))

    # --- Title strategy ---
    if strategy in ("title", "both"):
        # Load titles
        ph = ",".join("?" * len(item_ids))
        title_rows = conn.execute(
            f"SELECT id.itemID, iv.value FROM itemData id "
            f"JOIN fields f ON id.fieldID = f.fieldID "
            f"JOIN itemDataValues iv ON id.valueID = iv.valueID "
            f"WHERE f.fieldName = 'title' AND id.itemID IN ({ph})",
            item_ids,
        ).fetchall()

        def _normalize(title: str) -> str:
            t = re.sub(r"[^\w\s]", "", title.lower()).strip()
            return re.sub(r"\s+", " ", t)

        title_items: list[tuple[int, str, str]] = []  # (itemID, original, normalized)
        for r in title_rows:
            title_items.append((r["itemID"], r["value"], _normalize(r["value"])))

        # Group exact normalized matches (O(n))
        norm_groups: dict[str, list[int]] = {}
        for item_id, orig, norm in title_items:
            norm_groups.setdefault(norm, []).append(item_id)

        for norm, ids in norm_groups.items():
            if len(ids) >= 2:
                group_key = frozenset(item_keys[i] for i in ids)
                if group_key not in seen_group_keys:
                    seen_group_keys.add(group_key)
                    items = self._get_items_batch(conn, ids)
                    if len(items) >= 2:
                        groups.append(DuplicateGroup(items=items, match_type="title", score=1.0))

        # Fuzzy match singletons only (O(n^2) on singletons)
        singletons = [(item_id, norm) for item_id, _, norm in title_items
                      if len(norm_groups[norm]) == 1]
        matched: set[int] = set()
        for idx, (id_a, norm_a) in enumerate(singletons):
            if id_a in matched:
                continue
            cluster = [id_a]
            for j in range(idx + 1, len(singletons)):
                id_b, norm_b = singletons[j]
                if id_b in matched:
                    continue
                ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
                if ratio >= threshold:
                    cluster.append(id_b)
                    matched.add(id_b)
            if len(cluster) >= 2:
                matched.add(id_a)
                group_key = frozenset(item_keys[cid] for cid in cluster)
                if group_key not in seen_group_keys:
                    seen_group_keys.add(group_key)
                    items = self._get_items_batch(conn, cluster)
                    best_score = max(
                        SequenceMatcher(None, _normalize(items[0].title), _normalize(it.title)).ratio()
                        for it in items[1:]
                    ) if len(items) >= 2 else 0.0
                    groups.append(DuplicateGroup(items=items, match_type="title", score=round(best_score, 3)))

    return groups[:limit]
```

- [ ] **Step 5: Add `format_duplicates` to formatter**

In `src/zotero_cli_cc/formatter.py`, add import of `DuplicateGroup` and the function:

```python
from zotero_cli_cc.models import Collection, DuplicateGroup, ErrorInfo, Item, Note


def format_duplicates(groups: list[DuplicateGroup], output_json: bool = False) -> str:
    if output_json:
        data = []
        for i, g in enumerate(groups, 1):
            data.append({
                "group": i,
                "match_type": g.match_type,
                "score": g.score,
                "items": [asdict(item) for item in g.items],
            })
        return json.dumps(data, indent=2, ensure_ascii=False)
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    table = Table(show_header=True, header_style="bold")
    table.add_column("Group", width=6)
    table.add_column("Keys", width=20)
    table.add_column("Title", width=50)
    table.add_column("Match", width=8)
    table.add_column("Score", width=6)
    for i, g in enumerate(groups, 1):
        keys = ", ".join(item.key for item in g.items)
        title = g.items[0].title if g.items else ""
        table.add_row(str(i), keys, title, g.match_type, f"{g.score:.2f}")
    console.print(table)
    return buf.getvalue()
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_duplicates.py::TestDuplicateReader -v`
Expected: All reader tests PASS.

- [ ] **Step 7: Lint and commit**

```bash
ruff check src/zotero_cli_cc/models.py src/zotero_cli_cc/core/reader.py src/zotero_cli_cc/formatter.py --fix
ruff format src/zotero_cli_cc/models.py src/zotero_cli_cc/core/reader.py src/zotero_cli_cc/formatter.py
git add src/zotero_cli_cc/models.py src/zotero_cli_cc/core/reader.py src/zotero_cli_cc/formatter.py tests/fixtures/create_test_db.py tests/fixtures/zotero.sqlite tests/test_duplicates.py
git commit -m "feat(duplicates): add duplicate detection reader, model, and formatter"
```

---

### Task 4: Duplicate Detection — CLI & MCP

**Files:**
- Create: `src/zotero_cli_cc/commands/duplicates.py`
- Modify: `src/zotero_cli_cc/cli.py`
- Modify: `src/zotero_cli_cc/mcp_server.py`
- Modify: `tests/test_duplicates.py`

- [ ] **Step 1: Create CLI command**

Create `src/zotero_cli_cc/commands/duplicates.py`:

```python
from __future__ import annotations

import click

from zotero_cli_cc.config import get_data_dir, load_config
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_duplicates


@click.command("duplicates")
@click.option(
    "--by",
    "strategy",
    default="both",
    type=click.Choice(["doi", "title", "both"]),
    help="Detection strategy (default: both)",
)
@click.option("--threshold", default=0.85, type=float, help="Title similarity threshold (default: 0.85)")
@click.pass_context
def duplicates_cmd(ctx: click.Context, strategy: str, threshold: float) -> None:
    """Find potential duplicate items in the library.

    \b
    Examples:
      zot duplicates
      zot duplicates --by doi
      zot duplicates --by title --threshold 0.9
      zot --json duplicates
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    reader = ZoteroReader(data_dir / "zotero.sqlite")
    try:
        limit = ctx.obj.get("limit", cfg.default_limit)
        groups = reader.find_duplicates(strategy=strategy, threshold=threshold, limit=limit)
        if not groups:
            if ctx.obj.get("json"):
                click.echo("[]")
            else:
                click.echo("No duplicates found.")
            return
        click.echo(format_duplicates(groups, output_json=ctx.obj.get("json", False)))
    finally:
        reader.close()
```

- [ ] **Step 2: Register in CLI**

In `src/zotero_cli_cc/cli.py`, add import:
```python
from zotero_cli_cc.commands.duplicates import duplicates_cmd
```
And registration:
```python
main.add_command(duplicates_cmd, "duplicates")
```

- [ ] **Step 3: Add MCP handler and tool**

In `src/zotero_cli_cc/mcp_server.py`:

Handler:
```python
def _handle_duplicates(strategy: str = "both", threshold: float = 0.85, limit: int = 50) -> dict:
    reader = _get_reader()
    groups = reader.find_duplicates(strategy=strategy, threshold=threshold, limit=limit)
    result_groups = []
    for g in groups:
        result_groups.append({
            "match_type": g.match_type,
            "score": g.score,
            "items": [_item_to_dict(i) for i in g.items],
        })
    return {"groups": result_groups, "total": len(result_groups)}
```

Tool:
```python
@mcp.tool()
def duplicates(strategy: str = "both", threshold: float = 0.85, limit: int = 50) -> dict:
    """Find potential duplicate items by DOI and/or title similarity.

    Args:
        strategy: Detection strategy — 'doi', 'title', or 'both' (default 'both').
        threshold: Minimum title similarity ratio (0.0–1.0, default 0.85).
        limit: Maximum number of duplicate groups to return (default 50).
    """
    return _handle_duplicates(strategy, threshold, limit)
```

Add import at top of `mcp_server.py`:
```python
from zotero_cli_cc.models import Collection, DuplicateGroup, Item, Note
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/test_duplicates.py -v`
Expected: All PASS.

Run: `pytest tests/ -v --tb=short`
Expected: No regressions.

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/zotero_cli_cc/commands/duplicates.py src/zotero_cli_cc/cli.py src/zotero_cli_cc/mcp_server.py --fix
ruff format src/zotero_cli_cc/commands/duplicates.py src/zotero_cli_cc/cli.py src/zotero_cli_cc/mcp_server.py
git add src/zotero_cli_cc/commands/duplicates.py src/zotero_cli_cc/cli.py src/zotero_cli_cc/mcp_server.py tests/test_duplicates.py
git commit -m "feat(duplicates): add duplicates CLI command and MCP tool"
```

---

### Task 5: File Attachment Upload

**Files:**
- Modify: `src/zotero_cli_cc/core/writer.py`
- Create: `src/zotero_cli_cc/commands/attach.py`
- Modify: `src/zotero_cli_cc/cli.py`
- Modify: `src/zotero_cli_cc/mcp_server.py`
- Create: `tests/test_attach.py`

**Context:** pyzotero's `attachment_simple([path], parentid)` returns `{"success": [...], "failure": [...], "unchanged": [...]}`. Success items have a `"key"` field. Unchanged means identical file already uploaded (same MD5). Treat unchanged as success.

- [ ] **Step 1: Write failing tests**

Create `tests/test_attach.py`:

```python
"""Tests for file attachment upload."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.writer import ZoteroWriteError, ZoteroWriter


class TestAttachWriter:
    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_upload_attachment_success(self, mock_zotero_cls, tmp_path):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        mock_zot.attachment_simple.return_value = {
            "success": [{"key": "ATT001", "filename": "test.pdf"}],
            "failure": [],
            "unchanged": [],
        }
        writer = ZoteroWriter(library_id="123", api_key="abc")
        key = writer.upload_attachment("PARENT1", pdf)
        assert key == "ATT001"
        mock_zot.attachment_simple.assert_called_once()

    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_upload_attachment_unchanged(self, mock_zotero_cls, tmp_path):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        mock_zot.attachment_simple.return_value = {
            "success": [],
            "failure": [],
            "unchanged": [{"key": "ATT001"}],
        }
        writer = ZoteroWriter(library_id="123", api_key="abc")
        key = writer.upload_attachment("PARENT1", pdf)
        assert key == "ATT001"

    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_upload_attachment_failure(self, mock_zotero_cls, tmp_path):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        mock_zot.attachment_simple.return_value = {
            "success": [],
            "failure": [{"key": "", "message": "Upload failed"}],
            "unchanged": [],
        }
        writer = ZoteroWriter(library_id="123", api_key="abc")
        with pytest.raises(ZoteroWriteError, match="Upload failed"):
            writer.upload_attachment("PARENT1", pdf)

    def test_upload_attachment_file_not_found(self):
        with patch("zotero_cli_cc.core.writer.zotero.Zotero"):
            writer = ZoteroWriter(library_id="123", api_key="abc")
            with pytest.raises(ZoteroWriteError, match="not found"):
                writer.upload_attachment("PARENT1", Path("/nonexistent/file.pdf"))

    @patch("zotero_cli_cc.core.writer.zotero.Zotero")
    def test_upload_attachment_empty_response(self, mock_zotero_cls, tmp_path):
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        mock_zot.attachment_simple.return_value = {
            "success": [],
            "failure": [],
            "unchanged": [],
        }
        writer = ZoteroWriter(library_id="123", api_key="abc")
        with pytest.raises(ZoteroWriteError, match="Unexpected"):
            writer.upload_attachment("PARENT1", pdf)


class TestAttachMCP:
    def test_handle_attach(self):
        from zotero_cli_cc.mcp_server import _handle_attach
        with patch("zotero_cli_cc.mcp_server._get_writer") as mock_get:
            mock_writer = MagicMock()
            mock_get.return_value = mock_writer
            mock_writer.upload_attachment.return_value = "ATT001"
            result = _handle_attach("PARENT1", "/tmp/test.pdf")
            assert result["key"] == "ATT001"
```

Run: `pytest tests/test_attach.py -v`
Expected: FAIL.

- [ ] **Step 2: Implement writer method**

In `src/zotero_cli_cc/core/writer.py`, add after `restore_from_trash`:

```python
def upload_attachment(self, parent_key: str, file_path: Path) -> str:
    """Upload a file attachment to an existing item. Returns attachment key."""
    if not file_path.exists():
        raise ZoteroWriteError(f"File not found: {file_path}")
    try:
        resp = self._zot.attachment_simple([str(file_path)], parentid=parent_key)
        if resp.get("success"):
            return str(resp["success"][0]["key"])
        if resp.get("unchanged"):
            return str(resp["unchanged"][0]["key"])
        if resp.get("failure"):
            msg = resp["failure"][0].get("message", "Upload failed")
            raise ZoteroWriteError(f"Attachment upload failed: {msg}")
        raise ZoteroWriteError("Unexpected empty response from attachment upload")
    except (HttpxConnectError, HttpxTimeoutException) as e:
        raise ZoteroWriteError(f"Network error: {e}") from e
```

Add `from pathlib import Path` to the imports at top of `writer.py`.

- [ ] **Step 3: Create CLI command**

Create `src/zotero_cli_cc/commands/attach.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.formatter import format_error
from zotero_cli_cc.models import ErrorInfo


@click.command("attach")
@click.argument("key")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="File to upload")
@click.pass_context
def attach_cmd(ctx: click.Context, key: str, file_path: str) -> None:
    """Upload a file attachment to an existing Zotero item.

    \b
    Examples:
      zot attach ABC123 --file paper.pdf
      zot attach ABC123 --file ~/Downloads/supplement.pdf
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    if not library_id or not api_key:
        click.echo(
            format_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="attach",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        )
        return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key)
    try:
        att_key = writer.upload_attachment(key, Path(file_path))
        click.echo(f"Attachment uploaded: {att_key}")
        click.echo(SYNC_REMINDER)
    except ZoteroWriteError as e:
        click.echo(
            format_error(
                ErrorInfo(message=str(e), context="attach", hint="Check the item key and file path"),
                output_json=json_out,
            )
        )
```

- [ ] **Step 4: Register in CLI and add MCP**

In `src/zotero_cli_cc/cli.py`:
```python
from zotero_cli_cc.commands.attach import attach_cmd
# ...
main.add_command(attach_cmd, "attach")
```

In `src/zotero_cli_cc/mcp_server.py`:

Handler:
```python
def _handle_attach(parent_key: str, file_path: str) -> dict:
    try:
        writer = _get_writer()
        att_key = writer.upload_attachment(parent_key, Path(file_path))
        return {"key": att_key, "parent_key": parent_key, "filename": Path(file_path).name}
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "attach"}
```

Add `from pathlib import Path` to imports if not already present.

Tool:
```python
@mcp.tool()
def attach(parent_key: str, file_path: str) -> dict:
    """Upload a file attachment to an existing Zotero item.

    Args:
        parent_key: The item key to attach the file to.
        file_path: Path to the file to upload.
    """
    return _handle_attach(parent_key, file_path)
```

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_attach.py -v`
Expected: All PASS.

Run: `pytest tests/ -v --tb=short`
Expected: No regressions.

```bash
ruff check src/zotero_cli_cc/commands/attach.py src/zotero_cli_cc/core/writer.py src/zotero_cli_cc/mcp_server.py --fix
ruff format src/zotero_cli_cc/commands/attach.py src/zotero_cli_cc/core/writer.py src/zotero_cli_cc/mcp_server.py
git add src/zotero_cli_cc/commands/attach.py src/zotero_cli_cc/core/writer.py src/zotero_cli_cc/cli.py src/zotero_cli_cc/mcp_server.py tests/test_attach.py
git commit -m "feat(attach): add file attachment upload command and MCP tool"
```

---

### Task 6: Add from Local PDF

**Files:**
- Modify: `src/zotero_cli_cc/core/pdf_extractor.py`
- Modify: `src/zotero_cli_cc/commands/add.py`
- Modify: `src/zotero_cli_cc/mcp_server.py`
- Create: `tests/test_add_pdf.py`

**Context:** `zot add --pdf paper.pdf` extracts DOI from first 2 pages, creates item via API, then uploads the PDF as attachment. If DOI not found, fails with hint. Uses existing `extract_text_from_pdf` and `upload_attachment`. The `--pdf` option uses Click dest name `pdf_file` to avoid collision with `--from-file`.

**Important:** The Zotero Web API does NOT auto-resolve DOI metadata. Created items are bare (just DOI field). This is documented in help text.

- [ ] **Step 1: Write failing tests**

Create `tests/test_add_pdf.py`:

```python
"""Tests for add-from-PDF feature."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zotero_cli_cc.core.pdf_extractor import extract_doi


class TestExtractDoi:
    def test_extract_doi_found(self, tmp_path):
        # Create a mock text that extract_text_from_pdf would return
        with patch("zotero_cli_cc.core.pdf_extractor.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "Some text with DOI 10.1038/s41586-023-06139-9 in it"
            result = extract_doi(tmp_path / "dummy.pdf")
            assert result == "10.1038/s41586-023-06139-9"

    def test_extract_doi_not_found(self, tmp_path):
        with patch("zotero_cli_cc.core.pdf_extractor.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "No DOI in this text"
            result = extract_doi(tmp_path / "dummy.pdf")
            assert result is None

    def test_extract_doi_strips_trailing_punctuation(self, tmp_path):
        with patch("zotero_cli_cc.core.pdf_extractor.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "DOI: 10.1234/test.paper)."
            result = extract_doi(tmp_path / "dummy.pdf")
            assert result == "10.1234/test.paper"

    def test_extract_doi_multiple_returns_first(self, tmp_path):
        with patch("zotero_cli_cc.core.pdf_extractor.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "10.1234/first and 10.5678/second"
            result = extract_doi(tmp_path / "dummy.pdf")
            assert result == "10.1234/first"


class TestAddPdfMCP:
    def test_handle_add_from_pdf_with_doi_override(self):
        from zotero_cli_cc.mcp_server import _handle_add_from_pdf
        with patch("zotero_cli_cc.mcp_server._get_writer") as mock_get:
            mock_writer = MagicMock()
            mock_get.return_value = mock_writer
            mock_writer.add_item.return_value = "NEW001"
            mock_writer.upload_attachment.return_value = "ATT001"
            result = _handle_add_from_pdf("/tmp/test.pdf", doi_override="10.1234/test")
            mock_writer.add_item.assert_called_once_with(doi="10.1234/test")
            assert result["item_key"] == "NEW001"
            assert result["attachment_key"] == "ATT001"

    def test_handle_add_from_pdf_no_doi_found(self):
        from zotero_cli_cc.mcp_server import _handle_add_from_pdf
        with patch("zotero_cli_cc.mcp_server._get_writer"), \
             patch("zotero_cli_cc.core.pdf_extractor.extract_doi", return_value=None):
            result = _handle_add_from_pdf("/tmp/test.pdf")
            assert "error" in result

    def test_handle_add_from_pdf_upload_fails(self):
        from zotero_cli_cc.mcp_server import _handle_add_from_pdf
        from zotero_cli_cc.core.writer import ZoteroWriteError
        with patch("zotero_cli_cc.mcp_server._get_writer") as mock_get, \
             patch("zotero_cli_cc.core.pdf_extractor.extract_doi", return_value="10.1234/test"):
            mock_writer = MagicMock()
            mock_get.return_value = mock_writer
            mock_writer.add_item.return_value = "NEW001"
            mock_writer.upload_attachment.side_effect = ZoteroWriteError("Upload failed")
            result = _handle_add_from_pdf("/tmp/test.pdf")
            assert result["item_key"] == "NEW001"
            assert "error" in result
            assert "Retry with" in result["error"]
```

Run: `pytest tests/test_add_pdf.py -v`
Expected: FAIL.

- [ ] **Step 2: Implement `extract_doi`**

In `src/zotero_cli_cc/core/pdf_extractor.py`, add at top:
```python
import re
```

Add after `extract_annotations`:

```python
def extract_doi(pdf_path: Path) -> str | None:
    """Extract DOI from first 2 pages of a PDF. Returns first match or None."""
    try:
        text = extract_text_from_pdf(pdf_path, pages=(1, 2))
    except (PdfExtractionError, FileNotFoundError):
        return None
    match = re.search(r"10\.\d{4,9}/[^\s]+", text)
    if match:
        return match.group(0).rstrip(".,;)]}>'\"")
    return None
```

- [ ] **Step 3: Extend `add` command with `--pdf`**

In `src/zotero_cli_cc/commands/add.py`, add the `--pdf` option to `add_cmd`:

```python
@click.option(
    "--pdf",
    "pdf_file",
    default=None,
    type=click.Path(exists=True),
    help="PDF file to extract DOI from and attach (metadata not auto-resolved by API)",
)
```

Update the function signature to include `pdf_file: str | None`. Add handling logic at the start of the function body (after credential check, before the `from_file` check):

```python
if pdf_file:
    _add_from_pdf(Path(pdf_file), doi, library_id, api_key, json_out)
    return
```

Add the helper function:

```python
def _add_from_pdf(pdf_path: Path, doi_override: str | None, library_id: str, api_key: str, json_out: bool) -> None:
    """Add item from PDF: extract DOI, create item, upload attachment."""
    from zotero_cli_cc.core.pdf_extractor import extract_doi

    doi = doi_override
    if not doi:
        doi = extract_doi(pdf_path)
    if not doi:
        click.echo(
            format_error(
                ErrorInfo(
                    message="No DOI found in PDF",
                    context="add",
                    hint="Use --doi to specify the DOI manually: zot add --pdf paper.pdf --doi '10.1234/...'",
                ),
                output_json=json_out,
            )
        )
        return

    writer = ZoteroWriter(library_id=library_id, api_key=api_key)
    try:
        key = writer.add_item(doi=doi)
        click.echo(f"Item created: {key} (DOI: {doi})")
    except ZoteroWriteError as e:
        click.echo(format_error(ErrorInfo(message=str(e), context="add"), output_json=json_out))
        return

    try:
        att_key = writer.upload_attachment(key, pdf_path)
        click.echo(f"Attachment uploaded: {att_key}")
        click.echo(SYNC_REMINDER)
        click.echo("Note: Zotero API creates bare items. Sync and use Zotero desktop to retrieve full metadata.")
    except ZoteroWriteError as e:
        click.echo(f"Item created ({key}) but attachment upload failed: {e}")
        click.echo(f"Retry with: zot attach {key} --file {pdf_path}")
```

- [ ] **Step 4: Add MCP handler and tool**

In `src/zotero_cli_cc/mcp_server.py`:

```python
def _handle_add_from_pdf(file_path: str, doi_override: str | None = None) -> dict:
    from zotero_cli_cc.core.pdf_extractor import extract_doi

    doi = doi_override
    if not doi:
        doi = extract_doi(Path(file_path))
    if not doi:
        return {"error": "No DOI found in PDF. Use doi_override to specify manually."}

    try:
        writer = _get_writer()
        item_key = writer.add_item(doi=doi)
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "add_from_pdf"}

    try:
        att_key = writer.upload_attachment(item_key, Path(file_path))
        return {
            "item_key": item_key,
            "attachment_key": att_key,
            "doi": doi,
            "note": "Item created with DOI only. Sync with Zotero desktop to retrieve full metadata.",
        }
    except ZoteroWriteError as e:
        return {
            "item_key": item_key,
            "doi": doi,
            "error": f"Attachment upload failed: {e}. Retry with: attach(parent_key='{item_key}', file_path='{file_path}')",
        }


@mcp.tool()
def add_from_pdf(file_path: str, doi_override: str | None = None) -> dict:
    """Add an item from a local PDF by extracting its DOI, then attach the PDF.

    Note: The Zotero Web API creates bare items (DOI only). Sync with Zotero desktop
    to retrieve full metadata (title, authors, etc.).

    Args:
        file_path: Path to the PDF file.
        doi_override: Optional DOI to use instead of extracting from PDF.
    """
    return _handle_add_from_pdf(file_path, doi_override)
```

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_add_pdf.py -v`
Expected: All PASS.

Run: `pytest tests/ -v --tb=short`
Expected: No regressions.

```bash
ruff check src/zotero_cli_cc/core/pdf_extractor.py src/zotero_cli_cc/commands/add.py src/zotero_cli_cc/mcp_server.py --fix
ruff format src/zotero_cli_cc/core/pdf_extractor.py src/zotero_cli_cc/commands/add.py src/zotero_cli_cc/mcp_server.py
git add src/zotero_cli_cc/core/pdf_extractor.py src/zotero_cli_cc/commands/add.py src/zotero_cli_cc/mcp_server.py tests/test_add_pdf.py
git commit -m "feat(add): add --pdf option to extract DOI and attach PDF"
```

---

### Task 7: Group Library Support — Reader Changes

**Files:**
- Modify: `tests/fixtures/create_test_db.py`
- Modify: `src/zotero_cli_cc/core/reader.py`
- Create: `tests/test_group_library.py`

**Context:** Zotero stores all libraries in one `zotero.sqlite`. The `items` table has a `libraryID` column (1=user, 2+=groups). The `groups` table maps `groupID` (public, used by pyzotero) to `libraryID` (SQLite internal). Reader needs to filter by `libraryID` when a group is specified.

- [ ] **Step 1: Add group library data to fixture**

In `tests/fixtures/create_test_db.py`, add to the `executescript` block:

```python
CREATE TABLE groups (
    groupID INTEGER PRIMARY KEY,
    libraryID INT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1
);
```

After `INSERT INTO libraries VALUES (1, 'user', 1, 1);`:
```python
INSERT INTO libraries VALUES (2, 'group', 1, 1);
```

After the `groups` CREATE TABLE:
```python
INSERT INTO groups VALUES (99999, 2, 'Lab Group', '', 1);
```

Then add a group item after all existing items:

```python
# Item 9: Group library item
c.execute("INSERT INTO items VALUES (9, 2, '2024-06-01', '2024-06-02', '2024-06-02', 2, 'GRPITM09')")
c.execute("INSERT INTO itemDataValues VALUES (19, 'Group Paper on Protein Folding')")
c.execute("INSERT INTO itemDataValues VALUES (20, '2024')")
c.execute("INSERT INTO itemData VALUES (9, 4, 19)")  # title
c.execute("INSERT INTO itemData VALUES (9, 14, 20)")  # date
c.execute("INSERT INTO creators VALUES (7, 'Alice', 'Wong')")
c.execute("INSERT INTO itemCreators VALUES (9, 7, 1, 0)")

# Group collection
c.execute("INSERT INTO collections VALUES (3, 'Group Papers', NULL, 2, 'GRPCOL03')")
c.execute("INSERT INTO collectionItems VALUES (3, 9, 0)")
```

Run: `python tests/fixtures/create_test_db.py`

- [ ] **Step 2: Write failing tests**

Create `tests/test_group_library.py`:

```python
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

    def test_search_default_excludes_group_items(self):
        reader = ZoteroReader(FIXTURES_DIR / "zotero.sqlite")
        try:
            result = reader.search("")
            keys = [i.key for i in result.items]
            assert "GRPITM09" not in keys
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
        assert result.exit_code != 0 or "Invalid" in result.output
```

Run: `pytest tests/test_group_library.py -v`
Expected: FAIL.

- [ ] **Step 3: Add `library_id` to `ZoteroReader.__init__` and `resolve_group_library_id`**

In `src/zotero_cli_cc/core/reader.py`, modify `__init__`:

```python
def __init__(self, db_path: Path, library_id: int = 1) -> None:
    self._db_path = db_path
    self._library_id = library_id
    self._conn: sqlite3.Connection | None = None
    self._tmp_dir: Path | None = None
    self._excluded_sql: str | None = None
    self._excluded_ids: tuple[int, ...] | None = None
    self._tmp_dir_obj: tempfile.TemporaryDirectory[str] | None = None
```

Add `resolve_group_library_id` method:

```python
def resolve_group_library_id(self, group_id: int) -> int | None:
    """Look up the SQLite libraryID for a Zotero group by its public groupID."""
    conn = self._connect()
    row = conn.execute(
        "SELECT libraryID FROM groups WHERE groupID = ?",
        (group_id,),
    ).fetchone()
    return row["libraryID"] if row else None
```

Add a private helper for library filtering:

```python
def _library_filter(self) -> tuple[str, tuple[int, ...]]:
    """Return (SQL fragment, params) for filtering by library.
    Returns empty string/tuple for library_id=1 to preserve existing behavior."""
    if self._library_id == 1:
        return "", ()
    return "AND i.libraryID = ?", (self._library_id,)
```

- [ ] **Step 4: Add `libraryID` filter to all item queries**

Modify `get_item()` — add library filter to the WHERE clause:

```python
def get_item(self, key: str) -> Item | None:
    conn = self._connect()
    lib_sql, lib_params = self._library_filter()
    row = conn.execute(
        "SELECT itemID, itemTypeID, key, dateAdded, dateModified "
        "FROM items i WHERE key = ? AND itemTypeID " + self._get_excluded_sql() + " " + lib_sql,
        (key, *lib_params),
    ).fetchone()
    # ... rest unchanged
```

Similarly update `search()`, `get_recent_items()`, `get_trash_items()`, `get_stats()`, `get_collection_items()`, `get_collections()`, and `find_duplicates()`. The pattern is the same: add `lib_sql, lib_params = self._library_filter()` and append `lib_sql` to WHERE clause with `*lib_params` in the params tuple.

For `get_collections()`:
```python
def get_collections(self) -> list[Collection]:
    conn = self._connect()
    rows = conn.execute(
        "SELECT collectionID, collectionName, parentCollectionID, key "
        "FROM collections WHERE libraryID = ?",
        (self._library_id,),
    ).fetchall()
    # ... rest unchanged
```

For `_get_items_batch()` — add library filter to the base item rows query:
```python
lib_sql, lib_params = self._library_filter()
rows = conn.execute(
    f"SELECT itemID, itemTypeID, key, dateAdded, dateModified "
    f"FROM items i WHERE itemID IN ({placeholders}) AND itemTypeID {self._get_excluded_sql()} {lib_sql}",
    (*item_ids, *lib_params),
).fetchall()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_group_library.py::TestGroupReader -v`
Expected: All PASS.

Run: `pytest tests/ -v --tb=short`
Expected: All existing tests still pass (library_id defaults to 1, same as before).

- [ ] **Step 6: Commit**

```bash
ruff check src/zotero_cli_cc/core/reader.py --fix && ruff format src/zotero_cli_cc/core/reader.py
git add src/zotero_cli_cc/core/reader.py tests/fixtures/create_test_db.py tests/fixtures/zotero.sqlite tests/test_group_library.py
git commit -m "feat(group): add library_id filtering to reader for group library support"
```

---

### Task 8: Group Library Support — CLI, Writer & MCP

**Files:**
- Modify: `src/zotero_cli_cc/cli.py`
- Modify: `src/zotero_cli_cc/core/writer.py`
- Modify: `src/zotero_cli_cc/mcp_server.py`
- Modify: all command files that create a reader or writer
- Modify: `tests/test_group_library.py`

**Context:** The `--library` option is parsed in `cli.py`'s `main()` and stored in `ctx.obj`. Every command that creates a `ZoteroReader` must pass `library_id`. Every command that creates a `ZoteroWriter` must pass `library_type`. The MCP server helpers `_get_reader()` and `_get_writer()` need a `library` parameter.

- [ ] **Step 1: Add `--library` option to CLI and parse it**

In `src/zotero_cli_cc/cli.py`, add option to `main`:

```python
@click.option("--library", default="user", help="Library: 'user' (default) or 'group:<id>'")
```

Update function signature to include `library: str`. Add parsing logic in `main()`:

```python
# Parse --library option
if library == "user":
    ctx.obj["library_type"] = "user"
    ctx.obj["group_id"] = None
elif library.startswith("group:"):
    group_part = library[6:]
    if not group_part.isdigit():
        raise click.BadParameter(f"Invalid --library format: '{library}'. Use 'user' or 'group:<id>'")
    ctx.obj["library_type"] = "group"
    ctx.obj["group_id"] = group_part
else:
    raise click.BadParameter(f"Invalid --library format: '{library}'. Use 'user' or 'group:<id>'")
```

- [ ] **Step 2: Update `ZoteroWriter` to accept `library_type`**

In `src/zotero_cli_cc/core/writer.py`, modify `__init__`:

```python
def __init__(self, library_id: str, api_key: str, library_type: str = "user", timeout: float = API_TIMEOUT) -> None:
    self._zot = zotero.Zotero(library_id, library_type, api_key)
    if self._zot.client is not None:
        self._zot.client.timeout = httpx.Timeout(timeout)
```

- [ ] **Step 3: Create helper functions for reader/writer creation in commands**

Rather than updating every individual command file, add two helpers to the config or a new utility. The cleanest approach: update each command to pass the library context. Since each command already gets `ctx.obj`, add a pattern:

For **reader commands** (e.g., `search.py`), change the reader creation from:
```python
reader = ZoteroReader(db_path)
```
to:
```python
library_id = 1
if ctx.obj.get("library_type") == "group" and ctx.obj.get("group_id"):
    temp_reader = ZoteroReader(db_path)
    try:
        resolved = temp_reader.resolve_group_library_id(int(ctx.obj["group_id"]))
        if resolved is None:
            click.echo(format_error(ErrorInfo(message=f"Group {ctx.obj['group_id']} not found")))
            return
        library_id = resolved
    finally:
        temp_reader.close()
reader = ZoteroReader(db_path, library_id=library_id)
```

This is verbose. Better: add a helper in `config.py`:

```python
def resolve_library_id(db_path: Path, ctx_obj: dict) -> int:
    """Resolve the library_id from ctx.obj, defaulting to 1 (user library)."""
    if ctx_obj.get("library_type") != "group" or not ctx_obj.get("group_id"):
        return 1
    from zotero_cli_cc.core.reader import ZoteroReader
    reader = ZoteroReader(db_path)
    try:
        resolved = reader.resolve_group_library_id(int(ctx_obj["group_id"]))
    finally:
        reader.close()
    if resolved is None:
        raise click.ClickException(f"Group '{ctx_obj['group_id']}' not found in local database")
    return resolved
```

Then in each reader command:
```python
from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
# ...
library_id = resolve_library_id(db_path, ctx.obj)
reader = ZoteroReader(db_path, library_id=library_id)
```

For **writer commands**, update writer creation:
```python
library_type = ctx.obj.get("library_type", "user")
writer_lib_id = ctx.obj.get("group_id") if library_type == "group" else library_id
writer = ZoteroWriter(library_id=writer_lib_id, api_key=api_key, library_type=library_type)
```

Apply this change to ALL command files listed in the spec:
- Reader commands: `search.py`, `list_cmd.py`, `read.py`, `recent.py`, `pdf.py`, `summarize.py`, `summarize_all.py`, `stats.py`, `export.py`, `cite.py`, `relate.py`, `open_cmd.py`, `note.py`, `tag.py`, `collection.py`, `duplicates.py`, `trash.py`
- Writer commands: `add.py`, `delete.py`, `update.py`, `note.py`, `tag.py`, `collection.py`, `attach.py`, `trash.py`

- [ ] **Step 4: Update MCP server**

In `src/zotero_cli_cc/mcp_server.py`, update `_get_reader()` and `_get_writer()`:

```python
_readers: dict[int, ZoteroReader] = {}


def _get_reader(library: str = "user") -> ZoteroReader:
    """Return a shared ZoteroReader, creating it on first use."""
    cfg = load_config()
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"

    library_id = 1
    if library.startswith("group:"):
        group_id = int(library[6:])
        temp = ZoteroReader(db_path)
        try:
            resolved = temp.resolve_group_library_id(group_id)
        finally:
            temp.close()
        if resolved is None:
            raise ValueError(f"Group '{group_id}' not found")
        library_id = resolved

    if library_id not in _readers:
        reader = ZoteroReader(db_path, library_id=library_id)
        _readers[library_id] = reader
        atexit.register(reader.close)
    return _readers[library_id]


def _get_writer(library: str = "user") -> ZoteroWriter:
    cfg = load_config()
    if not cfg.has_write_credentials:
        raise ValueError("Write credentials not configured.")
    library_type = "user"
    lib_id = cfg.library_id
    if library.startswith("group:"):
        library_type = "group"
        lib_id = library[6:]
    return ZoteroWriter(lib_id, cfg.api_key, library_type=library_type)
```

Update the `_reader` global to `_readers` dict. Remove old `_reader` variable.

Add `library: str = "user"` parameter to all MCP handler functions and pass through to `_get_reader(library)` / `_get_writer(library)`. Add `library: str = "user"` parameter to all `@mcp.tool()` definitions with appropriate docstring.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_group_library.py -v`
Expected: All PASS.

Run: `pytest tests/ -v --tb=short`
Expected: No regressions (default library_id=1 matches existing behavior).

```bash
ruff check src/ --fix && ruff format src/
git add -u src/ tests/
git commit -m "feat(group): add --library option for group library support across all commands and MCP tools"
```

---

## Post-Implementation

After all 8 tasks are complete:

1. Run full test suite: `pytest tests/ -v`
2. Run linter: `ruff check src/ tests/`
3. Verify with live library: `zot trash list`, `zot duplicates`, `zot attach`, `zot add --pdf`, `zot --library group:ID search ""`
4. Update `CHANGELOG.md` with v0.1.6 entry
5. Update `README.md` roadmap to mark Tier 2 complete
