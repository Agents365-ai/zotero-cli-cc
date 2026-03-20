from __future__ import annotations

import json
import os

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import ZoteroWriter, SYNC_REMINDER
from zotero_cli_cc.formatter import format_error


@click.command("tag")
@click.argument("key")
@click.option("--add", "add_tag", default=None, help="Add a tag")
@click.option("--remove", "remove_tag", default=None, help="Remove a tag")
@click.pass_context
def tag_cmd(ctx: click.Context, key: str, add_tag: str | None, remove_tag: str | None) -> None:
    """View or manage tags for an item."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)

    if add_tag or remove_tag:
        library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
        api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
        if not library_id or not api_key:
            click.echo(format_error("Write credentials not configured. Run: zot config init", output_json=json_out))
            return
        writer = ZoteroWriter(library_id=library_id, api_key=api_key)
        if add_tag:
            writer.add_tags(key, [add_tag])
            click.echo(f"Tag '{add_tag}' added to '{key}'.")
        if remove_tag:
            writer.remove_tags(key, [remove_tag])
            click.echo(f"Tag '{remove_tag}' removed from '{key}'.")
        click.echo(SYNC_REMINDER)
    else:
        data_dir = get_data_dir(cfg)
        db_path = data_dir / "zotero.sqlite"
        reader = ZoteroReader(db_path)
        try:
            item = reader.get_item(key)
            if item is None:
                click.echo(format_error(f"Item '{key}' not found", output_json=json_out))
                return
            if json_out:
                click.echo(json.dumps(item.tags))
            else:
                click.echo(f"Tags for {key}: {', '.join(item.tags) if item.tags else '(none)'}")
        finally:
            reader.close()
