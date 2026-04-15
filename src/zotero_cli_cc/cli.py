from __future__ import annotations

import os
import sys

import click

from zotero_cli_cc import __version__
from zotero_cli_cc.commands.add import add_cmd
from zotero_cli_cc.commands.attach import attach_cmd
from zotero_cli_cc.commands.cite import cite_cmd
from zotero_cli_cc.commands.collection import collection_group
from zotero_cli_cc.commands.completions import completions_cmd
from zotero_cli_cc.commands.config import config_group
from zotero_cli_cc.commands.delete import delete_cmd
from zotero_cli_cc.commands.duplicates import duplicates_cmd
from zotero_cli_cc.commands.export import export_cmd
from zotero_cli_cc.commands.list_cmd import list_cmd
from zotero_cli_cc.commands.mcp import mcp_group
from zotero_cli_cc.commands.note import note_cmd
from zotero_cli_cc.commands.open_cmd import open_cmd
from zotero_cli_cc.commands.pdf import pdf_cmd
from zotero_cli_cc.commands.read import read_cmd
from zotero_cli_cc.commands.recent import recent_cmd
from zotero_cli_cc.commands.relate import relate_cmd
from zotero_cli_cc.commands.schema import schema_cmd
from zotero_cli_cc.commands.search import search_cmd
from zotero_cli_cc.commands.stats import stats_cmd
from zotero_cli_cc.commands.summarize import summarize_cmd
from zotero_cli_cc.commands.summarize_all import summarize_all_cmd
from zotero_cli_cc.commands.tag import tag_cmd
from zotero_cli_cc.commands.trash import trash_group
from zotero_cli_cc.commands.update import update_cmd
from zotero_cli_cc.commands.update_status import update_status_cmd
from zotero_cli_cc.commands.workspace import workspace_group


@click.group()
@click.version_option(version=__version__, prog_name="zot")
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=None,
    help="Output as JSON (auto-enabled when stdout is not a TTY)",
)
@click.option("--limit", default=50, help="Limit results")
@click.option(
    "--detail", type=click.Choice(["minimal", "standard", "full"]), default="standard", help="Output detail level"
)
@click.option("--no-interaction", is_flag=True, help="Suppress interactive prompts for automation")
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.option("--profile", default=None, help="Config profile name")
@click.option("--library", default="user", help="Library: 'user' (default) or 'group:<id>'")
@click.pass_context
def main(
    ctx: click.Context,
    output_json: bool | None,
    limit: int,
    detail: str,
    no_interaction: bool,
    verbose: bool,
    profile: str | None,
    library: str,
) -> None:
    """zot — Zotero CLI for Claude Code.

    \b
    Quick start:
      zot search "attention mechanism"    Search papers
      zot read ABC123                     View paper details
      zot --json search "BERT"            JSON output for AI
    """
    ctx.ensure_object(dict)
    # TTY auto-detect: when stdout is redirected/piped, default to JSON so agents
    # never have to remember --json. Explicit --json or ZOT_FORMAT env var override.
    if output_json is None:
        env_fmt = os.environ.get("ZOT_FORMAT", "").lower()
        if env_fmt == "json":
            output_json = True
        elif env_fmt in ("table", "text"):
            output_json = False
        else:
            output_json = not sys.stdout.isatty()
    ctx.obj["json"] = output_json
    ctx.obj["limit"] = limit
    ctx.obj["detail"] = detail
    ctx.obj["no_interaction"] = no_interaction
    ctx.obj["verbose"] = verbose
    ctx.obj["profile"] = profile or os.environ.get("ZOT_PROFILE")

    # Parse --library option
    if library == "user":
        ctx.obj["library_type"] = "user"
        ctx.obj["group_id"] = None
    elif library.startswith("group:"):
        group_part = library[6:]
        if not group_part.isdigit():
            raise click.BadParameter(f"Invalid --library format: '{library}'. Use 'user' or 'group:<id>'")
        ctx.obj["library_type"] = "group"
        ctx.obj["group_id"] = group_part
    else:
        raise click.BadParameter(f"Invalid --library format: '{library}'. Use 'user' or 'group:<id>'")


@main.result_callback()
@click.pass_context
def _after_command(ctx: click.Context, *_args: object, **_kwargs: object) -> None:
    """Show update notice after command completes (interactive mode only)."""
    import sys

    obj = ctx.obj or {}
    if obj.get("json") or obj.get("no_interaction") or not sys.stderr.isatty():
        return
    from zotero_cli_cc import __version__
    from zotero_cli_cc.core.version_check import check_for_update

    latest = check_for_update(__version__)
    if latest:
        click.echo(
            click.style(
                f"\n Update available: v{__version__} → v{latest}. "
                f"Run: uv tool upgrade zotero-cli-cc",
                fg="yellow",
            ),
            err=True,
        )


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
main.add_command(cite_cmd, "cite")
main.add_command(completions_cmd, "completions")
main.add_command(recent_cmd, "recent")
main.add_command(update_cmd, "update")
main.add_command(trash_group, "trash")
main.add_command(duplicates_cmd, "duplicates")
main.add_command(attach_cmd, "attach")
main.add_command(update_status_cmd, "update-status")
main.add_command(workspace_group, "workspace")
main.add_command(schema_cmd, "schema")
