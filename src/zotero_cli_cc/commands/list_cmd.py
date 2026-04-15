from __future__ import annotations

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import format_items, stream_items


@click.command("list")
@click.option(
    "--collection",
    default=None,
    help="Filter by Zotero collection (folder) name. Use 'zot collection list' to see available names.",
)
@click.option("--type", "item_type", default=None, help="Filter by item type (e.g. journalArticle, book, preprint)")
@click.option(
    "--sort",
    default=None,
    type=click.Choice(["dateAdded", "dateModified", "title", "creator"]),
    help="Sort results by field",
)
@click.option(
    "--direction",
    default="desc",
    type=click.Choice(["asc", "desc"]),
    help="Sort direction (default: desc)",
)
@click.option("--limit", default=None, type=int, help="Limit results (overrides global --limit)")
@click.option("--stream", is_flag=True, help="Emit NDJSON (one item per line) for incremental processing")
@click.pass_context
def list_cmd(
    ctx: click.Context,
    collection: str | None,
    item_type: str | None,
    sort: str | None,
    direction: str,
    limit: int | None,
    stream: bool,
) -> None:
    """List items in the Zotero library.

    \b
    Examples:
      zot list
      zot list --type journalArticle
      zot list --limit 10

    \b
    Filter by Zotero collection (folder):
      zot collection list                                  # show available collections
      zot list --collection "Machine Learning" --limit 10  # list within a collection
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        limit = limit if limit is not None else ctx.obj.get("limit", cfg.default_limit)
        try:
            result = reader.search(
                "", collection=collection, item_type=item_type, sort=sort, direction=direction, limit=limit
            )
        except ValueError as e:
            emit_error("validation_error", str(e), output_json=ctx.obj.get("json", False))
        detail = ctx.obj.get("detail", "standard")
        if stream:
            click.echo(stream_items(result.items, detail=detail))
            return
        click.echo(format_items(result.items, output_json=ctx.obj.get("json", False), detail=detail))
    finally:
        reader.close()
