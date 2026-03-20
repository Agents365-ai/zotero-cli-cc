from __future__ import annotations

import os

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import ZoteroWriter, SYNC_REMINDER
from zotero_cli_cc.formatter import format_error


@click.command("delete")
@click.argument("key")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def delete_cmd(ctx: click.Context, key: str, yes: bool) -> None:
    """Delete an item (move to trash)."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    if not library_id or not api_key:
        click.echo(format_error("Write credentials not configured. Run: zot config init", output_json=json_out))
        return
    if not yes:
        if not click.confirm(f"Delete item '{key}'?"):
            click.echo("Cancelled.")
            return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key)
    writer.delete_item(key)
    click.echo(f"Item '{key}' moved to trash.")
    click.echo(SYNC_REMINDER)
