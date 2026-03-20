from __future__ import annotations

import click

from zotero_cli_cc import __version__
from zotero_cli_cc.commands.config import config_group


@click.group()
@click.version_option(version=__version__, prog_name="zot")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--limit", default=50, help="Limit results")
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.pass_context
def main(ctx: click.Context, output_json: bool, limit: int, verbose: bool) -> None:
    """zot — Zotero CLI for Claude Code."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["limit"] = limit
    ctx.obj["verbose"] = verbose


main.add_command(config_group, "config")
