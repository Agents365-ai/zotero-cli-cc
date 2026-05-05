# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`zotero-cli-cc` (binary: `zot`) — a Zotero CLI built for Claude Code / agent use. It combines **direct local SQLite reads** with **Zotero Web API writes**, and exposes the same surface via an MCP server. The CLI follows an agent-native contract documented in `docs/agent-interface.md` (stable JSON envelope, typed exit codes, `zot schema` introspection, `--dry-run`, `--idempotency-key`, NDJSON streaming).

## Common commands

Uses `uv` as the package manager (`uv.lock` is authoritative). CI runs on Python 3.10–3.13.

```bash
# Install dev environment (mirrors CI)
uv sync --group dev --extra mcp

# Lint / format / type-check / test — same order as .github/workflows/ci.yml
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/   # use `ruff format` (without --check) to auto-fix
uv run mypy src/zotero_cli_cc/
uv run pytest tests/ -v

# Run a single test / file / node
uv run pytest tests/test_reader.py -v
uv run pytest tests/test_reader.py::test_name -v
uv run pytest -k "search and not rag" -v

# Run the CLI from source
uv run zot search "foo"
uv run zot schema                         # emit full command tree (agent introspection)

# Build / publish artifacts (hatchling backend)
uv build
```

Note on PyPI publish gating: the `publish.yml` workflow gates release on lint+mypy only, **not** full pytest (see commit `6267da8`). Keep that intentional when editing CI.

## Architecture

### Read/write split (the central design constraint)

- **Reads** go through `core/reader.py` — opens `zotero.sqlite` directly (read-only) from the auto-detected Zotero data directory. No network, no API key, works offline, works while Zotero.app is running.
- **Writes** go through `core/writer.py` — uses `pyzotero` against the Zotero Web API so Zotero's sync engine sees the change. Never write to `zotero.sqlite` directly; doing so corrupts Zotero's sync state.

This split is load-bearing for the project's value proposition. Preserve it when adding commands: a new mutating command belongs on the Web API side, not SQLite.

### CLI shape (`cli.py` + `commands/`)

- `cli.py` is the Click root group. It registers every subcommand from `commands/*.py` and classifies them into safety tiers (read / mutating / destructive) which drive `--help` grouping and the agent schema. When adding a command, register it in `cli.py` AND add it to the appropriate tier set, or help/schema will misreport its risk.
- Each `commands/<name>.py` is a self-contained Click command/group. They orchestrate `core/*` modules and pass results through `formatter.py`.
- `formatter.py` implements the dual-output contract: Rich tables when stdout is a TTY, JSON envelope when piped (auto-detected) or when `--json` / `ZOT_FORMAT=json` is set. Every command's output must flow through the formatter to keep the envelope stable — don't `click.echo` structured data directly.
- `exit_codes.py` enumerates the typed exit codes (1 runtime, 2 auth, 3 validation, 4 not-found, 5 network, 6 conflict). Errors must map to one of these via `emit_error(...)`; the agent contract in `docs/agent-interface.md` promises stability. Avoid the legacy `print_error(...); return` pattern — it silently exits 0 and breaks agent error-handling.
- `schema.py` (command) reflects the entire Click tree into the JSON schema that agents consume. If you add options/arguments, they appear here automatically — but only if you use standard Click constructs.

### Core subsystems (`core/`)

- `reader.py` — SQLite read layer (search, list, read, collections, tags, attachments metadata).
- `writer.py` — pyzotero-backed writes (add, update, delete, note, tag mutations, attachment upload).
- `pdf_extractor.py` + `pdf_cache.py` — pluggable extraction backends (`pymupdf` default, `mineru` opt-in with auto-fallback) with on-disk cache keyed per-extractor; feeds `zot pdf`, `summarize`, and the workspace RAG indexer.
- `workspace.py` — local-only TOML-backed workspaces at `~/.config/zot/workspaces/<name>.toml` (no API key, no Zotero sync). Workspaces are lightweight cross-cutting groupings, distinct from Zotero collections.
- `rag.py` + `rag_index.py` — BM25 index over workspace metadata + PDF text, with optional embedding-based hybrid retrieval. The embedding layer is provider-routed (`core/embedding_router.py`) — choose via `[embedding] provider` (jina/aliyun) plus `ZOT_EMBEDDING_URL` / `ZOT_EMBEDDING_KEY`.
- `idempotency.py` — supports `--idempotency-key` on mutating commands so agent retries are safe.
- `semantic_scholar.py` — drives `zot update-status` (preprint → published detection).
- `version_check.py` — PyPI version nudge.

### MCP server (`mcp_server.py`)

Exposes the CLI functionality as MCP tools (`zot mcp serve`). When adding a new CLI command that should also be agent-callable via MCP clients, mirror it here. The MCP surface is optional (`pip install zotero-cli-cc[mcp]`).

### Config & profiles

Config lives at `~/.config/zot/config.toml` with multi-profile support (`[profiles.<name>]` sections). Resolution order for any setting: CLI flag → env var (`ZOT_DATA_DIR`, `ZOT_LIBRARY_ID`, `ZOT_API_KEY`, `ZOT_PROFILE`, …) → active profile → defaults. Zotero data dir auto-detects: Windows registry / `%APPDATA%\Zotero` / `%LOCALAPPDATA%\Zotero` on Windows; `~/Zotero` on macOS/Linux.

## Conventions

- Type hints are required (`disallow_untyped_defs = true`). mypy runs on `src/zotero_cli_cc/` only — tests are exempt.
- Ruff: `target-version = py310`, `line-length = 120`, E501 ignored. `zotero_cli_cc` is configured as first-party for isort.
- License is **CC-BY-NC-4.0** (non-commercial). This is unusual for Python tooling; preserve the license header and classifier when touching packaging metadata.
- Never run `git commit` or `git push` without explicit user instruction — the repo has CI, docs, and PyPI publish wired to `main`.

## Docs & skill

- User-facing docs in `docs/` build with MkDocs Material (bilingual via `mkdocs-static-i18n`); CLI reference is generated by `mkdocs-click` from the Click tree, so updating Click help text updates the docs.
- `skill/zotero-cli-cc/` is the Claude Code skill packaged with this repo; users install it by copying to `~/.claude/skills/`. Keep it in sync with CLI surface changes.
- `docs/agent-interface.md` is the authoritative agent contract — when changing envelope shape, exit codes, or schema, update it and bump `schema_version` accordingly.

## Designing new commands

When adding or refactoring a CLI command (flags, output shape, exit codes, confirmation/idempotency behavior), invoke the **`agent-native-design`** skill first: https://github.com/Agents365-ai/agent-native-design

It encodes the design rules that keep `zot` usable by both humans and agents — dual-output contract, typed exit codes, JSON envelope shape, idempotency, dry-run conventions — and aligns with `docs/agent-interface.md`. New contributors should read it before touching the CLI surface.
