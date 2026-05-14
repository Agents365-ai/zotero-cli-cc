# Agent Interface

`zot` is designed to serve three audiences from the same command surface:

- **Humans** — readable tables, colored output, interactive confirmation prompts.
- **AI agents** (Claude Code, Codex) — stable JSON envelopes, schema introspection, typed errors.
- **Orchestrators** — deterministic exit codes, delegated auth, structured progress.

Everything on this page is machine-verifiable via `zot schema`.

## Channels

| Channel | Primary audience | Contents |
|---------|-----------------|----------|
| `stdout` | machines / agents | one JSON envelope per invocation (or NDJSON under `--stream`) |
| `stderr` | humans | prose diagnostics, progress events, `SYNC_REMINDER` |
| exit code | orchestrators | distinct code per failure class |

When `stdout` is not a TTY, JSON output is enabled automatically. Humans running `zot search foo` in a terminal see a Rich table; pipelines (`zot search foo | jq`) see JSON without passing `--json`.

Override auto-detection with `ZOT_FORMAT`:

```bash
ZOT_FORMAT=json zot search foo    # force JSON even on a TTY
ZOT_FORMAT=table zot search foo   # force table even when piped
```

## Envelope

### Success

```json
{
  "ok": true,
  "data": { "key": "ABC123", "title": "..." },
  "meta": {
    "schema_version": "1.2.0",
    "cli_version": "0.3.0",
    "request_id": "a1b2c3d4e5f6",
    "latency_ms": 412
  }
}
```

Mutating commands additionally set `data.sync_required: true` and may carry a `next` slot with follow-up commands:

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
  "meta": { "request_id": "...", "schema_version": "1.2.0" }
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

Re-running with the same `--idempotency-key` retries only the failed items (see below).

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

Commands are grouped by risk in `zot --help`:

- **Read** — `search`, `list`, `read`, `export`, `recent`, `stats`, `cite`, `pdf`, `collection list`, `tag list`, ...
- **Write (MUTATES LIBRARY)** — `add`, `update`, `note`, `attach`, `find-pdf`
- **Destructive (MUTATES LIBRARY)** — `delete`, `update-status`

Each write or destructive command's `--help` carries a `MUTATES LIBRARY` marker. The same classification is available via `zot schema <cmd>.safety_tier`.

## `--dry-run`

Every mutating command accepts `--dry-run`:

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

Dry-run does not require credentials and never touches the network.

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

## `--idempotency-key`

Mutating commands (`add`, `update`, `note --add`, `attach`, `delete`) accept `--idempotency-key <string>`:

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
  "meta": { "schema_version": "1.2.0", ... }
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
  "meta": { "schema_version": "1.2.0", ... }
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
