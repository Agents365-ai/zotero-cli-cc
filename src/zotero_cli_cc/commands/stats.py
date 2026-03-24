from __future__ import annotations

import json

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader


@click.command("stats")
@click.pass_context
def stats_cmd(ctx: click.Context) -> None:
    """Show library statistics (items, PDFs, notes, types, collections, tags).

    \b
    Examples:
      zot stats
      zot --json stats
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    json_out = ctx.obj.get("json", False)
    try:
        stats = reader.get_stats()
        if json_out:
            click.echo(json.dumps(stats, indent=2, ensure_ascii=False))
        else:
            click.echo(f"Total items: {stats['total_items']}")
            click.echo(f"PDF attachments: {stats['pdf_attachments']}")
            click.echo(f"Notes: {stats['notes']}")
            click.echo()
            click.echo("Items by type:")
            for name, cnt in stats["by_type"].items():
                click.echo(f"  {name}: {cnt}")
            click.echo()
            click.echo(f"Collections ({len(stats['collections'])}):")
            for name, cnt in stats["collections"].items():
                click.echo(f"  {name}: {cnt} items")
            click.echo()
            click.echo(f"Top tags ({len(stats['top_tags'])}):")
            for name, cnt in stats["top_tags"].items():
                click.echo(f"  {name}: {cnt}")
    finally:
        reader.close()
