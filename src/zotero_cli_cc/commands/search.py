from __future__ import annotations

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import format_items, format_success, stream_items


@click.command("search")
@click.argument("query")
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
def search_cmd(
    ctx: click.Context,
    query: str,
    collection: str | None,
    item_type: str | None,
    sort: str | None,
    direction: str,
    limit: int | None,
    stream: bool,
) -> None:
    """Search the Zotero library by title, author, tag, or full text.

    \b
    Examples:
      zot search "transformer attention"
      zot search "GAN" --limit 5
      zot --json search "single cell"

    \b
    Filter by Zotero collection (folder):
      zot collection list                        # show available collections
      zot search "BERT" --collection "NLP"       # search within "NLP" collection
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        limit = limit if limit is not None else ctx.obj.get("limit", cfg.default_limit)
        json_out = ctx.obj.get("json", False)
        try:
            result = reader.search(
                query, collection=collection, item_type=item_type, sort=sort, direction=direction, limit=limit
            )
        except ValueError as e:
            emit_error("validation_error", str(e), output_json=json_out)
        detail = ctx.obj.get("detail", "standard")
        if stream:
            click.echo(stream_items(result.items, detail=detail))
            return
        if not result.items:
            if json_out:
                click.echo(format_items([], output_json=True))
            else:
                click.echo("No results found.", err=True)
            return
        click.echo(format_items(result.items, output_json=json_out, detail=detail))
    finally:
        reader.close()
