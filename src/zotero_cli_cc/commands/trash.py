from __future__ import annotations

import os

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.formatter import format_error, format_items, print_error
from zotero_cli_cc.models import ErrorInfo


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
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
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
    finally:
        reader.close()


@trash_group.command("restore")
@click.argument("keys", nargs=-1, required=True)
@click.option("--dry-run", is_flag=True, help="Show what would be restored without executing")
@click.pass_context
def trash_restore_cmd(ctx: click.Context, keys: tuple[str, ...], dry_run: bool) -> None:
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
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        print_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="trash restore",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        return

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    any_success = False
    for key in keys:
        try:
            writer.restore_from_trash(key)
            click.echo(f"Restored: {key}")
            any_success = True
        except ZoteroWriteError as e:
            print_error(
                    ErrorInfo(message=str(e), context="trash restore", hint=f"Failed for key '{key}'"),
                    output_json=json_out,
                )
    if any_success:
        click.echo(SYNC_REMINDER)
