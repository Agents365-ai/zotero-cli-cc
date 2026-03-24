from __future__ import annotations

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_items


@click.command("search")
@click.argument("query")
@click.option("--collection", default=None, help="Filter by collection name")
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
@click.pass_context
def search_cmd(
    ctx: click.Context,
    query: str,
    collection: str | None,
    item_type: str | None,
    sort: str | None,
    direction: str,
) -> None:
    """Search the Zotero library by title, author, tag, or full text.

    \b
    Examples:
      zot search "transformer attention"
      zot search "BERT" --collection "NLP"
      zot --json search "single cell"
      zot --detail minimal search "GAN"
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        limit = ctx.obj.get("limit", cfg.default_limit)
        result = reader.search(
            query, collection=collection, item_type=item_type, sort=sort, direction=direction, limit=limit
        )
        if not result.items:
            if ctx.obj.get("json"):
                click.echo("[]")
            else:
                click.echo("No results found.")
            return
        detail = ctx.obj.get("detail", "standard")
        click.echo(format_items(result.items, output_json=ctx.obj.get("json", False), detail=detail))
    finally:
        reader.close()
