"""MCP server exposing Zotero tools via FastMCP."""

from __future__ import annotations

import atexit

from mcp.server.fastmcp import FastMCP

from zotero_cli_cc.config import get_data_dir, load_config
from zotero_cli_cc.core.pdf_cache import PdfCache
from zotero_cli_cc.core.pdf_extractor import PdfExtractionError, extract_text_from_pdf
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.models import Collection, Item, Note

mcp = FastMCP("zotero", instructions="Read and write access to a local Zotero library")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_reader: ZoteroReader | None = None


def _get_reader() -> ZoteroReader:
    """Return a shared ZoteroReader, creating it on first use."""
    global _reader
    if _reader is None:
        cfg = load_config()
        data_dir = get_data_dir(cfg)
        _reader = ZoteroReader(data_dir / "zotero.sqlite")
        atexit.register(_reader.close)
    return _reader


def _get_writer() -> ZoteroWriter:
    """Create a ZoteroWriter from the user's config.

    Raises ValueError if write credentials are not configured.
    """
    cfg = load_config()
    if not cfg.has_write_credentials:
        raise ValueError("Write credentials not configured. Set library_id and api_key in your Zotero CLI config.")
    return ZoteroWriter(cfg.library_id, cfg.api_key)


def _item_to_dict(item: Item, detail: str = "standard") -> dict:
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
    return {
        "key": note.key,
        "parent_key": note.parent_key,
        "content": note.content,
        "tags": note.tags,
    }


def _collection_to_dict(coll: Collection) -> dict:
    return {
        "key": coll.key,
        "name": coll.name,
        "parent_key": coll.parent_key,
        "children": [_collection_to_dict(c) for c in coll.children],
    }


# ---------------------------------------------------------------------------
# Handler functions (testable without MCP decorator)
# ---------------------------------------------------------------------------


def _handle_search(
    query: str,
    collection: str | None,
    limit: int,
    item_type: str | None = None,
    sort: str | None = None,
    direction: str = "desc",
) -> dict:
    reader = _get_reader()
    result = reader.search(
        query, collection=collection, item_type=item_type, sort=sort, direction=direction, limit=limit
    )
    return {
        "items": [_item_to_dict(i) for i in result.items],
        "total": result.total,
        "query": result.query,
    }


def _handle_list_items(
    limit: int,
    item_type: str | None = None,
    sort: str | None = None,
    direction: str = "desc",
) -> dict:
    reader = _get_reader()
    result = reader.search("", collection=None, item_type=item_type, sort=sort, direction=direction, limit=limit)
    return {
        "items": [_item_to_dict(i) for i in result.items],
        "total": result.total,
    }


def _handle_read(key: str, detail: str = "standard") -> dict:
    reader = _get_reader()
    item = reader.get_item(key)
    if item is None:
        raise ValueError(f"Item '{key}' not found")
    notes = reader.get_notes(key)
    return {
        "item": _item_to_dict(item, detail=detail),
        "notes": [_note_to_dict(n) for n in notes],
    }


def _handle_pdf(key: str, pages: str | None) -> dict:
    cfg = load_config()
    data_dir = get_data_dir(cfg)
    reader = _get_reader()
    att = reader.get_pdf_attachment(key)
    if att is None:
        raise ValueError(f"No PDF attachment found for item '{key}'")
    pdf_path = data_dir / "storage" / att.key / att.filename
    if not pdf_path.exists():
        raise ValueError(f"PDF file not found at {pdf_path}")

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
    except PdfExtractionError as e:
        return {"error": str(e), "context": "pdf"}
    finally:
        cache.close()

    return {"key": key, "pages": pages, "text": text}


def _handle_annotations(key: str) -> dict:
    from zotero_cli_cc.core.pdf_extractor import extract_annotations

    reader = _get_reader()
    att = reader.get_pdf_attachment(key)
    if att is None:
        return {"error": f"No PDF attachment found for '{key}'"}
    cfg = load_config()
    data_dir = get_data_dir(cfg)
    pdf_path = data_dir / "storage" / att.key / att.filename
    if not pdf_path.exists():
        return {"error": f"PDF file not found at {pdf_path}"}
    annots = extract_annotations(pdf_path)
    return {"key": key, "annotations": annots, "total": len(annots)}


def _handle_summarize(key: str) -> dict:
    reader = _get_reader()
    item = reader.get_item(key)
    if item is None:
        raise ValueError(f"Item '{key}' not found")
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


def _handle_summarize_all(limit: int) -> dict:
    reader = _get_reader()
    result = reader.search("", limit=limit)
    items = []
    for item in result.items:
        items.append(
            {
                "key": item.key,
                "title": item.title,
                "authors": [c.full_name for c in item.creators],
                "abstract": item.abstract,
                "tags": item.tags,
                "date": item.date,
            }
        )
    return {"items": items, "total": result.total}


def _handle_export(key: str, fmt: str) -> dict:
    reader = _get_reader()
    citation = reader.export_citation(key, fmt=fmt)
    if citation is None:
        raise ValueError(f"Item '{key}' not found or format '{fmt}' not supported")
    return {
        "citation": citation,
        "format": fmt,
        "key": key,
    }


def _handle_relate(key: str, limit: int) -> dict:
    reader = _get_reader()
    items = reader.get_related_items(key, limit=limit)
    return {
        "items": [_item_to_dict(i) for i in items],
        "source_key": key,
    }


def _handle_recent(days: int, modified: bool, limit: int) -> dict:
    from datetime import datetime, timedelta, timezone

    reader = _get_reader()
    sort_field = "dateModified" if modified else "dateAdded"
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    items = reader.get_recent_items(since=since_str, sort=sort_field, limit=limit)
    return {"items": [_item_to_dict(i) for i in items], "total": len(items)}


def _handle_note_view(key: str) -> dict:
    reader = _get_reader()
    notes = reader.get_notes(key)
    return {
        "notes": [_note_to_dict(n) for n in notes],
        "parent_key": key,
    }


def _handle_tag_view(key: str) -> dict:
    reader = _get_reader()
    item = reader.get_item(key)
    if item is None:
        raise ValueError(f"Item '{key}' not found")
    return {
        "tags": item.tags,
        "key": key,
        "title": item.title,
    }


def _handle_collection_list() -> dict:
    reader = _get_reader()
    collections = reader.get_collections()
    return {
        "collections": [_collection_to_dict(c) for c in collections],
    }


def _handle_collection_items(collection_key: str) -> dict:
    reader = _get_reader()
    items = reader.get_collection_items(collection_key)
    return {
        "items": [_item_to_dict(i) for i in items],
        "collection_key": collection_key,
    }


def _handle_duplicates(strategy: str = "both", threshold: float = 0.85, limit: int = 50) -> dict:
    reader = _get_reader()
    groups = reader.find_duplicates(strategy=strategy, threshold=threshold, limit=limit)
    result_groups = []
    for g in groups:
        result_groups.append(
            {
                "match_type": g.match_type,
                "score": g.score,
                "items": [_item_to_dict(i) for i in g.items],
            }
        )
    return {"groups": result_groups, "total": len(result_groups)}


# ---------------------------------------------------------------------------
# Write handler functions
# ---------------------------------------------------------------------------


def _handle_note_add(key: str, content: str) -> dict:
    try:
        writer = _get_writer()
        note_key = writer.add_note(key, content)
        return {"note_key": note_key}
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "note_add"}


def _handle_note_update(note_key: str, content: str) -> dict:
    try:
        writer = _get_writer()
        writer.update_note(note_key, content)
        return {"note_key": note_key, "updated": True}
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "note_update"}


def _handle_tag_add(keys: list[str], tags: list[str]) -> dict:
    try:
        writer = _get_writer()
    except (ValueError, ZoteroWriteError) as e:
        return {"error": str(e), "context": "tag_add"}
    results = []
    for key in keys:
        try:
            writer.add_tags(key, tags)
            results.append({"key": key, "tags_added": tags})
        except ZoteroWriteError as e:
            results.append({"key": key, "error": str(e)})
    return {"results": results}


def _handle_tag_remove(keys: list[str], tags: list[str]) -> dict:
    try:
        writer = _get_writer()
    except (ValueError, ZoteroWriteError) as e:
        return {"error": str(e), "context": "tag_remove"}
    results = []
    for key in keys:
        try:
            writer.remove_tags(key, tags)
            results.append({"key": key, "tags_removed": tags})
        except ZoteroWriteError as e:
            results.append({"key": key, "error": str(e)})
    return {"results": results}


def _handle_add(doi: str | None, url: str | None) -> dict:
    if not doi and not url:
        raise ValueError("Either doi or url must be provided.")
    try:
        writer = _get_writer()
        item_key = writer.add_item(doi=doi, url=url)
        return {"item_key": item_key}
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "add"}


def _handle_delete(keys: list[str]) -> dict:
    try:
        writer = _get_writer()
    except (ValueError, ZoteroWriteError) as e:
        return {"error": str(e), "context": "delete"}
    results = []
    for key in keys:
        try:
            writer.delete_item(key)
            results.append({"key": key, "deleted": True})
        except ZoteroWriteError as e:
            results.append({"key": key, "deleted": False, "error": str(e)})
    return {"results": results}


def _handle_update(key: str, fields: dict) -> dict:
    try:
        writer = _get_writer()
        writer.update_item(key, fields)
        return {"status": "updated", "key": key, "fields": fields}
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "update"}


def _handle_collection_create(name: str, parent_key: str | None) -> dict:
    try:
        writer = _get_writer()
        collection_key = writer.create_collection(name, parent_key=parent_key)
        return {"collection_key": collection_key}
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "collection_create"}


def _handle_collection_move(item_key: str, collection_key: str) -> dict:
    try:
        writer = _get_writer()
        writer.move_to_collection(item_key, collection_key)
        return {"item_key": item_key, "collection_key": collection_key}
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "collection_move"}


def _handle_collection_delete(collection_key: str) -> dict:
    try:
        writer = _get_writer()
        writer.delete_collection(collection_key)
        return {"deleted": True, "collection_key": collection_key}
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "collection_delete"}


def _handle_collection_reorganize(plan: dict) -> dict:
    """Execute a collection reorganization plan."""
    try:
        writer = _get_writer()
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "collection_reorganize"}

    collections = plan.get("collections", [])
    if not collections:
        raise ValueError("No collections in plan.")

    created: dict[str, str] = {}  # name -> key
    results = []

    for coll in collections:
        name = coll["name"]
        parent_name = coll.get("parent")
        parent_key = created.get(parent_name) if parent_name else None
        items = coll.get("items", [])

        try:
            col_key = writer.create_collection(name, parent_key=parent_key)
            created[name] = col_key

            moved = []
            failed = []
            for item_key in items:
                try:
                    writer.move_to_collection(item_key, col_key)
                    moved.append(item_key)
                except ZoteroWriteError as e:
                    failed.append({"key": item_key, "error": str(e)})

            results.append(
                {
                    "name": name,
                    "collection_key": col_key,
                    "items_moved": len(moved),
                    "items_failed": len(failed),
                    "failures": failed,
                }
            )
        except ZoteroWriteError as e:
            results.append({"name": name, "error": str(e)})

    return {"collections_created": len(created), "results": results}


def _handle_collection_rename(collection_key: str, new_name: str) -> dict:
    try:
        writer = _get_writer()
        writer.rename_collection(collection_key, new_name)
        return {"collection_key": collection_key, "new_name": new_name}
    except ZoteroWriteError as e:
        return {"error": str(e), "context": "collection_rename"}


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


# ---------------------------------------------------------------------------
# MCP tool definitions
# ---------------------------------------------------------------------------


@mcp.tool()
def search(
    query: str,
    collection: str | None = None,
    item_type: str | None = None,
    sort: str | None = None,
    direction: str = "desc",
    limit: int = 50,
) -> dict:
    """Search the Zotero library by title, author, tag, or full text.

    Args:
        query: Search query string.
        collection: Optional collection name or key to filter results.
        item_type: Optional item type filter (e.g. journalArticle, book, preprint).
        sort: Sort field — 'dateAdded', 'dateModified', 'title', or 'creator'.
        direction: Sort direction — 'asc' or 'desc' (default 'desc').
        limit: Maximum number of results (default 50).
    """
    return _handle_search(query, collection, limit, item_type=item_type, sort=sort, direction=direction)


@mcp.tool()
def list_items(
    item_type: str | None = None,
    sort: str | None = None,
    direction: str = "desc",
    limit: int = 50,
) -> dict:
    """List all items in the Zotero library.

    Args:
        item_type: Optional item type filter (e.g. journalArticle, book, preprint).
        sort: Sort field — 'dateAdded', 'dateModified', 'title', or 'creator'.
        direction: Sort direction — 'asc' or 'desc' (default 'desc').
        limit: Maximum number of items to return (default 50).
    """
    return _handle_list_items(limit, item_type=item_type, sort=sort, direction=direction)


@mcp.tool()
def read(key: str, detail: str = "standard") -> dict:
    """Read full details of a Zotero item including its notes.

    Args:
        key: The Zotero item key (e.g. 'ABC123').
        detail: Detail level — 'minimal', 'standard', or 'full'.
    """
    return _handle_read(key, detail)


@mcp.tool()
def pdf(key: str, pages: str | None = None) -> dict:
    """Extract text from the PDF attachment of a Zotero item.

    Args:
        key: The Zotero item key.
        pages: Optional page range (e.g. '1-5' or '3' for a single page).
    """
    return _handle_pdf(key, pages)


@mcp.tool()
def annotations(key: str) -> dict:
    """Extract annotations (highlights, notes, comments) from a PDF attachment.

    Args:
        key: Item key whose PDF attachment to extract annotations from.
    """
    return _handle_annotations(key)


@mcp.tool()
def summarize(key: str) -> dict:
    """Get a structured summary of a Zotero item for AI consumption.

    Args:
        key: The Zotero item key.
    """
    return _handle_summarize(key)


@mcp.tool()
def summarize_all(limit: int = 10000) -> dict:
    """Export all items with key, title, abstract, authors, tags for AI classification.

    Args:
        limit: Maximum number of items (default 10000).
    """
    return _handle_summarize_all(limit)


@mcp.tool()
def export(key: str, fmt: str = "bibtex") -> dict:
    """Export citation for a Zotero item.

    Args:
        key: The Zotero item key.
        fmt: Citation format — 'bibtex', 'csl-json', or 'ris' (default 'bibtex').
    """
    return _handle_export(key, fmt)


@mcp.tool()
def relate(key: str, limit: int = 20) -> dict:
    """Find items related to a given Zotero item.

    Args:
        key: The Zotero item key.
        limit: Maximum number of related items (default 20).
    """
    return _handle_relate(key, limit)


@mcp.tool()
def recent(days: int = 7, modified: bool = False, limit: int = 50) -> dict:
    """Show recently added or modified items.

    Args:
        days: Number of days to look back (default: 7)
        modified: If True, use dateModified instead of dateAdded
        limit: Maximum number of items to return
    """
    return _handle_recent(days, modified, limit)


@mcp.tool()
def note_view(key: str) -> dict:
    """View all notes attached to a Zotero item.

    Args:
        key: The Zotero item key.
    """
    return _handle_note_view(key)


@mcp.tool()
def tag_view(key: str) -> dict:
    """View tags for a Zotero item.

    Args:
        key: The Zotero item key.
    """
    return _handle_tag_view(key)


@mcp.tool()
def collection_list() -> dict:
    """List all collections in the Zotero library."""
    return _handle_collection_list()


@mcp.tool()
def collection_items(collection_key: str) -> dict:
    """List all items in a specific Zotero collection.

    Args:
        collection_key: The collection key.
    """
    return _handle_collection_items(collection_key)


@mcp.tool()
def duplicates(strategy: str = "both", threshold: float = 0.85, limit: int = 50) -> dict:
    """Find potential duplicate items by DOI and/or title similarity.

    Args:
        strategy: Detection strategy — 'doi', 'title', or 'both' (default 'both').
        threshold: Minimum title similarity ratio (0.0–1.0, default 0.85).
        limit: Maximum number of duplicate groups to return (default 50).
    """
    return _handle_duplicates(strategy, threshold, limit)


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------


@mcp.tool()
def note_add(key: str, content: str) -> dict:
    """Add a note to a Zotero item.

    Args:
        key: The Zotero item key to attach the note to.
        content: The note content (HTML or plain text).
    """
    return _handle_note_add(key, content)


@mcp.tool()
def note_update(note_key: str, content: str) -> dict:
    """Update an existing note in the Zotero library.

    Args:
        note_key: The Zotero note key to update.
        content: The new note content (HTML or plain text).
    """
    return _handle_note_update(note_key, content)


@mcp.tool()
def tag_add(keys: list[str], tags: list[str]) -> dict:
    """Add tags to one or more Zotero items.

    Args:
        keys: List of Zotero item keys (e.g. ['ABC123'] or ['K1', 'K2', 'K3']).
        tags: List of tag strings to add.
    """
    return _handle_tag_add(keys, tags)


@mcp.tool()
def tag_remove(keys: list[str], tags: list[str]) -> dict:
    """Remove tags from one or more Zotero items.

    Args:
        keys: List of Zotero item keys (e.g. ['ABC123'] or ['K1', 'K2', 'K3']).
        tags: List of tag strings to remove.
    """
    return _handle_tag_remove(keys, tags)


@mcp.tool()
def add(doi: str | None = None, url: str | None = None) -> dict:
    """Add a new item to the Zotero library by DOI or URL.

    Args:
        doi: The DOI of the item (e.g. '10.1234/test').
        url: The URL of the item.
    """
    return _handle_add(doi, url)


@mcp.tool()
def delete(keys: list[str]) -> dict:
    """Delete one or more items from the Zotero library (move to trash).

    Args:
        keys: List of Zotero item keys to delete (e.g. ['ABC123'] or ['K1', 'K2']).
    """
    return _handle_delete(keys)


@mcp.tool()
def update(key: str, title: str | None = None, date: str | None = None, fields: dict | None = None) -> dict:
    """Update item metadata. Pass title/date directly or use fields dict for arbitrary fields.

    Args:
        key: Item key to update.
        title: New title (optional).
        date: New date (optional).
        fields: Dict of field_name: value pairs for arbitrary fields (optional).
    """
    update_fields: dict[str, str] = {}
    if title:
        update_fields["title"] = title
    if date:
        update_fields["date"] = date
    if fields:
        update_fields.update(fields)
    if not update_fields:
        return {"error": "No fields to update"}
    return _handle_update(key, update_fields)


@mcp.tool()
def collection_create(name: str, parent_key: str | None = None) -> dict:
    """Create a new collection in the Zotero library.

    Args:
        name: The name for the new collection.
        parent_key: Optional parent collection key for creating a subcollection.
    """
    return _handle_collection_create(name, parent_key)


@mcp.tool()
def collection_move(item_key: str, collection_key: str) -> dict:
    """Move an item to a collection. Requires API credentials.

    Args:
        item_key: The Zotero item key.
        collection_key: The target collection key.
    """
    return _handle_collection_move(item_key, collection_key)


@mcp.tool()
def collection_delete(collection_key: str) -> dict:
    """Delete a collection from the Zotero library. Requires API credentials.

    Args:
        collection_key: The collection key to delete.
    """
    return _handle_collection_delete(collection_key)


@mcp.tool()
def collection_rename(collection_key: str, new_name: str) -> dict:
    """Rename a collection in the Zotero library. Requires API credentials.

    Args:
        collection_key: The collection key to rename.
        new_name: The new name for the collection.
    """
    return _handle_collection_rename(collection_key, new_name)


@mcp.tool()
def collection_reorganize(plan: dict) -> dict:
    """Batch create collections and move items based on a reorganization plan.

    The plan should have this structure:
    {"collections": [{"name": "Topic", "items": ["KEY1", "KEY2"]}, ...]}

    Optional "parent" field creates subcollections under an already-created collection.
    Requires API credentials.

    Args:
        plan: JSON object with collections array, each having name and items list.
    """
    return _handle_collection_reorganize(plan)


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
