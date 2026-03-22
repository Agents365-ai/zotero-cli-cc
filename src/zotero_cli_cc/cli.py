from __future__ import annotations

import os

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
from zotero_cli_cc.commands.summarize import summarize_cmd
from zotero_cli_cc.commands.summarize_all import summarize_all_cmd
from zotero_cli_cc.commands.pdf import pdf_cmd
from zotero_cli_cc.commands.relate import relate_cmd
from zotero_cli_cc.commands.mcp import mcp_group
from zotero_cli_cc.commands.stats import stats_cmd
from zotero_cli_cc.commands.open_cmd import open_cmd
from zotero_cli_cc.commands.completions import completions_cmd


@click.group()
@click.version_option(version=__version__, prog_name="zot")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--limit", default=50, help="Limit results")
@click.option("--detail", type=click.Choice(["minimal", "standard", "full"]), default="standard", help="Output detail level")
@click.option("--no-interaction", is_flag=True, help="Suppress interactive prompts for automation")
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.option("--profile", default=None, help="Config profile name")
@click.pass_context
def main(ctx: click.Context, output_json: bool, limit: int, detail: str, no_interaction: bool, verbose: bool, profile: str | None) -> None:
    """zot — Zotero CLI for Claude Code."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["limit"] = limit
    ctx.obj["detail"] = detail
    ctx.obj["no_interaction"] = no_interaction
    ctx.obj["verbose"] = verbose
    ctx.obj["profile"] = profile or os.environ.get("ZOT_PROFILE")


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
main.add_command(summarize_cmd, "summarize")
main.add_command(summarize_all_cmd, "summarize-all")
main.add_command(pdf_cmd, "pdf")
main.add_command(relate_cmd, "relate")
main.add_command(mcp_group, "mcp")
main.add_command(stats_cmd, "stats")
main.add_command(open_cmd, "open")
main.add_command(completions_cmd, "completions")
