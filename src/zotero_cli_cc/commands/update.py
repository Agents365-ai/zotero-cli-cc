from __future__ import annotations

import json
import os

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.formatter import format_error, print_error
from zotero_cli_cc.models import ErrorInfo


@click.command("update")
@click.argument("key")
@click.option("--title", default=None, help="New title")
@click.option("--date", default=None, help="New date (e.g. 2025-01-01)")
@click.option("--field", multiple=True, help="Set field as key=value (repeatable)")
@click.pass_context
def update_cmd(ctx: click.Context, key: str, title: str | None, date: str | None, field: tuple[str, ...]) -> None:
    """Update item metadata fields via the Zotero API.

    \b
    Examples:
      zot update ABC123 --title "New Title"
      zot update ABC123 --date "2025-01-01"
      zot update ABC123 --field volume=42 --field pages=1-10
      zot update ABC123 --title "Title" --field abstractNote="New abstract"
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)

    # Build fields dict
    fields: dict[str, str] = {}
    if title:
        fields["title"] = title
    if date:
        fields["date"] = date
    for f in field:
        if "=" not in f:
            print_error(
                    ErrorInfo(message=f"Invalid field format: '{f}'", context="update", hint="Use key=value format"),
                    output_json=json_out,
                )
            return
        k, v = f.split("=", 1)
        fields[k] = v

    if not fields:
        print_error(
                ErrorInfo(
                    message="No fields to update",
                    context="update",
                    hint="Use --title, --date, or --field key=value",
                ),
                output_json=json_out,
            )
        return

    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        print_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="update",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        return

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        writer.update_item(key, fields)
        if json_out:
            click.echo(json.dumps({"status": "updated", "key": key, "fields": fields}))
        else:
            click.echo(f"Updated {len(fields)} field(s) for '{key}'.")
            click.echo(SYNC_REMINDER)
    except ZoteroWriteError as e:
        print_error(
                ErrorInfo(message=str(e), context="update", hint=f"Failed to update '{key}'"),
                output_json=json_out,
            )
