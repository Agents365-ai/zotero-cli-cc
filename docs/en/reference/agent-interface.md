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
    "schema_version": "1.0.0",
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
  "meta": { "request_id": "...", "schema_version": "1.0.0" }
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

## Safety tiers

Commands are grouped by risk in `zot --help`:

- **Read** — `search`, `list`, `read`, `export`, `recent`, `stats`, `cite`, `pdf`, `collection list`, `tag list`, ...
- **Write (MUTATES LIBRARY)** — `add`, `update`, `note`, `attach`
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
  "data": { "would": { "source": "doi", "doi": "10.1/x" } },
  "meta": { ... }
}
```

Dry-run does not require credentials and never touches the network.

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
