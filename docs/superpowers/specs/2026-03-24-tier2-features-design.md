# Tier 2 Features Design Spec

> **Goal:** Add 5 high-value features to zotero-cli-cc: duplicate detection, trash management, file attachment upload, group library support, and add-from-PDF.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Duplicate detection | Read-only (no merge) | Merge logic is fragile; Zotero desktop does it better |
| Trash management | List + restore only (no empty) | Permanent deletion from CLI is too risky |
| DOI extraction failure | Fail with hint, no fallback | Clean failure; user retries with `--doi` |
| Group library | Global `--library` option | No command duplication; follows pyzotero's model |
| `add --pdf` vs `attach` | Separate commands | Different use cases: create+attach vs attach-to-existing |
| DOI metadata enrichment | Not done by API | Zotero Web API creates bare items; metadata enrichment happens only in Zotero desktop client's "Add by Identifier" feature. Document this limitation. |

## Feature 1: Duplicate Detection

**Command:** `zot duplicates [--by doi|title|both] [--threshold 0.85]`

**Strategies:**
- **DOI match:** Exact DOI comparison across items. One `DuplicateGroup` per unique DOI that appears on 2+ items (e.g., 3 items with the same DOI = one group of 3).
- **Title match:** Normalize titles (lowercase, strip punctuation/extra whitespace), then compute similarity ratio. Default threshold 0.85. One group per cluster of similar titles.
- **Both:** Run both strategies, merge groups that share items.

**Reader method:** `find_duplicates(strategy: str = "both", threshold: float = 0.85, limit: int = 50) -> list[DuplicateGroup]`
- `limit` controls the maximum number of duplicate **groups** returned (not items fetched)
- Items fetched for comparison: capped at 10,000. If library exceeds this, emit a warning and only compare the most recent 10,000 items (by dateAdded DESC).

**Model:**
```python
@dataclass
class DuplicateGroup:
    items: list[Item]         # Always 2+ items
    match_type: str           # "doi" | "title"
    score: float              # 1.0 for DOI exact match, 0.0-1.0 for title similarity
```

**Algorithm (title):**
1. Load item titles + keys + itemIDs from SQLite (exclude attachments/notes/annotations), cap at 10k most recent
2. Normalize: `re.sub(r'[^\w\s]', '', title.lower()).strip()` + collapse whitespace via `re.sub(r'\s+', ' ', ...)`
3. Group identical normalized titles (score=1.0) — O(n) via dict
4. For remaining, use `difflib.SequenceMatcher.ratio()` for O(n^2) comparison. Skip pairs below threshold.

**Formatter:**
- **Table mode:** Columns: Group #, Keys (comma-separated), Title (first item's), Match Type, Score
- **JSON mode:** `[{"group": 1, "match_type": "doi", "score": 1.0, "items": [<Item dicts>]}, ...]`

**MCP tool:** `duplicates(strategy: str = "both", threshold: float = 0.85, limit: int = 50)`

## Feature 2: Trash Management

**Commands:**
- `zot trash list` — show trashed items using existing `format_items()` table
- `zot trash restore KEY [KEY ...]` — restore item(s) from trash

**Reader method:** `get_trash_items(limit: int = 50) -> list[Item]`
- Uses `_excluded_filter()` for type exclusion (parameterized, not hardcoded)
```sql
SELECT i.itemID FROM items i
JOIN deletedItems d ON i.itemID = d.itemID
WHERE i.itemTypeID {excl_sql}
ORDER BY d.dateDeleted DESC
LIMIT ?
```
- Builds full `Item` objects via existing `_get_items_batch()`

**Writer method:** `restore_from_trash(key: str) -> None`
- pyzotero has NO dedicated restore method
- Implementation: fetch item via `self._zot.item(key)`, set `item["data"]["deleted"] = 0`, call `self._zot.update_item(item)`
- This PATCHes the item with `deleted: 0` via the Zotero Web API, which removes it from trash
- Raises `ZoteroWriteError` if item not found or network error

**Partial failure handling:** When multiple keys provided, process each independently. Report per-key success/failure. Continue on individual failures (same pattern as batch operations in `add --from-file`).

**Output:** `trash list` uses existing `format_items()`. `trash restore` echoes per-key result: `"Restored: KEY"` or `"Failed: KEY (reason)"`, then `SYNC_REMINDER` if any succeeded.

**CLI:** Click group `trash` with subcommands `list` and `restore`

**MCP tools:** `trash_list(limit)`, `trash_restore(key)`

**SQLite schema reference:**
```sql
CREATE TABLE deletedItems (
    itemID INTEGER PRIMARY KEY,
    dateDeleted DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (itemID) REFERENCES items(itemID) ON DELETE CASCADE
);
```

## Feature 3: File Attachment Upload

**Command:** `zot attach KEY --file paper.pdf`

**Writer method:** `upload_attachment(parent_key: str, file_path: Path) -> str`
- Validates file exists before API call
- Uses `self._zot.attachment_simple([str(file_path)], parentid=parent_key)`
- Return value is `{"success": [...], "failure": [...], "unchanged": [...]}`
- If `success` is non-empty, extract key from `success[0]["key"]`
- If `unchanged` is non-empty (file already uploaded with same MD5), treat as success: return `unchanged[0]["key"]`
- If `failure` is non-empty, raise `ZoteroWriteError` with the failure message
- If all three lists are empty, raise `ZoteroWriteError("Unexpected empty response")`
- No streaming: pyzotero loads entire file into memory. Practical limit ~100MB.

**CLI:** New `attach` command. Follows write command pattern:
- Credentials from env vars (`ZOT_LIBRARY_ID`, `ZOT_API_KEY`) or config
- `ZoteroWriteError` handling with `format_error()`
- Success output: `f"Attachment uploaded: {attachment_key}"`
- `SYNC_REMINDER` on success

**JSON output:** `{"key": "<attachment_key>", "parent_key": "<parent_key>", "filename": "<name>"}`

**MCP tool:** `attach(parent_key: str, file_path: str)` — returns attachment key or error

## Feature 4: Group Library Support

**Global option:** `--library user` (default) | `--library group:<id>`

### Verified Schema

Zotero stores all libraries (user + groups) in the **same** `zotero.sqlite` file. The `items` table has a `libraryID` column:
- `libraryID=1` → personal user library (type="user" in `libraries` table)
- `libraryID=2+` → group libraries (type="group", linked via `groups` table)

```sql
-- libraries table
CREATE TABLE libraries (
    libraryID INTEGER PRIMARY KEY,
    type TEXT NOT NULL,  -- 'user' or 'group'
    editable INT NOT NULL, filesEditable INT NOT NULL, ...
);

-- groups table
CREATE TABLE groups (
    groupID INTEGER PRIMARY KEY,  -- This is the Zotero group ID (used by pyzotero)
    libraryID INT NOT NULL UNIQUE,  -- FK to libraries.libraryID (SQLite internal ID)
    name TEXT NOT NULL, ...
);
```

**Key distinction:**
- **Zotero groupID** (in `groups` table) = the public group identifier used by pyzotero and the Web API (e.g., `12345`)
- **SQLite libraryID** (in `libraries`/`items` tables) = internal integer for DB filtering (e.g., `2`)
- These are different numbers. `--library group:12345` uses the groupID; reader must look up the corresponding libraryID.

### Parsing & Validation

In `cli.py`'s `main()`:
```python
@click.option("--library", default="user", help="Library: 'user' or 'group:<id>'")
```
- `"user"` → `ctx.obj["library_type"] = "user"`, `ctx.obj["group_id"] = None`
- `"group:<digits>"` → `ctx.obj["library_type"] = "group"`, `ctx.obj["group_id"] = "<digits>"`
- Invalid format (empty id, non-integer, malformed) → Click error: `"Invalid --library format. Use 'user' or 'group:<id>'"`

### Reader Changes

Add `library_id: int = 1` parameter to `ZoteroReader.__init__()`. On init:
- If `library_id == 1` → current behavior (no query changes)
- If `library_id > 1` → add `AND i.libraryID = ?` to all item queries

**Lookup helper:** `resolve_group_library_id(group_id: int) -> int | None`
- Queries `SELECT libraryID FROM groups WHERE groupID = ?`
- Returns SQLite libraryID or None if group not found

**Affected queries** (all queries that touch the `items` table):
- `get_item()` — add `AND i.libraryID = ?`
- `search()` — add to all item subqueries
- `get_recent_items()` — add filter
- `get_trash_items()` — add filter
- `find_duplicates()` — add filter
- `get_collection_items()` — add filter
- `get_collections()` — collections also have libraryID via `collections.libraryID` column
- `get_notes()` — inherits from parent item filter
- `get_attachments()` — inherits from parent item filter
- `get_stats()` — add filter

### Writer Changes

`ZoteroWriter.__init__` signature:
```python
def __init__(self, library_id: str, api_key: str, library_type: str = "user", timeout: float = API_TIMEOUT)
```
- `library_type` passed to `zotero.Zotero(library_id, library_type, api_key)`
- When `library_type="group"`, `library_id` is the Zotero **groupID** (not SQLite libraryID)

### MCP Server Changes

Add `library` parameter to MCP tools that need it:
- All read tools get optional `library: str = "user"` parameter
- All write tools get optional `library: str = "user"` parameter
- `_get_reader()` and `_get_writer()` accept library parameter, cache per library key

### Command Changes

Every command that creates a reader or writer must read `ctx.obj["library_type"]` and `ctx.obj["group_id"]` and pass them through. Specifically:
- `search.py`, `list_cmd.py`, `read.py`, `recent.py`, `pdf.py`, `summarize.py`, `summarize_all.py`, `stats.py`, `export.py`, `cite.py`, `relate.py`, `open_cmd.py`, `note.py` (view), `tag.py` (view), `collection.py` (list, items), `duplicates.py`, `trash.py` (list) — reader commands
- `add.py`, `delete.py`, `update.py`, `note.py` (add/update), `tag.py` (add/remove), `collection.py` (create/move/delete/rename/reorganize), `attach.py`, `trash.py` (restore) — writer commands

## Feature 5: Add from Local PDF

**Command:** `zot add --pdf paper.pdf [--doi DOI_OVERRIDE]`

Uses `--pdf` (not `--file`) to avoid confusion with existing `--from-file` batch import option.

**Click option:** `@click.option("--pdf", "pdf_file", default=None, type=click.Path(exists=True), help="PDF file to extract DOI from and attach")`

**Flow:**
1. If `--doi` provided alongside `--pdf`, skip extraction, use provided DOI
2. Extract text from first 2 pages via `extract_text_from_pdf(pdf_path, pages=(1, 2))`
3. Regex match DOI: `r'10\.\d{4,9}/[^\s]+'`, then strip trailing punctuation via `.rstrip('.,;)]}>\'"')`
4. If DOI found: `writer.add_item(doi=doi)` then `writer.upload_attachment(key, file_path)`
5. If DOI not found: error with hint "No DOI found in PDF. Use --doi to specify manually."

**Important limitation:** `writer.add_item(doi=doi)` creates a **bare journalArticle** with only the DOI field populated. The Zotero Web API does NOT auto-resolve metadata from DOI (that's a Zotero desktop feature). The user must sync and use Zotero desktop to retrieve metadata, or use `zot update KEY --field title="..."` to fill in fields manually. This limitation is documented in the command's `--help` text.

**Partial failure handling:** If `add_item` succeeds but `upload_attachment` fails, the item exists without an attachment. Error message includes: `f"Item created ({key}) but attachment upload failed: {error}. Retry with: zot attach {key} --file {path}"`.

**PDF extractor addition:** `extract_doi(pdf_path: Path) -> str | None` in `core/pdf_extractor.py`
- Calls `extract_text_from_pdf(pdf_path, pages=(1, 2))`
- Applies regex `r'10\.\d{4,9}/[^\s]+'`, returns first match after `.rstrip('.,;)]}>\'"')` or None

**Dependencies:** Requires Feature 3 (`upload_attachment`) in writer.

**MCP tool:** `add_from_pdf(file_path: str, doi_override: str | None = None)` — returns item key or error

## Implementation Order

```
1. Trash management (independent, simple read+write)
2. Duplicate detection (independent, read-only)
3. File attachment upload (independent write feature)
4. Add from local PDF (depends on #3)
5. Group library support (cross-cutting, do last)
```

Each feature includes: model additions (if any), reader/writer methods, CLI command, MCP tool(s), formatter support (if needed), tests.

## Files Affected

| Feature | New Files | Modified Files |
|---------|-----------|----------------|
| Trash | `commands/trash.py`, `tests/test_trash.py` | `cli.py`, `core/reader.py`, `core/writer.py`, `mcp_server.py` |
| Duplicates | `commands/duplicates.py`, `tests/test_duplicates.py` | `cli.py`, `core/reader.py`, `mcp_server.py`, `formatter.py`, `models.py` |
| Attach | `commands/attach.py`, `tests/test_attach.py` | `cli.py`, `core/writer.py`, `mcp_server.py` |
| Add --pdf | `tests/test_add_pdf.py` | `commands/add.py`, `core/writer.py`, `core/pdf_extractor.py`, `mcp_server.py` |
| Group library | `tests/test_group_library.py` | `cli.py`, `core/reader.py`, `core/writer.py`, `mcp_server.py`, `commands/search.py`, `commands/list_cmd.py`, `commands/read.py`, `commands/recent.py`, `commands/pdf.py`, `commands/summarize.py`, `commands/summarize_all.py`, `commands/stats.py`, `commands/export.py`, `commands/cite.py`, `commands/relate.py`, `commands/open_cmd.py`, `commands/note.py`, `commands/tag.py`, `commands/collection.py`, `commands/duplicates.py`, `commands/trash.py`, `commands/add.py`, `commands/delete.py`, `commands/update.py`, `commands/attach.py` |
