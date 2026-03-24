"""Batch export all item summaries for AI consumption."""

from __future__ import annotations

import json

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader


@click.command("summarize-all")
@click.option("--offset", default=0, help="Skip first N items (for pagination)")
@click.pass_context
def summarize_all_cmd(ctx: click.Context, offset: int) -> None:
    """Export all items with key, title, and abstract for AI classification.

    \b
    Examples:
      zot summarize-all                   Export all items
      zot --limit 100 summarize-all       First 100 items
      zot summarize-all --offset 100      Skip first 100 (pagination)
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    limit = ctx.obj.get("limit", 10000)
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        result = reader.search("", limit=limit, offset=offset)
        items = []
        for item in result.items:
            items.append(
                {
                    "key": item.key,
                    "title": item.title,
                    "authors": [c.full_name for c in item.creators],
                    "abstract": item.abstract,
                    "tags": item.tags,
                    "date": item.date,
                }
            )
        click.echo(json.dumps(items, indent=2, ensure_ascii=False))
    finally:
        reader.close()
