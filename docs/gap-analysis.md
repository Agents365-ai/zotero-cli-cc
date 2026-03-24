# Zotero-CLI-CC Feature Gap Analysis

> Generated: 2026-03-24 | Compared against: Zotero Web API v3, 54yyyu/zotero-mcp, pyzotero, papis

## Current State

- **18 CLI commands** + **21 MCP tools**
- Architecture: SQLite direct reads (offline, fast) + Zotero Web API writes via pyzotero
- Dual interface: CLI (`zot`) + MCP server (FastMCP)

## Features zotero-cli-cc Has

### Read Operations (via local SQLite)

| Feature | CLI Command | MCP Tool |
|---------|------------|----------|
| Search (title, author, tag, fulltext) | `zot search` | `search` |
| List all items | `zot list` | `list_items` |
| Read item details + notes | `zot read KEY` | `read` |
| PDF text extraction (pymupdf, page ranges, caching) | `zot pdf KEY` | `pdf` |
| View notes (HTML-to-Markdown) | `zot note view KEY` | `note_view` |
| View tags | `zot tag view KEY` | `tag_view` |
| List collections (tree) | `zot collection list` | `collection_list` |
| Collection items | `zot collection items KEY` | `collection_items` |
| Related items (explicit + shared tags/collections) | `zot relate KEY` | `relate` |
| Library statistics | `zot stats` | -- |
| Export citations (BibTeX, CSL-JSON, RIS) | `zot export KEY` | `export` |
| Format citations (APA, Nature, Vancouver) + clipboard | `zot cite KEY` | -- |
| Summarize item for AI | `zot summarize KEY` | `summarize` |
| Summarize all items for AI classification | `zot summarize-all` | `summarize_all` |
| Open PDF/URL in system app | `zot open KEY` | -- |

### Write Operations (via Zotero Web API / pyzotero)

| Feature | CLI Command | MCP Tool |
|---------|------------|----------|
| Add item by DOI or URL | `zot add --doi/--url` | `add` |
| Batch add from file | `zot add --from-file` | -- |
| Delete item(s) | `zot delete KEY` | `delete` |
| Add note to item | `zot note add KEY` | `note_add` |
| Update note | `zot note update KEY` | `note_update` |
| Add tags (batch) | `zot tag add KEY` | `tag_add` |
| Remove tags (batch) | `zot tag remove KEY` | `tag_remove` |
| Create collection | `zot collection create` | `collection_create` |
| Move item to collection | `zot collection move` | `collection_move` |
| Delete collection | `zot collection delete` | `collection_delete` |
| Rename collection | `zot collection rename` | `collection_rename` |
| Batch reorganize collections (JSON plan) | `zot collection reorganize` | `collection_reorganize` |

---

## Gap Analysis: Missing Features

### Tier 1 — High Value, Moderate Effort

| # | Feature | Description | Source |
|---|---------|-------------|--------|
| 1 | **Update item metadata** | `zot update KEY --title/--date/--field key=value` — pyzotero `update_item()` already available | Zotero API, pyzotero |
| 2 | **Item type filtering** | `zot search "query" --type journalArticle` — simple SQL WHERE addition | Zotero API |
| 3 | **Sort & order control** | `--sort dateAdded/title --direction desc` — ORDER BY in SQLite queries | Zotero API |
| 4 | **Recently added/modified** | `zot recent --days 7` — trivial with date sorting | Zotero API |
| 5 | **PDF annotation extraction** | Highlights, comments with page numbers — pymupdf already supports this | 54yyyu/zotero-mcp |

### Tier 2 — High Value, Higher Effort

| # | Feature | Description | Source |
|---|---------|-------------|--------|
| 6 | **Duplicate detection** | `zot duplicates --by title,doi` — fuzzy title + DOI comparison | 54yyyu/zotero-mcp |
| 7 | **Trash management** | `zot trash list/restore/empty` — read SQLite, restore via API | Zotero API |
| 8 | **File attachment upload** | `zot attach KEY --file paper.pdf` — multi-step upload auth flow | Zotero API, pyzotero |
| 9 | **Group library support** | `--library group:12345` — pyzotero supports, reader needs different SQLite | Zotero API, pyzotero |
| 10 | **Add from local PDF** | `zot add --file paper.pdf` — extract DOI from PDF, then add + attach | 54yyyu/zotero-mcp |

### Tier 3 — Medium Value

| # | Feature | Description | Source |
|---|---------|-------------|--------|
| 11 | Saved searches CRUD | pyzotero supports, just expose | Zotero API |
| 12 | More export formats | BibLaTeX, MODS, TEI, CSV | Zotero API |
| 13 | Formatted bibliography | CSL-driven bibliographies via citeproc-py | Zotero API |
| 14 | Remove item from collection | Missing counterpart to `collection move` | Zotero API |
| 15 | BetterBibTeX citation key lookup | Parse from `extra` field | 54yyyu/zotero-mcp |

### Tier 4 — Nice to Have

| # | Feature | Description | Source |
|---|---------|-------------|--------|
| 16 | Semantic search | Embedding-based similarity (vector DB) | 54yyyu/zotero-mcp |
| 17 | DOI-to-key index | Quick lookup table for citation workflows | pyzotero |
| 18 | Version tracking / sync | Incremental sync detection | Zotero API |
| 19 | Web interface | `zot serve` | papis |
| 20 | Collection-scoped tag listing | Simple SQL join | Zotero API |

---

## Competitor Comparison

### vs. 54yyyu/zotero-mcp (most feature-rich MCP server)

Missing: semantic search, PDF annotations, duplicate detection/merge, open-access PDF download, item metadata updates, BetterBibTeX lookup, recently added items, add from local file, search notes/annotations, PDF outline extraction.

### vs. pyzotero (Python library, used as dependency)

12 capabilities not exposed: full item CRUD, item templates (30+ types), file upload/download, saved searches, group access, version tracking, item validation, pagination helpers, delete from collection, library settings.

### vs. Zotero Web API v3

11 high-priority gaps (item updates, file upload/download, trash, saved searches, groups, pagination, sorting, type filtering, publications, version tracking). 8 medium-priority gaps (batch updates, library-wide tag deletion, remove from collection, batch delete, collection tags, conditional requests, write tokens).

---

## References

- [Zotero Web API v3 Basics](https://www.zotero.org/support/dev/web_api/v3/basics)
- [Zotero Web API v3 Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)
- [pyzotero Documentation](https://pyzotero.readthedocs.io/en/latest/)
- [54yyyu/zotero-mcp GitHub](https://github.com/54yyyu/zotero-mcp)
