# Tier 2 Features Design Spec

> **Goal:** Add 5 high-value features to zotero-cli-cc: duplicate detection, trash management, file attachment upload, group library support, and add-from-PDF.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Duplicate detection | Read-only (no merge) | Merge logic is fragile; Zotero desktop does it better |
| Trash management | List + restore only (no empty) | Permanent deletion from CLI is too risky |
| DOI extraction failure | Fail with hint, no fallback | Clean failure; user retries with `--doi` |
| Group library | Global `--library` option | No command duplication; follows pyzotero's model |
| `add --file` vs `attach` | Separate commands | Different use cases: create+attach vs attach-to-existing |

## Feature 1: Duplicate Detection

**Command:** `zot duplicates [--by doi|title|both] [--threshold 0.85]`

**Strategies:**
- **DOI match:** Exact DOI comparison across items. Groups items sharing the same non-empty DOI.
- **Title match:** Normalize titles (lowercase, strip punctuation/extra whitespace), then compute similarity ratio. Default threshold 0.85.
- **Both:** Run both strategies, deduplicate groups.

**Reader method:** `find_duplicates(strategy, threshold, limit) -> list[DuplicateGroup]`

**Model:**
```python
@dataclass
class DuplicateGroup:
    items: list[Item]
    match_type: str       # "doi" | "title"
    score: float          # 1.0 for DOI, similarity ratio for title
```

**Algorithm (title):**
1. Load all item titles + keys from SQLite (exclude attachments/notes/annotations)
2. Normalize: `re.sub(r'[^\w\s]', '', title.lower()).strip()` + collapse whitespace
3. Group identical normalized titles (score=1.0)
4. For remaining, use `difflib.SequenceMatcher.ratio()` for O(n^2) comparison — acceptable for typical libraries (<10k items). Skip pairs below threshold.

**Formatter:** Table with columns: Group #, Keys, Titles, Match Type, Score

**MCP tool:** `duplicates(strategy, threshold, limit)`

## Feature 2: Trash Management

**Commands:**
- `zot trash list` — show trashed items
- `zot trash restore KEY [KEY ...]` — restore item(s) from trash

**Reader method:** `get_trash_items(limit) -> list[Item]`
```sql
SELECT i.itemID FROM items i
JOIN deletedItems d ON i.itemID = d.itemID
WHERE i.itemTypeID NOT IN (excluded)
ORDER BY d.dateDeleted DESC
LIMIT ?
```

**Writer method:** `restore_from_trash(key) -> None`
- Uses `pyzotero` — fetches item, removes `deleted` flag, updates via API

**CLI:** Click group `trash` with subcommands `list` and `restore`

**MCP tools:** `trash_list`, `trash_restore`

## Feature 3: File Attachment Upload

**Command:** `zot attach KEY --file paper.pdf`

**Writer method:** `upload_attachment(parent_key, file_path) -> str`
- Uses `pyzotero.Zotero.attachment_simple([str(file_path)], parent_key)`
- Returns attachment key
- Validates file exists before API call

**CLI:** New `attach` command, follows write command pattern (credentials from env/config, `ZoteroWriteError` handling, `SYNC_REMINDER`)

**MCP tool:** `attach(parent_key, file_path)`

## Feature 4: Group Library Support

**Global option:** `--library user` (default) | `--library group:<id>`

**Parsing:** In `cli.py`'s `main()`, parse `--library` value:
- `"user"` or not set → current behavior
- `"group:<id>"` → set `ctx.obj["library_type"] = "group"`, `ctx.obj["library_id"] = "<id>"`

**Reader impact:**
- Group SQLite path: need to determine actual Zotero group DB location
- Zotero 7 stores group data in the same `zotero.sqlite` but with `libraryID > 1`
- Alternative: query `libraries` and `groups` tables to find group libraryID, then filter items by libraryID
- This is the simpler approach — no separate DB file, just add `WHERE libraryID = ?` to queries

**Writer impact:**
- `ZoteroWriter.__init__` accepts `library_type="user"|"group"`
- Passes to `zotero.Zotero(library_id, library_type, api_key)`

**Reader query changes:**
- Add optional `library_id: int | None` parameter to reader methods
- Default `None` means libraryID=1 (personal library, current behavior)
- When group specified, look up group's libraryID from `libraries`/`groups` tables

**Config:** `ctx.obj["library_type"]` and `ctx.obj["library_id_override"]` passed through to reader/writer initialization in each command

## Feature 5: Add from Local PDF

**Command:** `zot add --file paper.pdf [--doi DOI_OVERRIDE]`

**Flow:**
1. If `--doi` provided alongside `--file`, skip extraction, use provided DOI
2. Otherwise, extract text from first 2 pages of PDF via pymupdf
3. Regex match DOI: `r'10\.\d{4,9}/[^\s]+'`
4. If DOI found: `writer.add_item(doi=doi)` then `writer.upload_attachment(key, file_path)`
5. If DOI not found: error with hint "No DOI found. Use --doi to specify manually."

**PDF extractor addition:** `extract_doi(pdf_path: Path) -> str | None` in `pdf_extractor.py`

**Dependencies:** Requires Feature 3 (`upload_attachment`) in writer.

## Implementation Order

```
1. Trash management (independent, simple read+write)
2. Duplicate detection (independent, read-only)
3. File attachment upload (independent write feature)
4. Add from local PDF (depends on #3)
5. Group library support (cross-cutting, do last)
```

Each feature includes: model additions, reader/writer methods, CLI command, MCP tool, formatter support, tests.

## Files Affected

| Feature | New Files | Modified Files |
|---------|-----------|----------------|
| Trash | `commands/trash.py` | `cli.py`, `reader.py`, `writer.py`, `mcp_server.py`, `formatter.py`, `models.py` |
| Duplicates | `commands/duplicates.py` | `cli.py`, `reader.py`, `mcp_server.py`, `formatter.py`, `models.py` |
| Attach | `commands/attach.py` | `cli.py`, `writer.py`, `mcp_server.py` |
| Add --file | — | `commands/add.py`, `writer.py`, `pdf_extractor.py`, `mcp_server.py` |
| Group library | — | `cli.py`, `reader.py`, `writer.py`, `config.py`, most commands |
