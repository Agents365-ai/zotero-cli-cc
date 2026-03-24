# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.6] - 2026-03-24

### Added
- `zot duplicates [--by doi|title|both] [--threshold 0.85]` — find duplicate items by DOI match or fuzzy title similarity
- `zot trash list` — view trashed items
- `zot trash restore KEY [KEY ...]` — restore item(s) from trash via Zotero API
- `zot attach KEY --file paper.pdf` — upload file attachments to existing items
- `zot add --pdf paper.pdf` — extract DOI from PDF, create item, and attach file
- `--library group:<id>` — global option for group library support across all commands
- `DuplicateGroup` model for structured duplicate detection results
- `resolve_library_id()` helper for group library resolution
- All 5 new features available as MCP tools (`duplicates`, `trash_list`, `trash_restore`, `attach`, `add_from_pdf`)
- `library` parameter added to all existing MCP tools for group library access
- 43 new tests (314 total)

### Changed
- `ZoteroReader` accepts `library_id` parameter for multi-library filtering
- `ZoteroWriter` accepts `library_type` parameter for group library writes
- MCP server uses per-library reader cache instead of global singleton

## [0.1.5] - 2026-03-24

### Added
- `zot search --type journalArticle` — filter search/list results by item type
- `zot search --sort dateAdded --direction desc` — sort results by date, title, or creator
- `zot recent --days 7` — show recently added or modified items
- `zot update KEY --title/--date/--field` — update item metadata via Zotero API
- `zot pdf KEY --annotations` — extract PDF annotations (highlights, notes, comments)
- `--detail full` now shows journal, volume, issue, pages, ISSN, publisher, citation key
- `summarize` now shows URL, tags, source info, abstract, and notes
- All 5 new features available as MCP tools (`search`, `list_items`, `recent`, `update`, `annotations`)
- 37 new tests (271 total)

### Fixed
- `--detail full` output was identical to standard detail level
- `summarize` command only showed basic metadata without abstract or source info

## [0.1.3] - 2026-03-23

### Added
- `zot cite` command — format citations in APA, Nature, or Vancouver style and copy to clipboard
- `zot add --from-file` — batch import DOIs/URLs from a text file (one per line, supports `#` comments)
- RIS export format (`zot export KEY --format ris`) with 11 Zotero type mappings
- Usage examples in `--help` text for 13 commands
- PyPI/CI/Python/License badges in README
- `pipx` as install option
- Shell completion install instructions (zsh/bash/fish)

## [0.1.2] - 2026-03-22

### Added
- `--dry-run` flag for `delete`, `collection delete`, and `tag` commands
- `--offset` pagination for `summarize-all` and `reader.search()`
- `PdfExtractionError` with graceful handling of corrupted/password-protected PDFs
- Page range validation — error when requested pages exceed document length
- API timeout (30s) on ZoteroWriter to prevent hanging on unresponsive servers
- `_excluded_filter()` method returning parameterized SQL placeholders
- `markdownify` dependency for proper HTML-to-Markdown conversion
- 19 new tests covering dry-run, offset, PDF errors, timeouts, and write error handling (199 total)

### Changed
- Exception handling narrowed from `except Exception` to `except ZoteroWriteError` in all write commands
- HTML-to-Markdown conversion replaced from naive regex to `markdownify` library
- WAL lock fallback uses `TemporaryDirectory` instead of manual `mkdtemp`/`rmtree`
- `__enter__`/`__exit__` type annotations fixed, removed `type: ignore`
- Search queries use parameterized SQL (`?` placeholders) instead of string interpolation

### Fixed
- Unguarded writer calls in `add`, `delete`, `tag`, `note` commands now catch `ZoteroWriteError`
- `httpx.TimeoutException` now caught alongside `ConnectError` in all writer methods

## [0.1.1] - 2026-03-22

### Added
- `zot stats` command for library statistics
- `zot open` command for launching PDFs and URLs
- CSL-JSON export format
- Shared MCP reader instance with `atexit` cleanup
- `note_update` MCP tool
- Collection key filter for search
- Unified Zotero skill routing between `zot` and `rak`

### Fixed
- Excluded type IDs looked up dynamically instead of hardcoding
- Fulltext search routed to `rak` for semantic search
- Version sync, CI workflow, temp file leak, BibTeX escaping, search N+1

## [0.1.0] - 2026-03-21

### Added
- Initial release
- SQLite-based read operations (search, list, read, export, relate, notes, collections, attachments, PDF extraction)
- Web API write operations via pyzotero (add, delete, tag, note, collection CRUD)
- MCP server with 17 tools (11 read + 6 write)
- `summarize-all` and `collection reorganize` for AI classification
- PDF text extraction with SQLite-backed caching
- Rich table + JSON output formatting
- TOML-based configuration with profile support
- WAL lock handling with automatic fallback
- Batch query optimization (N+1 prevention)
- BibTeX and CSL-JSON citation export
- Related items discovery (explicit relations + implicit via shared tags/collections)
