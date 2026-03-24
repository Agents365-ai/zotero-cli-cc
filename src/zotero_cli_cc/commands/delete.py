from __future__ import annotations

import os

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.formatter import format_error
from zotero_cli_cc.models import ErrorInfo


@click.command("delete")
@click.argument("keys", nargs=-1, required=True)
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without executing")
@click.pass_context
def delete_cmd(ctx: click.Context, keys: tuple[str, ...], yes: bool, dry_run: bool) -> None:
    """Delete one or more items (move to trash).

    Accepts multiple keys: zot delete KEY1 KEY2 KEY3
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    if dry_run:
        for key in keys:
            click.echo(f"[dry-run] Would delete item '{key}' (move to trash)")
        return
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        click.echo(
            format_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="delete",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        )
        return
    no_interaction = ctx.obj.get("no_interaction", False)
    if not yes and not no_interaction:
        label = ", ".join(keys)
        if not click.confirm(f"Delete {len(keys)} item(s): {label}?"):
            click.echo("Cancelled.")
            return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    failed = []
    for key in keys:
        try:
            writer.delete_item(key)
            click.echo(f"Item '{key}' moved to trash.")
        except ZoteroWriteError as e:
            failed.append(key)
            click.echo(
                format_error(
                    ErrorInfo(message=str(e), context="delete", hint=f"Failed for key '{key}'"), output_json=json_out
                )
            )
    if not failed:
        click.echo(SYNC_REMINDER)
