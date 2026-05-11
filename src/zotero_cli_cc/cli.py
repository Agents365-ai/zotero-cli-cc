from __future__ import annotations

import os
import sys
from typing import Any

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

# Safety tiers: classifies each command so `zot --help` groups them by risk.
# Agents browsing help see read commands first; mutating and destructive
# commands appear under separate headers so they are not accidentally
# invoked from a generic-looking list.
_READ_COMMANDS = {
    "search",
    "list",
    "read",
    "export",
    "recent",
    "stats",
    "open",
    "cite",
    "pdf",
    "relate",
    "summarize",
    "summarize-all",
    "duplicates",
    "collection",
    "tag",
    "config",
    "completions",
    "mcp",
    "workspace",
    "schema",
    "trash",
}
_WRITE_COMMANDS = {"add", "update", "note", "attach"}
_DESTRUCTIVE_COMMANDS = {"delete", "update-status"}


def _hoist_global_flags(args: list[str]) -> list[str]:
    """Move `--json` / `--no-json` to the front so they parse regardless of position.

    Agents trained on the GNU "flag travels with the subcommand" convention
    write `zot search --json "x"`; without this, Click reports the flag as
    unknown for the subcommand. The two affected tokens are pure flags (no
    value) and are not redefined by any subcommand, so unconditional hoisting
    is safe. Tokens after `--` are left untouched.
    """
    flags: list[str] = []
    rest: list[str] = []
    seen_double_dash = False
    for tok in args:
        if seen_double_dash:
            rest.append(tok)
            continue
        if tok == "--":
            seen_double_dash = True
            rest.append(tok)
            continue
        if tok in ("--json", "--no-json"):
            flags.append(tok)
        else:
            rest.append(tok)
    return flags + rest


class TieredGroup(click.Group):
    """A Click Group that renders the command list grouped by safety tier."""

    def main(  # type: ignore[override]
        self,
        args: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        if args is None:
            args = sys.argv[1:]
        args = _hoist_global_flags(list(args))
        return super().main(args=args, **kwargs)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        commands: list[tuple[str, click.Command]] = []
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or getattr(cmd, "hidden", False):
                continue
            commands.append((name, cmd))

        def rows_for(names: set[str]) -> list[tuple[str, str]]:
            rows = []
            for name, cmd in commands:
                if name in names:
                    rows.append((name, cmd.get_short_help_str(limit=70)))
            return rows

        sections = [
            ("Read commands", rows_for(_READ_COMMANDS)),
            ("Write commands (MUTATES LIBRARY)", rows_for(_WRITE_COMMANDS)),
            ("Destructive commands (MUTATES LIBRARY)", rows_for(_DESTRUCTIVE_COMMANDS)),
        ]
        other = rows_for({n for n, _ in commands} - _READ_COMMANDS - _WRITE_COMMANDS - _DESTRUCTIVE_COMMANDS)
        if other:
            sections.append(("Other", other))

        for title, rows in sections:
            if not rows:
                continue
            with formatter.section(title):
                formatter.write_dl(rows)


@click.group(cls=TieredGroup)
@click.version_option(version=__version__, prog_name="zot")
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=None,
    help="Output as JSON (auto-enabled when stdout is not a TTY)",
)
@click.option(
    "--no-json",
    "output_no_json",
    is_flag=True,
    default=False,
    help="Force human-readable output even when stdout is not a TTY",
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
    output_no_json: bool,
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
    # Bind a request_id + start time for the duration of this invocation so
    # every envelope (success, error, partial) carries them automatically.
    from zotero_cli_cc.formatter import request_scope

    scope = request_scope()
    rid = scope.__enter__()
    ctx.call_on_close(lambda: scope.__exit__(None, None, None))
    ctx.ensure_object(dict)
    ctx.obj["request_id"] = rid
    # Mutual exclusion check: --json and --no-json cannot be used together
    if output_json is not None and output_no_json:
        raise click.BadParameter("Cannot use both --json and --no-json")
    # TTY auto-detect: when stdout is redirected/piped, default to JSON so agents
    # never have to remember --json. Explicit --json, --no-json, or ZOT_FORMAT env var override.
    if output_json is None:
        env_fmt = os.environ.get("ZOT_FORMAT", "").lower()
        if env_fmt == "json":
            output_json = True
        elif env_fmt in ("table", "text"):
            output_json = False
        else:
            output_json = not sys.stdout.isatty()
    # --no-json forces human-readable output regardless of auto-detect
    if output_no_json:
        output_json = False
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
    from zotero_cli_cc.core.version_check import check_for_update, upgrade_command

    latest = check_for_update(__version__)
    if latest:
        click.echo(
            click.style(
                f"\n Update available: v{__version__} → v{latest}. Run: {upgrade_command()}",
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


if __name__ == "__main__":
    main()
