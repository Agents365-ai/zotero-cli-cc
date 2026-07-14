# Agent Interface

`zot` is designed to serve three audiences from the same command surface:

- **Humans** — readable tables, colored output, interactive confirmation prompts.
- **AI agents** (Claude Code, Codex) — stable JSON envelopes, schema introspection, typed errors.
- **Orchestrators** — deterministic exit codes, delegated auth, structured progress.

`zot schema` is the machine-discoverable source for the command surface:
command names, nested subcommands, parameters, help text, and
`safety_tier`. The runtime semantics documented below describe the
execution-time contract agents should rely on; envelope coverage is now
standard across the documented commands.

## Channels

| Channel | Primary audience | Contents |
|---------|-----------------|----------|
| `stdout` | machines / agents | standard JSON envelopes; some documented commands use NDJSON/stream output |
| `stderr` | humans | prose diagnostics, progress events, `SYNC_REMINDER` |
| exit code | orchestrators | distinct code per failure class |

When `stdout` is not a TTY, JSON output is enabled automatically. Humans running `zot search foo` in a terminal see a Rich table; pipelines (`zot search foo | jq`) see JSON without passing `--json`.

Override auto-detection with `ZOT_FORMAT`:

```bash
ZOT_FORMAT=json zot search foo    # force JSON even on a TTY
ZOT_FORMAT=table zot search foo   # force table even when piped
```

## Envelope

In JSON mode, commands use the standard shapes below.

### Success

```json
{
  "ok": true,
  "data": { "key": "ABC123", "title": "..." },
  "meta": {
    "schema_version": "1.9.0",
    "cli_version": "0.3.0",
    "request_id": "a1b2c3d4e5f6",
    "latency_ms": 412
  }
}
```

Mutating command envelopes may include `data.sync_required`; when present, it is `true` if the command actually changed Zotero state and requires sync. They may also carry a `next` slot with follow-up commands:

```json
{
  "ok": true,
  "data": { "key": "ABC123", "sync_required": true },
  "next": ["zot read ABC123", "zot attach ABC123 --file <path>"],
  "meta": { ... }
}
```

### Error

```json
{
  "ok": false,
  "error": {
    "code": "not_found",
    "message": "Item 'XYZ' not found",
    "retryable": false,
    "hint": "Run 'zot search' to find valid item keys"
  },
  "meta": { "request_id": "...", "schema_version": "1.9.0" }
}
```

Error codes:

| Code | Exit | Retryable | Meaning |
|------|------|-----------|---------|
| `validation_error` | 3 | no | bad input |
| `auth_missing` / `auth_invalid` / `auth_expired` | 2 | no | credentials issue |
| `not_found` | 4 | no | resource does not exist |
| `conflict` | 6 | no | resource already exists |
| `network_error` | 5 | **yes** | transient network failure |
| `rate_limited` | 5 | **yes** | includes `retry_after_seconds` |
| `api_error` | 1 | variable | upstream Zotero API failure |
| `confirmation_required` | 3 | no | non-interactive stdin on destructive command without `--yes` |
| `not_reachable` | 5 | **yes** | `zot find-pdf`: Zotero desktop not running on 127.0.0.1:23119 |
| `bridge_missing` | 3 | no | `zot find-pdf`: `zot-cli-bridge` plugin not installed in Zotero |
| `bridge_error` | 1 | variable | `zot find-pdf`: local Zotero bridge returned an error |

Agents should read `error.retryable` before retrying.

### Partial success (batch)

```json
{
  "ok": "partial",
  "data": {
    "succeeded": [{ "entry": "10.1/a", "key": "ABC" }],
    "failed": [{ "entry": "10.1/b", "error": { "code": "network_error", "retryable": true } }]
  },
  "meta": { "total": 2, "sync_required": true }
}
```

When a batch reports partial success, inspect `data.failed[]` and explicitly retry the failed entries; do not assume the original batch will automatically replay only those items.

## Exit codes

```
0  success
1  runtime / generic error
2  auth error
3  validation / confirmation error
4  not found
5  network / rate limit
6  conflict
```

Codes are stable across versions.

## `zot schema`

Every command is self-describing:

```bash
zot schema                      # full CLI tree
zot schema search               # one command
zot schema collection add       # nested subcommand
```

Output:

```json
{
  "ok": true,
  "data": {
    "name": "search",
    "help": "Search the Zotero library by title, author, tag, or full text.",
    "safety_tier": "read",
    "since": "0.3.0",
    "deprecated": false,
    "params": [
      { "name": "query", "kind": "argument", "type": "string", "required": true },
      { "name": "collection", "kind": "option", "type": "string", "flags": ["--collection"] }
    ]
  },
  "meta": { ... }
}
```

Agents should use `zot schema <cmd>` instead of parsing `--help` output.

### Detecting changes between releases

When an agent has cached a previous schema and sees a new `meta.schema_version` on a later call, it can fetch a structural diff instead of re-parsing the whole tree:

```bash
zot schema --diff /path/to/cached-schema.json
```

The diff envelope reports added/removed commands (dotted paths) and added/removed option flags per surviving command. Type, help, and default changes are intentionally out of scope — re-fetch the full schema if those matter for your use case.

```json
{
  "ok": true,
  "data": {
    "from": { "schema_version": "1.0.0", "cli_version": "0.4.0" },
    "to":   { "schema_version": "1.1.0", "cli_version": "0.4.4" },
    "commands_added":   ["recent"],
    "commands_removed": ["legacy-cmd"],
    "commands_changed": {
      "search": { "params_added": ["--sort"] }
    }
  },
  "meta": { ... }
}
```

The input file may be either a full envelope or a bare `data` tree.

## Safety tiers

Top-level `zot --help` groups commands into risk buckets:

- **Read** — `search`, `list`, `read`, `export`, `recent`, `stats`, `cite`, `pdf`, `attachment`, `collection`, `tag`, `trash`, ...
- **Write commands (MUTATES LIBRARY)** — `add`, `update`, `note`, `attach`, `find-pdf`, `rename`, `enrich`, `bridge` (`bridge` is a local bridge/setup operation, not a Zotero library record mutation)
- **Destructive (MUTATES LIBRARY)** — `delete`, `update-status`, `orphans`

`data.safety_tier` from `zot schema <cmd>` exposes that same top-level
classification. Treat it as a coarse gating signal, not a complete runtime
authorization model: some top-level read groups contain nested mutators (for
example `trash restore`), while destructive top-level groups may also contain
inspection-only subcommands alongside the mutating ones (for example
`orphans list` versus `orphans clean`). Agents should evaluate the full command
path and documented subcommand semantics, not `safety_tier` alone.

## `--dry-run`

Many agent-facing mutating commands support `--dry-run`:

```bash
zot add --doi "10.1/x" --dry-run
```

```json
{
  "ok": true,
  "dry_run": true,
  "data": { "would": { "source": "doi", "doi": "10.1/x", "resolve_metadata": true } },
  "meta": { ... }
}
```

For commands that support it, preview envelopes set `dry_run: true`. Treat
preview behavior as command-specific: most `--dry-run` flows avoid the write
itself, `zot find-pdf --dry-run` still pings the local Zotero bridge to verify
reachability, and `zot update-status` uses preview-by-default / `--apply`
semantics instead of a `--dry-run` flag. Do not assume every mutating command
accepts `--dry-run`, or that preview mode is always network-free or
credential-free, unless that command's help says so.

## DOI metadata resolution

`zot add --doi …` calls Crossref before posting to the Zotero Web API so the
created item is not a bare DOI-only shell. The success envelope echoes a
compact summary of what was resolved (or, on miss, a `resolve_warning`):

```json
{
  "ok": true,
  "data": {
    "key": "ABCD1234",
    "doi": "10.1038/s41586-023-06139-9",
    "sync_required": true,
    "resolved": { "title": "...", "author": "Jumper et al.", "journal": "Nature", "date": "2023-07-13" }
  }
}
```

- `--no-resolve` skips the lookup (faster, but item is created with DOI only).
- Crossref `404` → `data.resolved = null` and `data.resolve_warning = "no_match"`; the item is still created.
- Network/5xx error → `data.resolved = null` and `data.resolve_warning = "<message>"`; the item is still created (agents can safely retry to populate metadata via `zot update`).
- Set `ZOT_CROSSREF_MAILTO=<email>` to join Crossref's "polite pool" (higher rate-limit ceiling, no key required).

## Local PDF attachment path (`zot attachment path`)

Agents that need to render PDF pages, inspect figures, or pass the file to a
separate parser should use `zot attachment path` instead of `zot open`.
`zot open` is for humans and launches the system PDF viewer; `attachment path`
only resolves the local file path and performs no GUI action or text extraction.

```bash
zot attachment path ABCD1234
zot --json attachment path ABCD1234
```

Envelope:

```json
{
  "ok": true,
  "data": {
    "item_key": "ABCD1234",
    "attachment_key": "ATT0001",
    "path": "/Users/me/Zotero/storage/ATT0001/paper.pdf",
    "filename": "paper.pdf",
    "exists": true,
    "mime_type": "application/pdf"
  }
}
```

The command returns the same first PDF attachment selected by `zot pdf` and
`zot open`. A missing item, missing PDF attachment, unresolved path, or missing
local file is reported as `not_found` with exit code 4. Successful output always
means `path` exists locally.

## Find Full Text (`zot find-pdf`)

The Web API cannot trigger Zotero's "Find Full Text" — that feature relies
on (1) the user's configured PDF resolvers and (2) authenticated sessions /
institutional proxies set up inside the desktop app, neither of which Web
API clients can reach. To bridge that gap, this repo ships a small Zotero 7
plugin (`extension/zot-cli-bridge/`) that registers `/zot-cli/find-pdf` on
Zotero's local HTTP server (`127.0.0.1:23119`). With the plugin installed:

```bash
zot find-pdf ABCD1234           # trigger Find Full Text for one item
zot find-pdf ABCD1234 --dry-run # only verify the bridge is reachable
```

Envelope:

```json
{
  "ok": true,
  "data": {
    "key": "ABCD1234",
    "found": true,
    "attachment_key": "ATT0001",
    "filename": "paper.pdf",
    "content_type": "application/pdf",
    "sync_required": true
  }
}
```

When no resolver matched, `found: false` and `message` explains why. New
error codes for this command: `not_reachable` (Zotero not running),
`bridge_missing` (plugin not installed), `bridge_error` (Zotero raised).

### Installing the bridge (`zot bridge`)

Modern Zotero's AddonManager won't accept a CLI-sideloaded plugin (it deletes
pointer files and hand-dropped `.xpi`s on startup), so `zot bridge install`
*builds* the plugin into an `.xpi` and hands it to Zotero's own installer.

```bash
zot bridge install                       # build the .xpi (default: ~/.cache/zot/zot-cli-bridge.xpi)
zot bridge install --output ~/x.xpi      # build to a chosen path
zot bridge status                        # ping the bridge (wraps GET /zot-cli/ping)
zot bridge uninstall                     # print Zotero plugin-manager removal steps
```

`install` prints the two-click install path: **Tools → Plugins → ⚙ → Install
Plugin From File…**, pick the `.xpi`, restart. `install`/`uninstall` use
`bridge_error` (plugin assets missing/malformed); `status` surfaces the same
`find-pdf` reachability codes (`not_reachable`, `bridge_missing`).

> The plugin manifest must carry `icons` and `applications.zotero.update_url`
> — Zotero 8/9 reject a manifest lacking them as "incompatible with this
> version of Zotero".

## Renaming attachment files (`zot rename`)

Renaming an attachment's *stored file* is a desktop operation: the Web API
can't rename the file in `storage/` without desyncing, and writing the SQLite
DB directly is forbidden. So `zot rename` goes through the same bridge plugin
as `find-pdf`, calling `POST /zot-cli/rename` →
`item.renameAttachmentFile(newName, force)` (and syncing the attachment title).
Requires the bridge plugin **v0.2.0+** — older installs return `bridge_missing`
(re-run `zot bridge install`).

```bash
zot rename ABCD1234 --dry-run        # preview old -> new for main + supp PDFs
zot rename ABCD1234 EFGH5678         # rename several items
zot rename ABCD1234 --main-only      # skip supplementary PDFs
zot rename ABCD1234 --template "{author}_{year}_{title}"
zot rename --attachment ATT0001 --name "X.pdf"  # rename one file explicitly
```

`zot` builds the new names from SQLite metadata (no network): the default
template is `{journal}_{year}_{title}` (tokens: `{journal} {year} {title}
{fulltitle} {shorttitle} {author}`; `{title}` prefers the Short Title field
when set). Empty tokens are collapsed (no `Pre__x`), single-word venues keep
the whole word (`Nature`, not `N`), and the name is truncated to a filesystem-
safe length. Attachments are filtered to PDFs by content type, so
Excel/Word/snapshots are skipped. Among PDFs, supplementary files are detected
by filename keywords (`supp`, `supplement`, `supporting`, `appendix`, a
standalone `si`); the main PDF gets the template name and each supplementary
one gets an `_SI` / `_SI2` suffix so names never collide.

The envelope's `data.results[]` carries a per-attachment `status`
(`renamed` / `unchanged` / `dry-run` / `error`); `data.renamed_count` and
`data.sync_required` summarize the run. Per-attachment failures appear inline
(e.g. `conflict` when the destination exists — pass `--force`); a missing
bridge or stopped desktop aborts the whole command with `bridge_missing` (3) /
`not_reachable` (5).

## Attaching files (`zot attach`)

`zot attach KEY --file paper.pdf` **auto-detects** how to route the file: when
the Zotero desktop bridge is reachable it imports through the desktop (local
storage); otherwise it uploads via the Web API (cloud storage). Force a route
with `--via-bridge` / `--no-via-bridge`.

The **Web-API** path stores the file in **zotero.org cloud storage**
(`data.stored: "cloud"`). The binary only appears in the local `storage/` folder
after the desktop runs a *file* sync ("Sync attachment files" enabled) — until
then the desktop shows "the attached file could not be found". The cloud result
also reports `data.result`: `"created"` (the file was uploaded) or `"exists"`
(Zotero already held an identical file, so nothing transferred).

The **bridge** path (auto-selected when the desktop is up, or forced with
`--via-bridge`) is the local-first option — it cooperates with movers like
zotero-attanger and imports through the running desktop via
`POST /zot-cli/import-file` → `Zotero.Attachments.importFromFile(...)`, writing
straight into local storage (`data.stored: "local"`) and syncing *up* afterwards.
It requires the bridge plugin **v0.3.0+** and uses the same reachability codes as
`find-pdf`/`rename` (`not_reachable` (5), `bridge_missing` (3)). Auto-detect
falls back to the Web API silently when the bridge is not reachable; an explicit
`--via-bridge` surfaces those codes as errors instead.

Importing into a **group library** (`--library group:<id>`) via the bridge needs
plugin **v0.4.0+** — the bridge maps the Web-API group id to the desktop's
internal `libraryID`. The CLI checks the running plugin's version first and fails
with `bridge_missing` (3) if it is too old, rather than silently importing into
your personal library.

## Orphaned attachments (`zot orphans`)

The flip side of the cloud-vs-local split: a storage-backed attachment whose
file is missing from the local `storage/` folder (Zotero shows "the attached
file could not be found"). `zot orphans list` scans for them (read-only) and
classifies each:

- `dead` — no copy anywhere (no server hash, not pending download). Safe to remove.
- `recoverable` — the server still has it (pending download / has a storage hash). Fix by running a Zotero file-sync, **not** by deleting.
- `unknown` — sync-state columns unavailable (e.g. a minimal database).

```bash
zot orphans list                       # all missing-file attachments, classified
zot orphans list --dead-only           # only the truly dead ones
zot orphans clean --dry-run            # preview deletions (dead only by default)
zot orphans clean --yes                # delete dead orphans via the Web API
zot orphans clean --include-recoverable --yes   # also delete server-held ones (discards the cloud copy)
```

`clean` deletes through the Web API (same path as `zot delete`), so records that
were never synced to the server come back `not_found` — remove those from the
Zotero desktop. It honors `--dry-run`, `--yes` / `--no-interaction`, and
`--idempotency-key`, and reports partial success via the standard
`envelope_partial` shape. The read scan is also exposed to agents as the MCP
`find_orphans` tool.

## Journal metrics (`zot enrich`)

`zot enrich` writes journal metrics (impact factor, JCR/CAS quartile, core-journal
flags, …) into an item's **Extra** field. It is deliberately **source-neutral**:
the values come from the caller, never from a bundled dataset or a third-party
API, so `zot` stays independent of any external product.

```bash
zot enrich ABCD1234 --set "SCI IF=5.8" --set "JCR=Q1" --dry-run
zot enrich ABCD1234 EFGH5678 --from-map journals.toml   # apply a table by journal name
zot enrich ABCD1234 --from-map journals.toml --set "JCR=Q1"   # --set overrides the map
```

- `--set "Label=value"` (repeatable) supplies metrics inline.
- `--from-map FILE` is a TOML table of `journal name -> {metric: value}`; each item
  is matched by its `publicationTitle` (or `conferenceName`), case-insensitively.
- Metrics are written between `<!-- zot:metrics -->` / `<!-- /zot:metrics -->`
  markers inside Extra (Zotero's official custom-field channel). Re-running
  **replaces only that block**, so any other Extra content (`DOI:`, `Citation
  Key:`, `tex.ids`, …) is preserved and re-running is idempotent.

This is a plain Web-API write (no bridge), so it needs API credentials. The
envelope's `data.results[]` carries per-item `status` (`updated` / `dry-run` /
`error`) plus the resolved `metrics`; `data.updated_count` / `data.sync_required`
summarize the run. Missing credentials abort with `auth_missing` (2).

## `--idempotency-key`

Mutating commands (`add`, `update`, `note --add`, `attach`, `delete`, `orphans clean`, `enrich`, `rename`, `tag`, `trash restore`, `collection create/delete/move/rename`, `update-status`) accept `--idempotency-key <string>`:

```bash
zot add --doi "10.1/x" --idempotency-key "ingest-2026-04-15-001"
# Safe to re-run; the second call returns the original envelope.
```

- Storage: SQLite under `$ZOT_CACHE_DIR/idempotency.db` (default `~/.cache/zotero-cli-cc/`).
- TTL: 24 hours.
- Scope: keyed by (command_scope, user_key) — two different commands with the same user key never collide.
- A cached response is an exact replay, including the original `request_id` and `meta`.

Retry guidance: check `error.retryable` first, then retry with the same `--idempotency-key`.

## PDF extraction

The `pdf` command supports structured content extraction:

```bash
zot pdf KEY                        # full text
zot pdf KEY --pages 1-5           # page range
zot pdf KEY --outline             # numbered heading outline
zot pdf KEY --section 3           # content under 3rd heading
zot pdf KEY --references          # parsed reference list (requires a running GROBID service)
zot pdf KEY --tables              # extract tables (requires the optional pdfplumber extractor)
zot pdf KEY --extractor pymupdf   # force specific extractor
```

JSON output envelopes the extracted content:

```json
{
  "ok": true,
  "data": {
    "key": "ABC123",
    "pages": "all",
    "text": "...",
    "meta": { "extractor": "pymupdf", "cached": true }
  },
  "meta": { "schema_version": "1.9.0", ... }
}
```

Outline output:

```json
{
  "ok": true,
  "data": {
    "key": "ABC123",
    "pages": "all",
    "outline": [
      { "number": 1, "text": "Introduction", "level": 1 },
      { "number": 2, "text": "Related Work", "level": 1 },
      { "number": 3, "text": "Methodology", "level": 2 }
    ]
  },
  "meta": { ... }
}
```

Section extraction:

```json
{
  "ok": true,
  "data": {
    "key": "ABC123",
    "pages": "all",
    "section": 3,
    "content": "Methodology content here..."
  },
  "meta": { ... }
}
```

PDF text is cached locally by (pdf_path, extractor) to avoid re-extraction. Use `zot config cache list` to inspect the cache, or `zot config cache clear` to invalidate it.

## Non-interactive operation

- `zot` never prompts for input when `stdin` is not a TTY.
- Destructive commands (`delete`) return `confirmation_required` instead of blocking. Pass `--yes`, `--dry-run`, or `--no-interaction`.
- Secrets come from env vars (`ZOT_API_KEY`, `ZOT_LIBRARY_ID`), never interactive prompts. The agent inherits these; it never runs `zot config init`.

## Streaming

`search`, `list`, and `recent` support `--stream` for incremental agent processing:

```bash
zot list --stream
```

```
{"ok":true,"data":{"key":"ABC1","title":"..."}}
{"ok":true,"data":{"key":"ABC2","title":"..."}}
{"ok":true,"summary":{"count":2,"has_more":false},"meta":{...}}
```

One JSON object per line; the final line is the summary envelope.

## Structured progress (stderr)

Long-running commands (`add --from-file`, `summarize-all`) emit NDJSON progress events on stderr while the final result envelope goes to stdout:

```
stderr:
{"event":"start","phase":"batch_add","total":730,"request_id":"...","elapsed_ms":0}
{"event":"progress","phase":"batch_add","done":100,"total":730,"elapsed_ms":18421}
{"event":"progress","phase":"batch_add","done":200,"total":730,"elapsed_ms":36842}
{"event":"complete","phase":"batch_add","done":730,"total":730,"succeeded":725,"failed":5,"elapsed_ms":56234}

stdout:
{"ok":"partial","data":{"succeeded":[...],"failed":[...]},"meta":{...}}
```

Agents tail stderr for liveness; stdout remains a single clean envelope.

## Workspace RAG

Workspaces support hybrid BM25 + semantic search via embeddings:

```bash
zot workspace index my-workspace           # BM25 only
zot workspace index my-workspace --force  # rebuild index
zot workspace query "reward hacking" --workspace my-workspace
zot workspace query "reward hacking" --workspace my-workspace --mode hybrid
zot workspace query "reward hacking" --workspace my-workspace --mode bm25
```

Query JSON output:

```json
{
  "ok": true,
  "data": {
    "mode": "hybrid",
    "results": [
      { "rank": 1, "score": 0.8942, "item_key": "ABC123", "source": "pdf", "content": "..." },
      { "rank": 2, "score": 0.8123, "item_key": "DEF456", "source": "metadata", "content": "..." }
    ]
  },
  "meta": { "schema_version": "1.9.0", ... }
}
```

The `mode` field indicates what retrieval was used:
- `bm25`: keyword search only
- `semantic`: embedding similarity only
- `hybrid`: reciprocal rank fusion of both

When `--mode auto` is used (default), the system automatically selects `hybrid` if embeddings exist for the workspace, otherwise `bm25`.

## Auth delegation

Writes require `ZOT_LIBRARY_ID` and `ZOT_API_KEY` in the environment. Set these once (shell profile, systemd unit, supervisor) before launching the agent:

```bash
export ZOT_LIBRARY_ID="$(zot config get library_id)"
export ZOT_API_KEY="$(zot config get api_key)"
claude-code                          # agent inherits credentials
```

The agent never runs `zot config init` and never handles OAuth. If the env var is missing, the agent gets a structured `auth_missing` error with exit code 2.

## Trust boundary

| Supplied by | Examples | Trust level |
|-------------|----------|-------------|
| Human / orchestrator env | `ZOT_API_KEY`, `ZOT_LIBRARY_ID`, `ZOT_FORMAT`, `ZOT_PROFILE`, `ZOT_CACHE_DIR` | trusted |
| Agent CLI args | `--doi`, `--title`, `--key`, `--idempotency-key` | untrusted (validated at CLI boundary) |

Agents choose *what* to do inside the surface the human set up; they cannot escalate their own credentials.

## Quick reference

```bash
# discovery
zot schema                       # list commands
zot schema add                   # schema for one command

# read (always safe)
zot search "attention" --limit 5
zot list --stream                # NDJSON

# dry-run first, then commit
zot add --doi "10.1/x" --dry-run
zot add --doi "10.1/x" --idempotency-key "k1"

# safe retry
zot add --doi "10.1/x" --idempotency-key "k1"   # returns cached envelope

# error routing
zot read NOPE; echo $?           # 4
zot delete XYZ; echo $?          # 3 (confirmation_required under non-tty)
```
