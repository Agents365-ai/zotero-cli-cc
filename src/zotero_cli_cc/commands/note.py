from __future__ import annotations

import os

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.formatter import format_error, format_notes, print_error
from zotero_cli_cc.models import ErrorInfo


@click.command("note")
@click.argument("key")
@click.option("--add", "content", default=None, help="Add a new note")
@click.pass_context
def note_cmd(ctx: click.Context, key: str, content: str | None) -> None:
    """View or add notes for an item.

    \b
    Examples:
      zot note ABC123                            View notes
      zot note ABC123 --add "Key finding: ..."   Add a note
      zot --json note ABC123                     JSON output
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)

    if content:
        # Write mode
        library_id: str | int | None = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
        api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
        library_type = ctx.obj.get("library_type", "user")
        if library_type == "group" and ctx.obj.get("group_id"):
            library_id = ctx.obj["group_id"]
        if not library_id or not api_key:
            print_error(
                    ErrorInfo(
                        message="Write credentials not configured",
                        context="note",
                        hint="Run 'zot config init' to set up API credentials",
                    ),
                    output_json=json_out,
                )
            return
        writer = ZoteroWriter(library_id=str(library_id), api_key=api_key, library_type=library_type)
        try:
            note_key = writer.add_note(key, content)
            click.echo(f"Note added: {note_key}")
            click.echo(SYNC_REMINDER)
        except ZoteroWriteError as e:
            print_error(
                    ErrorInfo(message=str(e), context="note", hint="Check item key and API credentials"),
                    output_json=json_out,
                )
    else:
        # Read mode
        data_dir = get_data_dir(cfg)
        db_path = data_dir / "zotero.sqlite"
        library_id = resolve_library_id(db_path, ctx.obj)
        reader = ZoteroReader(db_path, library_id=library_id)
        try:
            notes = reader.get_notes(key)
            if not notes:
                print_error(
                        ErrorInfo(
                            message=f"No notes found for '{key}'",
                            context="note",
                            hint="Add one with: zot note KEY --add 'content'",
                        ),
                        output_json=json_out,
                    )
                return
            click.echo(format_notes(notes, output_json=json_out))
        finally:
            reader.close()
