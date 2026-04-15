from __future__ import annotations

import json
import os

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.exit_codes import EXIT_RUNTIME, emit_error
from zotero_cli_cc.formatter import envelope_ok, envelope_partial


@click.command("delete")
@click.argument("keys", nargs=-1, required=True)
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without executing")
@click.option("--idempotency-key", default=None, help="Key so retries are safe; same key returns the original result")
@click.pass_context
def delete_cmd(
    ctx: click.Context,
    keys: tuple[str, ...],
    yes: bool,
    dry_run: bool,
    idempotency_key: str | None,
) -> None:
    """Delete one or more items (move to trash). MUTATES LIBRARY.

    Accepts multiple keys: zot delete KEY1 KEY2 KEY3
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    if dry_run:
        data = {"would_delete": list(keys), "count": len(keys)}
        if json_out:
            click.echo(json.dumps(envelope_ok(data, extra={"dry_run": True}), indent=2, ensure_ascii=False))
        else:
            for key in keys:
                click.echo(f"[dry-run] Would delete item '{key}' (move to trash)")
        return
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        emit_error(
            "auth_missing",
            "Write credentials not configured",
            output_json=json_out,
            hint="Run 'zot config init' to set up API credentials",
            context="delete",
        )
    no_interaction = ctx.obj.get("no_interaction", False)
    import sys

    if not yes and not no_interaction:
        if not sys.stdin.isatty():
            emit_error(
                "confirmation_required",
                f"Refusing to delete {len(keys)} item(s) without confirmation on non-interactive stdin",
                output_json=json_out,
                hint="Pass --yes to confirm or use --dry-run to preview",
                context="delete",
            )
        label = ", ".join(keys)
        if not click.confirm(f"Delete {len(keys)} item(s): {label}?"):
            if json_out:
                click.echo(json.dumps(envelope_ok({"cancelled": True}), indent=2, ensure_ascii=False))
            else:
                click.echo("Cancelled.", err=True)
            return
    from zotero_cli_cc.core.idempotency import get_cached, store_cached

    cache_scope = "delete:" + ",".join(sorted(keys))
    if idempotency_key:
        cached = get_cached(cache_scope, idempotency_key)
        if cached is not None:
            if json_out:
                click.echo(json.dumps(cached, indent=2, ensure_ascii=False))
            else:
                click.echo(f"Deleted {len(keys)} item(s) (cached).")
            return

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    succeeded: list[dict] = []
    failed: list[dict] = []
    for key in keys:
        try:
            writer.delete_item(key)
            succeeded.append({"key": key})
            if not json_out:
                click.echo(f"Item '{key}' moved to trash.")
        except ZoteroWriteError as e:
            failed.append({"key": key, "error": {"code": e.code, "message": str(e), "retryable": e.retryable}})
            if not json_out:
                click.echo(f"Error: delete failed for '{key}': {e}", err=True)
    if json_out:
        if failed and succeeded:
            env = envelope_partial(succeeded, failed, meta={"sync_required": True})
        elif failed:
            click.echo(json.dumps({"ok": False, "error": {"code": "api_error", "message": f"{len(failed)} delete(s) failed", "retryable": True, "failed": failed}}, indent=2, ensure_ascii=False))
            raise SystemExit(EXIT_RUNTIME)
        else:
            env = envelope_ok(
                {"deleted": [s["key"] for s in succeeded], "sync_required": True},
                extra={"next": ["zot trash list", "zot trash empty --yes"]},
            )
        if idempotency_key and not failed:
            store_cached(cache_scope, idempotency_key, env)
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
    else:
        if not failed:
            click.echo(SYNC_REMINDER, err=True)
        if failed:
            raise SystemExit(EXIT_RUNTIME)
