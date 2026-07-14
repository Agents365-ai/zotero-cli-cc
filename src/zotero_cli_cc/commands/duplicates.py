from __future__ import annotations

import click

from zotero_cli_cc.commands._helpers import open_reader
from zotero_cli_cc.config import load_config
from zotero_cli_cc.exit_codes import EXIT_CONFLICT
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
@click.option("--limit", default=None, type=int, help="Limit results (overrides global --limit)")
@click.pass_context
def duplicates_cmd(ctx: click.Context, strategy: str, threshold: float, limit: int | None) -> None:
    """Find potential duplicate items in the library.

    \b
    Examples:
      zot duplicates
      zot duplicates --by doi
      zot duplicates --by title --threshold 0.9
      zot --json duplicates
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    with open_reader(ctx, cfg) as reader:
        limit = limit if limit is not None else ctx.obj.get("limit", cfg.default_limit)
        groups = reader.find_duplicates(strategy=strategy, threshold=threshold, limit=limit)
        if not groups:
            if ctx.obj.get("json"):
                click.echo("[]")
            else:
                click.echo("No duplicates found.")
            return
        click.echo(format_duplicates(groups, output_json=ctx.obj.get("json", False)))
    # Signal "duplicates detected" via typed exit code so agents/scripts can
    # branch on `if zot duplicates ...; then ...; else act_on_duplicates; fi`.
    ctx.exit(EXIT_CONFLICT)
