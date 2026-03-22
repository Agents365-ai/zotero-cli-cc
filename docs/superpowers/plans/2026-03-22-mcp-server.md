# MCP Server Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MCP server support to zotero-cli-cc so it can be used from LM Studio, Claude Desktop, Cursor, and other MCP clients.

**Architecture:** A thin MCP server module (`mcp_server.py`) wraps existing `ZoteroReader`, `ZoteroWriter`, `PdfExtractor`, and `PdfCache`. Uses FastMCP from the official `mcp` Python SDK with stdio transport. Launched via `zot mcp serve` subcommand.

**Tech Stack:** `mcp` Python SDK (FastMCP), Click CLI, existing zotero-cli-cc core modules.

**Spec:** `docs/superpowers/specs/2026-03-22-mcp-server-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/zotero_cli_cc/mcp_server.py` | Create | FastMCP server with all 17 tool handlers |
| `src/zotero_cli_cc/commands/mcp.py` | Create | `zot mcp serve` CLI subcommand |
| `src/zotero_cli_cc/cli.py` | Modify | Register `mcp` command group |
| `pyproject.toml` | Modify | Add `mcp` optional dependency |
| `tests/test_mcp_server.py` | Create | Unit tests for all tool handlers |
| `README.md` | Modify | Add MCP usage section |
| `README_EN.md` | Modify | Add MCP usage section (English) |

---

### Task 1: Add `mcp` optional dependency

**Files:**
- Modify: `pyproject.toml:16-20`

- [ ] **Step 1: Add mcp to optional dependencies in pyproject.toml**

Add `mcp` optional dependency group:

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.0"]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]
```

- [ ] **Step 2: Install the mcp extra locally**

Run: `uv pip install -e ".[mcp]"`
Expected: Successfully installs `mcp` package

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add mcp optional dependency for MCP server support"
```

---

### Task 2: Create MCP server with read-only tools

**Files:**
- Create: `src/zotero_cli_cc/mcp_server.py`
- Create: `tests/test_mcp_server.py`

This task implements the 11 read-only tools: `search`, `list_items`, `read`, `pdf`, `summarize`, `export`, `relate`, `note_view`, `tag_view`, `collection_list`, `collection_items`.

- [ ] **Step 1: Write failing tests for read-only tools**

Create `tests/test_mcp_server.py`:

```python
"""Tests for MCP server tool handlers."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import asdict

from zotero_cli_cc.models import Item, Creator, Note, Collection, SearchResult


def _make_item(key: str = "ABC123", title: str = "Test Paper") -> Item:
    return Item(
        key=key,
        item_type="journalArticle",
        title=title,
        creators=[Creator("Jane", "Doe", "author")],
        abstract="Test abstract",
        date="2025",
        url="https://example.com",
        doi="10.1234/test",
        tags=["ml", "ai"],
        collections=["COL1"],
        date_added="2025-01-01",
        date_modified="2025-06-01",
    )


def _make_note(key: str = "NOTE1", parent: str = "ABC123") -> Note:
    return Note(key=key, parent_key=parent, content="Test note content", tags=["important"])


def _make_collection(key: str = "COL1", name: str = "ML Papers") -> Collection:
    return Collection(key=key, name=name, parent_key=None, children=[])


class TestItemToDict:
    """Test the item serialization helper."""

    def test_item_to_dict_has_required_fields(self):
        from zotero_cli_cc.mcp_server import _item_to_dict
        item = _make_item()
        d = _item_to_dict(item)
        assert d["key"] == "ABC123"
        assert d["title"] == "Test Paper"
        assert d["authors"] == ["Jane Doe"]
        assert d["doi"] == "10.1234/test"

    def test_item_to_dict_minimal(self):
        from zotero_cli_cc.mcp_server import _item_to_dict
        item = _make_item()
        d = _item_to_dict(item, detail="minimal")
        assert "abstract" not in d
        assert "tags" not in d


class TestSearchTool:
    """Test the search tool handler."""

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_search_returns_items(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_search
        reader = MagicMock()
        reader.search.return_value = SearchResult(
            items=[_make_item()], total=1, query="test"
        )
        mock_get_reader.return_value = reader

        result = _handle_search("test", None, 50)
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "Test Paper"
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_search_empty_results(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_search
        reader = MagicMock()
        reader.search.return_value = SearchResult(items=[], total=0, query="none")
        mock_get_reader.return_value = reader

        result = _handle_search("none", None, 50)
        assert result["total"] == 0
        assert result["items"] == []


class TestReadTool:
    """Test the read tool handler."""

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_read_returns_item_with_notes(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_read
        reader = MagicMock()
        reader.get_item.return_value = _make_item()
        reader.get_notes.return_value = [_make_note()]
        mock_get_reader.return_value = reader

        result = _handle_read("ABC123", "standard")
        assert result["item"]["key"] == "ABC123"
        assert len(result["notes"]) == 1
        assert result["notes"][0]["content"] == "Test note content"

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_read_item_not_found(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_read
        reader = MagicMock()
        reader.get_item.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_read("NOTEXIST", "standard")


class TestNoteViewTool:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_note_view_returns_notes(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_note_view
        reader = MagicMock()
        reader.get_notes.return_value = [_make_note()]
        mock_get_reader.return_value = reader

        result = _handle_note_view("ABC123")
        assert len(result["notes"]) == 1


class TestTagViewTool:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_tag_view_returns_tags(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_tag_view
        reader = MagicMock()
        reader.get_item.return_value = _make_item()
        mock_get_reader.return_value = reader

        result = _handle_tag_view("ABC123")
        assert result["tags"] == ["ml", "ai"]


class TestCollectionListTool:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_collection_list(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_collection_list
        reader = MagicMock()
        reader.get_collections.return_value = [_make_collection()]
        mock_get_reader.return_value = reader

        result = _handle_collection_list()
        assert len(result["collections"]) == 1
        assert result["collections"][0]["name"] == "ML Papers"


class TestCollectionItemsTool:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_collection_items(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_collection_items
        reader = MagicMock()
        reader.get_collection_items.return_value = [_make_item()]
        mock_get_reader.return_value = reader

        result = _handle_collection_items("COL1")
        assert len(result["items"]) == 1


class TestExportTool:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_export_bibtex(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_export
        reader = MagicMock()
        reader.export_citation.return_value = "@article{abc123, ...}"
        mock_get_reader.return_value = reader

        result = _handle_export("ABC123", "bibtex")
        assert result["citation"] == "@article{abc123, ...}"
        assert result["format"] == "bibtex"

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_export_not_found(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_export
        reader = MagicMock()
        reader.export_citation.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_export("NOTEXIST", "bibtex")


class TestRelateTool:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_relate_returns_items(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_relate
        reader = MagicMock()
        reader.get_related_items.return_value = [_make_item("REL1", "Related Paper")]
        mock_get_reader.return_value = reader

        result = _handle_relate("ABC123", 20)
        assert len(result["items"]) == 1
        assert result["items"][0]["key"] == "REL1"


class TestSummarizeTool:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_summarize_returns_structured_data(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_summarize
        reader = MagicMock()
        reader.get_item.return_value = _make_item()
        reader.get_notes.return_value = [_make_note()]
        mock_get_reader.return_value = reader

        result = _handle_summarize("ABC123")
        assert result["title"] == "Test Paper"
        assert result["authors"] == ["Jane Doe"]
        assert result["doi"] == "10.1234/test"

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_summarize_not_found(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_summarize
        reader = MagicMock()
        reader.get_item.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_summarize("NOTEXIST")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_server.py -v`
Expected: FAIL — `mcp_server` module does not exist yet

- [ ] **Step 3: Implement mcp_server.py with read-only tools**

Create `src/zotero_cli_cc/mcp_server.py`:

```python
"""MCP server for zotero-cli-cc — exposes Zotero tools via Model Context Protocol."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.models import Collection, Item, Note

mcp = FastMCP(
    "zotero",
    description="Access your Zotero library — search, read, extract PDFs, export citations, and manage items.",
)


# --- Helpers ---

def _get_reader() -> ZoteroReader:
    """Create a ZoteroReader from current config."""
    cfg = load_config()
    data_dir = get_data_dir(cfg)
    return ZoteroReader(data_dir / "zotero.sqlite")


def _item_to_dict(item: Item, detail: str = "standard") -> dict:
    """Convert Item to JSON-serializable dict."""
    d: dict = {
        "key": item.key,
        "item_type": item.item_type,
        "title": item.title,
        "authors": [c.full_name for c in item.creators],
        "date": item.date,
    }
    if detail != "minimal":
        d["abstract"] = item.abstract
        d["url"] = item.url
        d["doi"] = item.doi
        d["tags"] = item.tags
        d["collections"] = item.collections
        d["date_added"] = item.date_added
        d["date_modified"] = item.date_modified
    if detail == "full":
        d["extra"] = item.extra
    return d


def _note_to_dict(note: Note) -> dict:
    return {"key": note.key, "parent_key": note.parent_key, "content": note.content, "tags": note.tags}


def _collection_to_dict(col: Collection) -> dict:
    return {
        "key": col.key,
        "name": col.name,
        "parent_key": col.parent_key,
        "children": [_collection_to_dict(c) for c in col.children],
    }


# --- Read-only tool handlers (testable without MCP decorator) ---

def _handle_search(query: str, collection: str | None, limit: int) -> dict:
    reader = _get_reader()
    try:
        result = reader.search(query, collection=collection, limit=limit)
        return {"items": [_item_to_dict(i) for i in result.items], "total": result.total, "query": result.query}
    finally:
        reader.close()


def _handle_list_items(collection: str | None, limit: int) -> dict:
    reader = _get_reader()
    try:
        result = reader.search("", collection=collection, limit=limit)
        return {"items": [_item_to_dict(i) for i in result.items], "total": result.total}
    finally:
        reader.close()


def _handle_read(key: str, detail: str) -> dict:
    reader = _get_reader()
    try:
        item = reader.get_item(key)
        if item is None:
            raise ValueError(f"Item '{key}' not found. Use the search tool to find valid item keys.")
        notes = reader.get_notes(key)
        return {"item": _item_to_dict(item, detail=detail), "notes": [_note_to_dict(n) for n in notes]}
    finally:
        reader.close()


def _handle_pdf(key: str, pages: str | None) -> dict:
    from zotero_cli_cc.core.pdf_extractor import extract_text_from_pdf
    from zotero_cli_cc.core.pdf_cache import PdfCache

    cfg = load_config()
    data_dir = get_data_dir(cfg)
    reader = ZoteroReader(data_dir / "zotero.sqlite")
    try:
        att = reader.get_pdf_attachment(key)
        if att is None:
            raise ValueError(f"No PDF attachment found for '{key}'. Use the read tool to check item details.")
        pdf_path = data_dir / "storage" / att.key / att.filename
        if not pdf_path.exists():
            raise ValueError(f"PDF file not found at {pdf_path}.")

        page_range = None
        if pages:
            parts = pages.split("-")
            start = int(parts[0])
            end = int(parts[1]) if len(parts) > 1 else start
            page_range = (start, end)

        cache = PdfCache()
        try:
            if page_range is None:
                cached = cache.get(pdf_path)
                if cached is not None:
                    text = cached
                else:
                    text = extract_text_from_pdf(pdf_path)
                    cache.put(pdf_path, text)
            else:
                text = extract_text_from_pdf(pdf_path, pages=page_range)
        finally:
            cache.close()

        return {"key": key, "pages": pages, "text": text}
    finally:
        reader.close()


def _handle_summarize(key: str) -> dict:
    reader = _get_reader()
    try:
        item = reader.get_item(key)
        if item is None:
            raise ValueError(f"Item '{key}' not found. Use the search tool to find valid item keys.")
        notes = reader.get_notes(key)
        return {
            "title": item.title,
            "authors": [c.full_name for c in item.creators],
            "year": item.date,
            "doi": item.doi,
            "abstract": item.abstract,
            "tags": item.tags,
            "notes": [n.content[:500] for n in notes],
        }
    finally:
        reader.close()


def _handle_export(key: str, fmt: str) -> dict:
    reader = _get_reader()
    try:
        citation = reader.export_citation(key, fmt=fmt)
        if citation is None:
            raise ValueError(f"Item '{key}' not found or format '{fmt}' not supported.")
        return {"citation": citation, "format": fmt}
    finally:
        reader.close()


def _handle_relate(key: str, limit: int) -> dict:
    reader = _get_reader()
    try:
        items = reader.get_related_items(key, limit=limit)
        return {"items": [_item_to_dict(i) for i in items]}
    finally:
        reader.close()


def _handle_note_view(key: str) -> dict:
    reader = _get_reader()
    try:
        notes = reader.get_notes(key)
        return {"notes": [_note_to_dict(n) for n in notes]}
    finally:
        reader.close()


def _handle_tag_view(key: str) -> dict:
    reader = _get_reader()
    try:
        item = reader.get_item(key)
        if item is None:
            raise ValueError(f"Item '{key}' not found.")
        return {"tags": item.tags}
    finally:
        reader.close()


def _handle_collection_list() -> dict:
    reader = _get_reader()
    try:
        collections = reader.get_collections()
        return {"collections": [_collection_to_dict(c) for c in collections]}
    finally:
        reader.close()


def _handle_collection_items(key: str) -> dict:
    reader = _get_reader()
    try:
        items = reader.get_collection_items(key)
        return {"items": [_item_to_dict(i) for i in items]}
    finally:
        reader.close()


# --- MCP tool registrations ---

@mcp.tool()
def search(query: str, collection: str | None = None, limit: int = 50) -> dict:
    """Search the Zotero library across titles, abstracts, authors, tags, and full-text.

    Args:
        query: Search query string
        collection: Optional collection name to filter by
        limit: Maximum number of results (default 50)
    """
    return _handle_search(query, collection, limit)


@mcp.tool()
def list_items(collection: str | None = None, limit: int = 50) -> dict:
    """List all items in the Zotero library.

    Args:
        collection: Optional collection name to filter by
        limit: Maximum number of results (default 50)
    """
    return _handle_list_items(collection, limit)


@mcp.tool()
def read(key: str, detail: str = "standard") -> dict:
    """View item details including metadata and notes.

    Args:
        key: Zotero item key (e.g. 'ABC123')
        detail: Detail level — 'minimal', 'standard', or 'full'
    """
    return _handle_read(key, detail)


@mcp.tool()
def pdf(key: str, pages: str | None = None) -> dict:
    """Extract text from a PDF attachment.

    Args:
        key: Zotero item key
        pages: Optional page range (e.g. '1-5' or '3')
    """
    return _handle_pdf(key, pages)


@mcp.tool()
def summarize(key: str) -> dict:
    """Get a structured summary of an item (title, authors, year, DOI, abstract, tags, notes).

    Args:
        key: Zotero item key
    """
    return _handle_summarize(key)


@mcp.tool()
def export(key: str, format: str = "bibtex") -> dict:
    """Export an item as a citation.

    Args:
        key: Zotero item key
        format: Citation format — 'bibtex' (default) or 'json'
    """
    return _handle_export(key, format)


@mcp.tool()
def relate(key: str, limit: int = 20) -> dict:
    """Find items related to the given item by relations, shared collections, and shared tags.

    Args:
        key: Zotero item key
        limit: Maximum number of related items (default 20)
    """
    return _handle_relate(key, limit)


@mcp.tool()
def note_view(key: str) -> dict:
    """View all notes for a Zotero item.

    Args:
        key: Zotero item key
    """
    return _handle_note_view(key)


@mcp.tool()
def tag_view(key: str) -> dict:
    """View all tags for a Zotero item.

    Args:
        key: Zotero item key
    """
    return _handle_tag_view(key)


@mcp.tool()
def collection_list() -> dict:
    """List all collections in the Zotero library as a tree."""
    return _handle_collection_list()


@mcp.tool()
def collection_items(key: str) -> dict:
    """List all items in a specific collection.

    Args:
        key: Collection key
    """
    return _handle_collection_items(key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mcp_server.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/zotero_cli_cc/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add MCP server with read-only tools

Implements 11 read-only MCP tools: search, list_items, read, pdf,
summarize, export, relate, note_view, tag_view, collection_list,
collection_items. Uses FastMCP with testable handler functions."
```

---

### Task 3: Add write tools to MCP server

**Files:**
- Modify: `src/zotero_cli_cc/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

This task adds the 6 write tools: `note_add`, `tag_add`, `tag_remove`, `add`, `delete`, `collection_create`.

- [ ] **Step 1: Write failing tests for write tools**

Append to `tests/test_mcp_server.py`:

```python
class TestNoteAddTool:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_note_add_returns_key(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_note_add
        writer = MagicMock()
        writer.add_note.return_value = "NOTE2"
        mock_get_writer.return_value = writer

        result = _handle_note_add("ABC123", "New note content")
        assert result["note_key"] == "NOTE2"
        writer.add_note.assert_called_once_with("ABC123", "New note content")

    def test_note_add_no_credentials(self):
        from zotero_cli_cc.mcp_server import _handle_note_add
        with patch("zotero_cli_cc.mcp_server._get_writer", side_effect=ValueError("No API credentials")):
            with pytest.raises(ValueError, match="credentials"):
                _handle_note_add("ABC123", "content")


class TestTagAddTool:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_tag_add(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_tag_add
        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_tag_add("ABC123", ["new-tag"])
        assert result["success"] is True
        writer.add_tags.assert_called_once_with("ABC123", ["new-tag"])


class TestTagRemoveTool:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_tag_remove(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_tag_remove
        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_tag_remove("ABC123", ["old-tag"])
        assert result["success"] is True
        writer.remove_tags.assert_called_once_with("ABC123", ["old-tag"])


class TestAddItemTool:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_add_by_doi(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_add
        writer = MagicMock()
        writer.add_item.return_value = "NEW1"
        mock_get_writer.return_value = writer

        result = _handle_add(doi="10.1234/test", url=None)
        assert result["item_key"] == "NEW1"

    def test_add_no_doi_no_url(self):
        from zotero_cli_cc.mcp_server import _handle_add
        with pytest.raises(ValueError, match="Either doi or url"):
            _handle_add(doi=None, url=None)


class TestDeleteItemTool:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_delete(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_delete
        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_delete("ABC123")
        assert result["success"] is True
        writer.delete_item.assert_called_once_with("ABC123")


class TestCollectionCreateTool:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_collection_create(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_collection_create
        writer = MagicMock()
        writer.create_collection.return_value = "NEWCOL1"
        mock_get_writer.return_value = writer

        result = _handle_collection_create("New Collection", None)
        assert result["collection_key"] == "NEWCOL1"
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `pytest tests/test_mcp_server.py -v -k "Add or Remove or Delete or Create or note_add"`
Expected: FAIL — `_get_writer` and `_handle_*` functions not yet defined

- [ ] **Step 3: Implement write tool handlers and MCP registrations**

Add to `src/zotero_cli_cc/mcp_server.py`:

```python
# Add import at top:
from zotero_cli_cc.core.writer import ZoteroWriter, ZoteroWriteError

# Add helper:
def _get_writer() -> ZoteroWriter:
    """Create a ZoteroWriter from current config."""
    cfg = load_config()
    if not cfg.has_write_credentials:
        raise ValueError(
            "No API credentials configured. "
            "Run 'zot config init --library-id YOUR_ID --api-key YOUR_KEY' to set up write access."
        )
    return ZoteroWriter(cfg.library_id, cfg.api_key)

# Add handlers:
def _handle_note_add(key: str, content: str) -> dict:
    writer = _get_writer()
    note_key = writer.add_note(key, content)
    return {"note_key": note_key}

def _handle_tag_add(key: str, tags: list[str]) -> dict:
    writer = _get_writer()
    writer.add_tags(key, tags)
    return {"success": True}

def _handle_tag_remove(key: str, tags: list[str]) -> dict:
    writer = _get_writer()
    writer.remove_tags(key, tags)
    return {"success": True}

def _handle_add(doi: str | None, url: str | None) -> dict:
    if not doi and not url:
        raise ValueError("Either doi or url must be provided.")
    writer = _get_writer()
    item_key = writer.add_item(doi=doi, url=url)
    return {"item_key": item_key}

def _handle_delete(key: str) -> dict:
    writer = _get_writer()
    writer.delete_item(key)
    return {"success": True}

def _handle_collection_create(name: str, parent: str | None) -> dict:
    writer = _get_writer()
    collection_key = writer.create_collection(name, parent_key=parent)
    return {"collection_key": collection_key}

# Add MCP tool registrations:
@mcp.tool()
def note_add(key: str, content: str) -> dict:
    """Add a new note to a Zotero item. Requires API credentials.

    Args:
        key: Zotero item key
        content: Note content (plain text or HTML)
    """
    return _handle_note_add(key, content)

@mcp.tool()
def tag_add(key: str, tags: list[str]) -> dict:
    """Add tags to a Zotero item. Requires API credentials.

    Args:
        key: Zotero item key
        tags: List of tags to add
    """
    return _handle_tag_add(key, tags)

@mcp.tool()
def tag_remove(key: str, tags: list[str]) -> dict:
    """Remove tags from a Zotero item. Requires API credentials.

    Args:
        key: Zotero item key
        tags: List of tags to remove
    """
    return _handle_tag_remove(key, tags)

@mcp.tool()
def add(doi: str | None = None, url: str | None = None) -> dict:
    """Add a new item to Zotero by DOI or URL. Requires API credentials.

    Args:
        doi: DOI (e.g. '10.1038/s41586-023-06139-9')
        url: URL (e.g. 'https://arxiv.org/abs/2301.00001')
    """
    return _handle_add(doi, url)

@mcp.tool()
def delete(key: str) -> dict:
    """Delete (move to trash) a Zotero item. Requires API credentials.

    Args:
        key: Zotero item key
    """
    return _handle_delete(key)

@mcp.tool()
def collection_create(name: str, parent: str | None = None) -> dict:
    """Create a new Zotero collection. Requires API credentials.

    Args:
        name: Collection name
        parent: Optional parent collection key
    """
    return _handle_collection_create(name, parent)
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `pytest tests/test_mcp_server.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/zotero_cli_cc/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add write tools to MCP server

Adds 6 write tools: note_add, tag_add, tag_remove, add, delete,
collection_create. All require API credentials with clear error
messages when not configured."
```

---

### Task 4: Add `zot mcp serve` CLI subcommand

**Files:**
- Create: `src/zotero_cli_cc/commands/mcp.py`
- Modify: `src/zotero_cli_cc/cli.py:7-8,43-55`

- [ ] **Step 1: Create the mcp command module**

Create `src/zotero_cli_cc/commands/mcp.py`:

```python
"""MCP server CLI commands."""
from __future__ import annotations

import click


@click.group("mcp")
def mcp_group() -> None:
    """MCP server commands."""
    pass


@mcp_group.command("serve")
def serve_cmd() -> None:
    """Start MCP server on stdio for use with LM Studio, Claude Desktop, etc."""
    try:
        from zotero_cli_cc.mcp_server import mcp as mcp_server
    except ImportError:
        click.echo(
            "Error: MCP support not installed.\n"
            "Install with: pip install zotero-cli-cc[mcp]",
            err=True,
        )
        raise SystemExit(1)
    mcp_server.run(transport="stdio")
```

- [ ] **Step 2: Register mcp command in cli.py**

Add import and registration in `src/zotero_cli_cc/cli.py`:

```python
# Add import:
from zotero_cli_cc.commands.mcp import mcp_group

# Add registration after existing commands:
main.add_command(mcp_group, "mcp")
```

- [ ] **Step 3: Verify the command shows up in help**

Run: `zot mcp --help`
Expected: Shows `serve` subcommand

Run: `zot mcp serve --help`
Expected: Shows description about starting MCP server

- [ ] **Step 4: Commit**

```bash
git add src/zotero_cli_cc/commands/mcp.py src/zotero_cli_cc/cli.py
git commit -m "feat: add 'zot mcp serve' CLI subcommand

Registers MCP server as a CLI subcommand. Gracefully handles
missing mcp dependency with install instructions."
```

---

### Task 5: Update documentation

**Files:**
- Modify: `README.md`
- Modify: `README_EN.md`

- [ ] **Step 1: Add MCP section to Chinese README**

Add after the installation section in `README.md`:

```markdown
### MCP 服务器模式

zotero-cli-cc 支持 [MCP (Model Context Protocol)](https://modelcontextprotocol.io/)，可在 LM Studio、Claude Desktop、Cursor 等支持 MCP 的客户端中使用。

**安装 MCP 支持：**

```bash
pip install zotero-cli-cc[mcp]
```

**启动 MCP 服务器：**

```bash
zot mcp serve
```

**客户端配置（LM Studio / Claude Desktop / Cursor）：**

```json
{
  "mcpServers": {
    "zotero": {
      "command": "zot",
      "args": ["mcp", "serve"]
    }
  }
}
```

MCP 模式提供 17 个工具，涵盖搜索、阅读、PDF 提取、笔记管理、标签管理、导出引用等完整功能。
```

- [ ] **Step 2: Add MCP section to English README**

Add the equivalent section to `README_EN.md`.

- [ ] **Step 3: Commit**

```bash
git add README.md README_EN.md
git commit -m "docs: add MCP server usage instructions to README"
```

---

### Task 6: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS (both existing CLI tests and new MCP tests)

- [ ] **Step 2: Verify MCP server starts**

Run: `echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' | timeout 5 zot mcp serve 2>/dev/null || true`
Expected: JSON-RPC response with server capabilities

- [ ] **Step 3: Verify help output**

Run: `zot --help`
Expected: Shows `mcp` in command list

Run: `zot mcp serve --help`
Expected: Shows description
