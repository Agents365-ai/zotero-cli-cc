from __future__ import annotations

from datetime import datetime, timedelta, timezone

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_items, stream_items


@click.command("recent")
@click.option("--days", default=7, type=int, help="Number of days to look back (default: 7)")
@click.option("--modified", is_flag=True, help="Sort by date modified instead of date added")
@click.option("--limit", default=None, type=int, help="Limit results (overrides global --limit)")
@click.option("--stream", is_flag=True, help="Emit NDJSON (one item per line) for incremental processing")
@click.pass_context
def recent_cmd(ctx: click.Context, days: int, modified: bool, limit: int | None, stream: bool) -> None:
    """Show recently added or modified items.

    \b
    Examples:
      zot recent                    Items added in last 7 days
      zot recent --days 30          Items added in last 30 days
      zot recent --limit 5          Limit to 5 results
      zot --json recent --days 14   JSON output
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        limit = limit if limit is not None else ctx.obj.get("limit", cfg.default_limit)
        sort_field = "dateModified" if modified else "dateAdded"
        since = datetime.now(timezone.utc) - timedelta(days=days)
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")

        items = reader.get_recent_items(since=since_str, sort=sort_field, limit=limit)
        json_out = ctx.obj.get("json", False)
        detail = ctx.obj.get("detail", "standard")
        if stream:
            click.echo(stream_items(items, detail=detail))
            return
        if not items:
            if json_out:
                click.echo(format_items([], output_json=True))
            else:
                click.echo(f"No items {'modified' if modified else 'added'} in the last {days} day(s).", err=True)
            return
        click.echo(format_items(items, output_json=json_out, detail=detail))
    finally:
        reader.close()
