"""`zot rename <KEY>...` — rename attachment files by a metadata template via the local bridge."""

from __future__ import annotations

import json

import click

from zotero_cli_cc.config import get_data_dir, get_prefs_js_path, load_config, resolve_library_id
from zotero_cli_cc.core.local_bridge import LocalBridgeError, ping, rename_attachment
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.rename import RenameError, build_plan
from zotero_cli_cc.core.writer import SYNC_REMINDER
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok

_BRIDGE_HINT = "Start Zotero desktop; run 'zot bridge install' to (re)install the bridge plugin (rename needs v0.2.0+)"
_ABORT_CODES = {"not_reachable", "bridge_missing"}


@click.command("rename")
@click.argument("item_keys", nargs=-1)
@click.option(
    "--template",
    default="{journal}_{year}_{title}",
    show_default=True,
    help="Filename template; tokens: {journal} {year} {title} (short title if set, else full) {fulltitle} {shorttitle} {author}",
)
@click.option("--main-only", is_flag=True, help="Rename only the main PDF (default also renames supplementary PDFs)")
@click.option(
    "--attachment", "attachment_key", default=None, help="Rename one specific attachment key (use with --name)"
)
@click.option(
    "--name", "explicit_name", default=None, help="Explicit new filename for --attachment (include the extension)"
)
@click.option("--library-id", type=int, default=None, help="Override the Zotero library ID (default: user library)")
@click.option("--force", is_flag=True, help="Overwrite if a file with the new name already exists")
@click.option("--dry-run", is_flag=True, help="Preview the renames without changing any files")
@click.option("--idempotency-key", default=None, help="Key so retries are safe; same key returns the original result")
@click.pass_context
def rename_cmd(
    ctx: click.Context,
    item_keys: tuple[str, ...],
    template: str,
    main_only: bool,
    attachment_key: str | None,
    explicit_name: str | None,
    library_id: int | None,
    force: bool,
    dry_run: bool,
    idempotency_key: str | None,
) -> None:
    """Rename PDF attachment files from item metadata. MUTATES LIBRARY.

    By default builds `{journal}_{year}_{title}.pdf` for each item's main PDF
    and `..._SI.pdf` for supplementary PDFs. Non-PDF attachments (Excel, Word,
    web snapshots) are skipped. Requires Zotero desktop running with the
    `zot-cli-bridge` plugin v0.2.0+ (run `zot bridge install`).

    \b
    Examples:
      zot rename ABCD1234 --dry-run                 # preview main + supp renames
      zot rename ABCD1234 EFGH5678                  # rename several items
      zot rename ABCD1234 --main-only               # skip supplementary PDFs
      zot rename ABCD1234 --template "{author}_{year}_{title}"
      zot rename --attachment ATT0001 --name "X.pdf"  # rename one file explicitly
    """
    json_out = ctx.obj.get("json", False)

    # Mode 1: explicit single-attachment rename (bypasses metadata/heuristics).
    if attachment_key or explicit_name:
        if not (attachment_key and explicit_name):
            emit_error(
                "validation_error",
                "--attachment and --name must be used together",
                output_json=json_out,
                context="rename",
            )
        from zotero_cli_cc.core.idempotency import get_cached, store_cached

        cache_scope = f"rename_explicit:{attachment_key}:{explicit_name}"
        row: dict[str, object] = {"attachment_key": attachment_key, "new_name": explicit_name, "role": "explicit"}
        if dry_run:
            row["status"] = "dry-run"
            _emit(ctx, json_out, [{"key": None, "renames": [row]}], renamed=0, dry_run=dry_run)
            return
        if idempotency_key:
            cached = get_cached(cache_scope, idempotency_key)
            if cached is not None:
                if json_out:
                    click.echo(json.dumps(cached, indent=2, ensure_ascii=False))
                else:
                    click.echo(f"Attachment {attachment_key} -> {explicit_name} (cached).")
                return
        try:
            res = rename_attachment(attachment_key, explicit_name, library_id=library_id, force=force)  # type: ignore[arg-type]
        except LocalBridgeError as e:
            emit_error(e.code, str(e), output_json=json_out, retryable=e.retryable, hint=_BRIDGE_HINT, context="rename")
        row["old_name"] = res.get("old_name")
        row["status"] = "renamed"
        env = _emit(ctx, json_out, [{"key": None, "renames": [row]}], renamed=1, dry_run=dry_run)
        if idempotency_key:
            store_cached(cache_scope, idempotency_key, env)
        return

    if not item_keys:
        emit_error(
            "validation_error",
            "Provide at least one ITEM_KEY, or use --attachment with --name",
            output_json=json_out,
            context="rename",
        )

    from zotero_cli_cc.core.idempotency import get_cached, store_cached

    cache_scope = f"rename:{':'.join(sorted(item_keys))}"
    if idempotency_key:
        cached = get_cached(cache_scope, idempotency_key)
        if cached is not None:
            if json_out:
                click.echo(json.dumps(cached, indent=2, ensure_ascii=False))
            else:
                n = cached.get("data", {}).get("renamed_count", 0)
                click.echo(f"Renamed {n} attachment(s) (cached).")
            return

    # Fail fast if the desktop / bridge is unreachable (skip for dry-run).
    if not dry_run:
        try:
            ping()
        except LocalBridgeError as e:
            emit_error(e.code, str(e), output_json=json_out, retryable=e.retryable, hint=_BRIDGE_HINT, context="rename")

    cfg = load_config(profile=ctx.obj.get("profile"))
    db_path = get_data_dir(cfg) / "zotero.sqlite"
    reader = ZoteroReader(
        db_path, library_id=resolve_library_id(db_path, ctx.obj), prefs_js_path=get_prefs_js_path(cfg)
    )

    results: list[dict] = []
    renamed = 0
    for key in item_keys:
        item = reader.get_item(key)
        if item is None:
            results.append({"key": key, "error": "item not found", "code": "not_found"})
            continue
        try:
            plan = build_plan(item, reader.get_attachments(key), template=template, include_supp=not main_only)
        except RenameError as e:
            results.append({"key": key, "error": str(e), "code": e.code})
            continue
        if not plan:
            results.append({"key": key, "warning": "no PDF attachments found"})
            continue
        renames: list[dict] = []
        for entry in plan:
            row = {
                "attachment_key": entry.attachment_key,
                "old_name": entry.old_name,
                "new_name": entry.new_name,
                "role": entry.role,
            }
            if entry.skip:
                row["status"] = "unchanged"
            elif dry_run:
                row["status"] = "dry-run"
            else:
                try:
                    rename_attachment(entry.attachment_key, entry.new_name, library_id=library_id, force=force)
                    row["status"] = "renamed"
                    renamed += 1
                except LocalBridgeError as e:
                    if e.code in _ABORT_CODES:
                        emit_error(
                            e.code,
                            str(e),
                            output_json=json_out,
                            retryable=e.retryable,
                            hint=_BRIDGE_HINT,
                            context="rename",
                        )
                    row["status"] = "error"
                    row["error"] = str(e)
                    row["code"] = e.code
            renames.append(row)
        results.append({"key": key, "renames": renames})

    env = _emit(ctx, json_out, results, renamed=renamed, dry_run=dry_run)
    if idempotency_key:
        store_cached(cache_scope, idempotency_key, env)


def _emit(ctx: click.Context, json_out: bool, results: list[dict], *, renamed: int, dry_run: bool) -> dict:
    data = {"results": results, "renamed_count": renamed, "sync_required": renamed > 0}
    env = envelope_ok(data, extra={"dry_run": True} if dry_run else None)
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        return env
    for item in results:
        if item.get("key"):
            click.echo(f"{item['key']}:")
        if item.get("error"):
            click.echo(f"  error: {item['error']}", err=True)
        elif item.get("warning"):
            click.echo(f"  {item['warning']}", err=True)
        for r in item.get("renames", []):
            click.echo(f"  [{r['role']}] {r.get('old_name') or '?'} -> {r['new_name']}  ({r['status']})")
    if dry_run:
        click.echo("[dry-run] no files changed", err=True)
    elif renamed:
        click.echo(SYNC_REMINDER, err=True)
    return env
