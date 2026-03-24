from __future__ import annotations

import click

from zotero_cli_cc.config import get_data_dir, load_config
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_duplicates


@click.command("duplicates")
@click.option(
    "--by",
    "strategy",
    default="both",
    type=click.Choice(["doi", "title", "both"]),
    help="Detection strategy (default: both)",
)
@click.option("--threshold", default=0.85, type=float, help="Title similarity threshold (default: 0.85)")
@click.pass_context
def duplicates_cmd(ctx: click.Context, strategy: str, threshold: float) -> None:
    """Find potential duplicate items in the library.

    \b
    Examples:
      zot duplicates
      zot duplicates --by doi
      zot duplicates --by title --threshold 0.9
      zot --json duplicates
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    reader = ZoteroReader(data_dir / "zotero.sqlite")
    try:
        limit = ctx.obj.get("limit", cfg.default_limit)
        groups = reader.find_duplicates(strategy=strategy, threshold=threshold, limit=limit)
        if not groups:
            if ctx.obj.get("json"):
                click.echo("[]")
            else:
                click.echo("No duplicates found.")
            return
        click.echo(format_duplicates(groups, output_json=ctx.obj.get("json", False)))
    finally:
        reader.close()
