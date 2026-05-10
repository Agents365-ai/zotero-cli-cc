# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.2] - 2026-05-10

### Fixed

- Update-available nag fired indefinitely after upgrading because
  `__version__` was hardcoded in `__init__.py` and missed in the 0.4.0 / 0.4.1
  bumps, so installed copies of 0.4.1 reported themselves as 0.3.0. Version is
  now sourced from package metadata (`importlib.metadata`), making
  `pyproject.toml` the single source of truth (#30).

## [0.4.1] - 2026-05-05

Embedding configuration cleanup. The provider-specific Aliyun key
(`aliyun_api_key` / `ZOT_EMBEDDING_ALIYUN_KEY`) and the implicit
`provider="auto"` mode were leaking the multi-provider routing
implementation into the user-facing config without a symmetrical
counterpart for Jina. Single-provider, single-key surface is cleaner.

### Changed

- `[embedding] provider` default is now `"jina"` (was `"auto"`). Set
  `provider = "aliyun"` (or `ZOT_EMBEDDING_PROVIDER=aliyun`) to use
  Aliyun DashScope.

### Removed (Breaking, very rare)

- `[embedding] aliyun_api_key` config key — use the unified
  `[embedding] api_key` instead.
- `ZOT_EMBEDDING_ALIYUN_KEY` env var — use `ZOT_EMBEDDING_KEY` instead.
- `provider = "auto"` mode — pick a provider explicitly.

If you upgraded to 0.4.0 within the past hour and were already using
the Aliyun-specific key, rename it to `api_key` /
`ZOT_EMBEDDING_KEY` and set `provider = "aliyun"`.

## [0.4.0] - 2026-05-05

PDF extraction overhaul, envelope routing for the rest of the `--json` surface,
typed exit codes wired up across all command error paths, and a CI repair pass.
`schema_version` bumps to **1.1.0**.

### Added

- **MinerU PDF extractor** alongside the existing pymupdf-based extractor, with
  a new `BasePdfExtractor` abstract class and automatic fallback when MinerU
  fails (`zot pdf KEY --extractor mineru`). Configure via `[pdf] extractor`,
  `[pdf] mineru_token`, or `MINERU_TOKEN` / `ZOT_PDF_EXTRACTOR` env vars.
- **`zot pdf --outline`** — list every heading in the document as a numbered
  outline so agents can navigate without dumping the full text.
- **`zot pdf --section N`** — extract just the content under the N-th heading
  from `--outline`. Useful for "show me the methods section" workflows.
- **`zot workspace index --extractor`** — choose the PDF extractor used during
  RAG indexing.
- **Embedding provider router** with first-class support for Aliyun
  (DashScope, OpenAI-compatible) and Jina endpoints. Routes via the new
  `[embedding] provider` config key / `ZOT_EMBEDDING_PROVIDER` env var.
  *(0.4.1 simplified the surface — see below.)*
- **Attachment resolver** that handles `storage:` paths, `file://` URLs,
  Zotero's `attachments:` paths, Windows drive letters, and base-attachment
  prefs. PDFs in non-default storage directories now resolve correctly.
- **`progress_callback`** plumbing through the PDF extraction path so MinerU
  batch operations and per-PDF extraction surface progress to the caller.

### Changed

- **Envelope routing** extended to the remaining `--json` commands:
  `zot pdf` (incl. `--outline` / `--section`), `zot workspace list`,
  `zot workspace query`, and `zot config cache list` now emit the standard
  `{ok, data, meta}` envelope. `workspace query` `data` becomes
  `{mode, results}` rather than the bare results list.
- **`schema_version` 1.0.0 → 1.1.0** to reflect the envelope-coverage extension
  and the typed-exit-code parity. `docs/agent-interface.md` updated.
- **Typed exit codes wired across all command error paths.** Previously many
  error paths called `print_error(...); return`, printing the error message
  but silently exiting 0. They now use `emit_error(...)` with the appropriate
  typed code:
  - `not_found` (4): item / PDF / workspace / collection / profile / index /
    section missing — affects `cite`, `export`, `summarize`, `open`, `pdf`,
    `workspace delete/add/remove/show/export/import/search/index/query`,
    `config profile_set`.
  - `validation_error` (3): bad page range in `pdf`, missing required source
    flag in `workspace import`, invalid workspace name.
  - `auth_missing` (2): all `tag` / `trash restore` / `collection`
    write commands when API credentials aren't configured.
  - `conflict` (6): `workspace new` when the workspace already exists,
    and **`zot duplicates` now exits 6 when duplicates are found** so
    agents can branch on `if zot duplicates …; then …; else act_on_dups; fi`.
  - `runtime_error` (1): caught `PdfExtractionError` in `pdf` and
    `ZoteroWriteError` in `collection move/delete/rename`.
- **`zot relate KEY`** with no related items is now a normal exit-0 outcome
  (matching `zot search` on no matches) rather than an error message.
- **`config cache list`** robustness: graceful fallback when the cache DB is
  unreachable; closes the connection in a `finally` block.

### Fixed

- 20 pre-existing test failures on `main` repaired (some were envelope-shape
  drift between tests and production; the rest were genuine exit-code
  regressions covered by the migration above). The `ci.yml` pytest run goes
  green again.
- `tests/test_extracts_text` no longer breaks on hosts without
  `~/.config/zot/config.toml`. The previous over-broad `Path.exists` mock
  also patched `load_pdf_config`'s file-existence check; tightened to a
  targeted `load_pdf_config` mock.

### Breaking

- Tools / agents parsing `--json` output from `zot pdf`, `zot workspace
  list`, `zot workspace query`, or `zot config cache list` need to unwrap
  the standard envelope (`result["data"]`). Other commands were already
  enveloped; this brings the rest of the surface into line.
- Error paths that previously exited 0 with a printed message now exit
  with their typed code (1, 2, 3, 4, or 6). Scripts that ran
  `zot cite NONEXIST && echo ok` and similar will now correctly fail.
- `zot duplicates` exits **6 (CONFLICT)** when duplicates are detected.
  Scripts that ignored the exit code or used `if zot duplicates; then`
  will need to invert the branch.

## [0.3.0] - 2026-04-15

Agent-native CLI interface. `zot` now serves humans, AI agents (Claude Code,
Codex), and orchestrators from a single surface. See `docs/agent-interface.md`
for the full contract.

### Added

- **Stable JSON envelope** for every command: `{"ok": true, "data": ..., "meta": {...}}` on success, `{"ok": false, "error": {"code", "message", "retryable"}, "meta": {...}}` on failure, `{"ok": "partial", "data": {"succeeded", "failed"}}` for batch operations.
- **TTY auto-detection**: `--json` is now implicit when stdout is not a TTY. Agents piping `zot` output always get parseable JSON without remembering a flag. Override with `ZOT_FORMAT=json|table|text`.
- **Typed exit codes**: 0 success, 1 runtime error, 2 auth error, 3 validation error, 4 not-found, 5 network error, 6 conflict. Orchestrators can route failures deterministically.
- `zot schema [command...]` — machine-readable introspection for the full CLI tree. Each entry carries `name`, `params` (typed), `safety_tier`, `since`, `deprecated`, and nested `subcommands`. Agents can discover every command without a README.
- **Safety tiers in `--help`**: top-level help groups commands into Read / Write (MUTATES LIBRARY) / Destructive sections. Destructive command help carries a "MUTATES LIBRARY" warning.
- **`--dry-run`** on all mutating commands: `add`, `update`, `note --add`, `attach`, `delete`, `trash restore`. Preview shape: `{"ok": true, "dry_run": true, "data": {"would": ...}}`.
- **`--idempotency-key`** on `add`, `update`, `note --add`, `attach`, `delete`. SQLite-backed cache at `$ZOT_CACHE_DIR/idempotency.db` (default `~/.cache/zotero-cli-cc`) with 24h TTL. Retried calls carrying the same key return the original envelope and never duplicate the upstream mutation.
- **`meta` slot** on every envelope: `request_id` (uuid), `latency_ms`, `schema_version`, `cli_version`. Mutating commands also set `sync_required: true`.
- **`next` hints** in success envelopes: `add`, `update`, `delete`, `note --add`, `attach` suggest plausible follow-up commands so the agent saves a planning turn.
- **`retryable` field on every error**: network / 5xx / rate-limit → `retryable: true`; not-found / validation / 4xx → `retryable: false`. `ZoteroWriteError` carries `code`, `retryable`, `retry_after_seconds`.
- **`--stream` mode** on `search`, `list`, `recent` — emits NDJSON (one item per line) plus a summary line. Agents can process long result sets incrementally.
- **Structured stderr progress events** for long-running commands (`add --from-file`, `summarize-all`): NDJSON `{event, phase, done, total, elapsed_ms, request_id}` so agents can detect liveness without blocking on the final stdout envelope.
- **Confirmation-required guard** on destructive commands: `zot delete K1` with non-interactive stdin and no `--yes`/`--dry-run` returns a structured `confirmation_required` error instead of blocking.
- New `exit_codes.py`, `core/idempotency.py` modules.
- 43 new tests across `test_agent_interface.py`, `test_agent_p1.py`, `test_agent_p2.py`.

### Changed

- `format_error` / `format_items` / `format_item_detail` / `format_collections` / `format_notes` / `format_duplicates` now wrap JSON output in the envelope. Callers that parsed raw arrays must unwrap via `env["data"]`.
- Human error messages moved from stdout to stderr via the new `print_error` helper.
- `ErrorInfo` dataclass gains `code` and `retryable` fields.
- Top-level CLI group uses a custom `TieredGroup` help renderer.

### Breaking

- JSON output contract: callers parsing bare arrays or dicts must now read from `env["data"]`. Error responses now nest under `env["error"]` with `code` / `message` / `retryable` fields instead of a flat `{"error": "..."}`.
- Exit codes: previously `1` for all failures; now distinct codes per failure class. Scripts checking for any non-zero exit remain valid.

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
