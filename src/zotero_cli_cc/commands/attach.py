from __future__ import annotations

import os
from pathlib import Path

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.formatter import format_error
from zotero_cli_cc.models import ErrorInfo


@click.command("attach")
@click.argument("key")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="File to upload")
@click.pass_context
def attach_cmd(ctx: click.Context, key: str, file_path: str) -> None:
    """Upload a file attachment to an existing Zotero item.

    \b
    Examples:
      zot attach ABC123 --file paper.pdf
      zot attach ABC123 --file ~/Downloads/supplement.pdf
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        click.echo(
            format_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="attach",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        )
        return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        att_key = writer.upload_attachment(key, Path(file_path))
        click.echo(f"Attachment uploaded: {att_key}")
        click.echo(SYNC_REMINDER)
    except ZoteroWriteError as e:
        click.echo(
            format_error(
                ErrorInfo(message=str(e), context="attach", hint="Check the item key and file path"),
                output_json=json_out,
            )
        )
