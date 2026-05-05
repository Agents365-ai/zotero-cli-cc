from __future__ import annotations

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_items


@click.command("relate")
@click.argument("key")
@click.option("--limit", default=None, type=int, help="Limit results (overrides global --limit)")
@click.pass_context
def relate_cmd(ctx: click.Context, key: str, limit: int | None) -> None:
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
        limit = limit if limit is not None else ctx.obj.get("limit", 20)
        items = reader.get_related_items(key, limit=limit)
        if not items:
            # Empty result is a normal outcome, not an error — exit 0 with a friendly message.
            if json_out:
                click.echo("[]")
            else:
                click.echo(
                    f"No related items found for '{key}'. Items need shared tags or collections to find relations."
                )
            return
        detail = ctx.obj.get("detail", "standard")
        click.echo(format_items(items, output_json=json_out, detail=detail))
    finally:
        reader.close()
