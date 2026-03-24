from __future__ import annotations

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_error, format_items
from zotero_cli_cc.models import ErrorInfo


@click.command("relate")
@click.argument("key")
@click.pass_context
def relate_cmd(ctx: click.Context, key: str) -> None:
    """Find related items via shared tags, collections, or explicit relations.

    \b
    Examples:
      zot relate ABC123
      zot --json relate ABC123
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        limit = ctx.obj.get("limit", 20)
        items = reader.get_related_items(key, limit=limit)
        if not items:
            click.echo(
                format_error(
                    ErrorInfo(
                        message=f"No related items found for '{key}'",
                        context="relate",
                        hint="Items need shared tags or collections to find relations",
                    ),
                    output_json=json_out,
                )
            )
            return
        detail = ctx.obj.get("detail", "standard")
        click.echo(format_items(items, output_json=json_out, detail=detail))
    finally:
        reader.close()
