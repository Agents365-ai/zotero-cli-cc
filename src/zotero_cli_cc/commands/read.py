from __future__ import annotations

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_error, format_item_detail
from zotero_cli_cc.models import ErrorInfo


@click.command("read")
@click.argument("key")
@click.pass_context
def read_cmd(ctx: click.Context, key: str) -> None:
    """View item details (metadata, abstract, notes).

    \b
    Examples:
      zot read ABC123
      zot --json read ABC123
      zot --detail full read ABC123
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    json_out = ctx.obj.get("json", False)
    try:
        item = reader.get_item(key)
        if item is None:
            click.echo(
                format_error(
                    ErrorInfo(
                        message=f"Item '{key}' not found",
                        context="read",
                        hint="Run 'zot search' to find valid item keys",
                    ),
                    output_json=json_out,
                )
            )
            return
        notes = reader.get_notes(key)
        detail = ctx.obj.get("detail", "standard")
        click.echo(format_item_detail(item, notes, output_json=json_out, detail=detail))
    finally:
        reader.close()
