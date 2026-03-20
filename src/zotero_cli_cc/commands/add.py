from __future__ import annotations

import os

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import ZoteroWriter, SYNC_REMINDER
from zotero_cli_cc.formatter import format_error


@click.command("add")
@click.option("--doi", default=None, help="DOI to add")
@click.option("--url", default=None, help="URL to add")
@click.pass_context
def add_cmd(ctx: click.Context, doi: str | None, url: str | None) -> None:
    """Add an item to the Zotero library."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    if not library_id or not api_key:
        click.echo(format_error("Write credentials not configured. Run: zot config init", output_json=json_out))
        return
    if not doi and not url:
        click.echo(format_error("Provide --doi or --url", output_json=json_out))
        return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key)
    key = writer.add_item(doi=doi, url=url)
    click.echo(f"Item added: {key}")
    click.echo(SYNC_REMINDER)
