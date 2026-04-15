# Agent-Native Refactor Plan

Branch: `agent-native-refactor`
Baseline audit score: 14 / 28 (partially agent-native)
Target after P0: ~22 / 28
Target after P1: ~26 / 28

Goal: make `zot` a first-class interface for humans, AI agents (Claude Code, Codex), and orchestrators, per the agent-native-cli skill.

---

## Design invariants

- `stdout` = machine channel (JSON envelope when non-TTY or `--json`)
- `stderr` = human channel (progress, hints, warnings, errors rendered for humans)
- Exit codes = orchestrator channel (0 success, 1 runtime, 2 auth, 3 validation, 4 not-found)
- Auth stays env-delegated (`ZOT_API_KEY`, `ZOT_LIBRARY_ID`). Agents never run `config init`.
- Human-facing UX (Rich tables, colored output, interactive prompts) preserved on TTY.

## Envelope shape

Success:
```json
{ "ok": true, "data": <payload>, "meta": { "request_id": "...", "schema_version": "1.0.0" } }
```

Failure:
```json
{ "ok": false, "error": { "code": "not_found", "message": "...", "retryable": false }, "meta": { ... } }
```

Partial (batch `add`):
```json
{ "ok": "partial", "data": { "succeeded": [...], "failed": [...] }, "next": ["zot add --from-file retry.txt"] }
```

Error codes: `validation_error`, `auth_missing`, `auth_invalid`, `not_found`, `rate_limited`, `network_error`, `api_error`, `conflict`, `confirmation_required`.

---

## P0 — First PR (blocking for agent use)

Scope: envelope + channel discipline + TTY detect + schema command.

### 1. `formatter.py` — envelope helpers
- Add `envelope_ok(data, meta=None)` and `envelope_error(code, message, retryable=False, **extra)`.
- Rewrite `format_items`, `format_item_detail`, `format_collections`, `format_notes`, `format_duplicates`, `format_error` so JSON mode wraps in envelope.
- Add `ErrorInfo.code` and `ErrorInfo.retryable` fields in `models.py`.

### 2. `cli.py` — TTY auto-detect + exit codes
- If `stdout.isatty()` is False and `--json` not explicitly passed, default `output_json=True`.
- `NO_COLOR` and explicit `--format json|table` override.
- Add typed exit codes via a central `exit_with(code, err)` helper.
- Top-level error callback that converts uncaught exceptions into envelope+exit-code pairs.

### 3. Stderr routing
- Every `click.echo(format_error(...))` → `click.echo(..., err=True)`.
- Progress messages (`"Adding N items..."`, `"Cancelled."`, `SYNC_REMINDER`) → stderr.
- Files to touch: `commands/add.py`, `delete.py`, `update.py`, `update_status.py`, `config.py`, `collection.py`, `tag.py`, `trash.py`, `attach.py`, `note.py`, `search.py`, `list_cmd.py`, `read.py`.

### 4. `zot schema` command
- New `commands/schema.py`: `zot schema [<command>]`.
- Walks Click command tree, emits JSON of params (name, type, required, default, help).
- Top-level: list all resources/actions. With arg: full schema for one command.
- Include `schema_version` pulled from `__version__`.

### 5. Tests
- `tests/test_envelope.py`: success shape, error shape, partial shape.
- `tests/test_tty_detect.py`: stdout redirected → JSON auto.
- `tests/test_stderr_routing.py`: errors never on stdout.
- `tests/test_exit_codes.py`: auth missing → 2, validation → 3, not-found → 4.
- `tests/test_schema_command.py`: `zot schema search` returns expected param shape.

### 6. Docs
- Update `README.md` agent usage section with envelope example.
- Add `docs/agent-interface.md` describing envelope, exit codes, schema.

---

## P1 — Second PR (recoverability + safety)

### 7. Dry-run everywhere mutating
- Add `--dry-run` to `add`, `update`, `tag add/remove`, `collection create/add/remove`, `attach`, `note add`, `trash empty`.
- Dry-run output: `{ "ok": true, "dry_run": true, "would": { ... } }`.

### 8. Idempotency keys
- Add `--idempotency-key` to `add`, `update`, batch `add --from-file`.
- Key stored in a local SQLite cache under `$ZOT_CACHE_DIR/idempotency.db` with TTL (default 24h).
- Retried call with same key returns original envelope.

### 9. `retryable` on all errors
- Network/timeout/5xx → `retryable: true`.
- 4xx/validation/auth → `retryable: false`.
- Rate limit → `retryable: true` + `retry_after_seconds`.

### 10. Safety tiers in help
- Group commands in top-level `--help`:
  - **Read:** search, list, read, export, recent, stats, cite, open, pdf, collection list, tag list
  - **Write:** add, update, note, tag add, collection create/add, attach
  - **Destructive (warned):** delete, trash empty, update-status
- Each write/destructive command's `--help` prepends a "MUTATES LIBRARY" line.

### 11. `meta` slot
- Add `request_id` (uuid4), `latency_ms`, `schema_version` to every envelope.
- For mutating commands, add `sync_required: true`.

### 12. `next` hints
- Success envelopes for `add`, `delete`, `update` carry plausible next commands (e.g. after `add` → `["zot read <key>", "zot attach <key> --file ..."]`).

---

## P2 — Later

- NDJSON streaming for `search --stream` / `list --stream`.
- Structured progress events on stderr for `summarize-all`, `add --from-file`.
- `tool schema <resource.action>` typed-schema introspection with `since`/`deprecated` fields.
- Versioned schema with deprecation signals.
- Confirmation-required structured error when TTY is false and `--yes` omitted on destructive commands.
- OS sandbox cooperation (per skill Principle 4 update).

---

## Out of scope

- MCP server changes (`mcp_server.py`) — separate surface, separate review.
- Workspace command refactor (756 lines, treat separately).
- Changing write credentials model (env delegation already correct).

---

## Rollout

- P0 PR merged behind no feature flag — envelope is additive for JSON mode only, TTY humans see no change.
- P1 PR after P0 stabilizes.
- CHANGELOG entry each PR under "Agent interface".
- Minor version bump (0.2.x → 0.3.0) at P0 merge to signal JSON contract change.

## Success criteria

- `zot search foo | jq .ok` returns `true` without `--json` flag.
- `zot delete BAD_KEY; echo $?` returns `4` (not-found), not `1`.
- `zot schema search` returns a parseable param list.
- Piping any command through `jq` never errors on prose.
- All existing human-TTY output unchanged (Rich tables intact).
- Test suite passes; new tests cover envelope, TTY detect, stderr routing, exit codes.
