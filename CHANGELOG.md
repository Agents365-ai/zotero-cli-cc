# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
