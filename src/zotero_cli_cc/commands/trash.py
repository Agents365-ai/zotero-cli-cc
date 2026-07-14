from __future__ import annotations

import click

from zotero_cli_cc.commands._helpers import build_writer, open_reader
from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import format_items


@click.group("trash")
def trash_group() -> None:
    """Manage trashed items (list, restore)."""
    pass


@trash_group.command("list")
@click.option("--limit", default=None, type=int, help="Limit results (overrides global --limit)")
@click.pass_context
def trash_list_cmd(ctx: click.Context, limit: int | None) -> None:
    """List items in the trash.

    \b
    Examples:
      zot trash list
      zot trash list --limit 10
      zot --json trash list
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    with open_reader(ctx, cfg) as reader:
        limit = limit if limit is not None else ctx.obj.get("limit", cfg.default_limit)
        items = reader.get_trash_items(limit=limit)
        if not items:
            if ctx.obj.get("json"):
                click.echo("[]")
            else:
                click.echo("Trash is empty.")
            return
        detail = ctx.obj.get("detail", "standard")
        click.echo(format_items(items, output_json=ctx.obj.get("json", False), detail=detail))


@trash_group.command("restore")
@click.argument("keys", nargs=-1, required=True)
@click.option("--dry-run", is_flag=True, help="Show what would be restored without executing")
@click.option("--idempotency-key", default=None, help="Key so retries are safe; same key returns the original result")
@click.pass_context
def trash_restore_cmd(ctx: click.Context, keys: tuple[str, ...], dry_run: bool, idempotency_key: str | None) -> None:
    """Restore item(s) from trash. MUTATES LIBRARY.

    \b
    Examples:
      zot trash restore ABC123
      zot trash restore KEY1 KEY2 KEY3
      zot trash restore ABC123 --dry-run
    """
    import json as _json

    from zotero_cli_cc.formatter import envelope_ok

    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    if dry_run:
        data = {"would_restore": list(keys), "count": len(keys)}
        if json_out:
            click.echo(_json.dumps(envelope_ok(data, extra={"dry_run": True}), indent=2, ensure_ascii=False))
        else:
            for k in keys:
                click.echo(f"[dry-run] Would restore '{k}'")
        return
    from zotero_cli_cc.core.idempotency import get_cached, store_cached

    cache_scope = f"trash_restore:{':'.join(sorted(keys))}"
    if idempotency_key:
        cached = get_cached(cache_scope, idempotency_key)
        if cached is not None:
            if json_out:
                click.echo(_json.dumps(cached, indent=2, ensure_ascii=False))
            else:
                count = len(cached.get("data", {}).get("restored", []))
                click.echo(f"Restored {count} item(s) (cached).")
            return

    writer = build_writer(ctx, cfg, json_out, context="trash restore")
    for key in keys:
        try:
            writer.restore_from_trash(key)
            click.echo(f"Restored: {key}")
        except ZoteroWriteError as e:
            emit_error("runtime_error", str(e), output_json=json_out, context="trash restore")

    env = envelope_ok({"restored": list(keys)})
    if idempotency_key:
        store_cached(cache_scope, idempotency_key, env)
    if json_out:
        click.echo(_json.dumps(env, indent=2, ensure_ascii=False))
    else:
        click.echo(SYNC_REMINDER)
