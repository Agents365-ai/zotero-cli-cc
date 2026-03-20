from __future__ import annotations

import click

from zotero_cli_cc import __version__
from zotero_cli_cc.commands.config import config_group
from zotero_cli_cc.commands.search import search_cmd
from zotero_cli_cc.commands.list_cmd import list_cmd
from zotero_cli_cc.commands.read import read_cmd
from zotero_cli_cc.commands.export import export_cmd
from zotero_cli_cc.commands.note import note_cmd
from zotero_cli_cc.commands.add import add_cmd
from zotero_cli_cc.commands.delete import delete_cmd
from zotero_cli_cc.commands.tag import tag_cmd
from zotero_cli_cc.commands.collection import collection_group


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
main.add_command(search_cmd, "search")
main.add_command(list_cmd, "list")
main.add_command(read_cmd, "read")
main.add_command(export_cmd, "export")
main.add_command(note_cmd, "note")
main.add_command(add_cmd, "add")
main.add_command(delete_cmd, "delete")
main.add_command(tag_cmd, "tag")
main.add_command(collection_group, "collection")
