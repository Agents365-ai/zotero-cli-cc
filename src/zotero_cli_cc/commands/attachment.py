from __future__ import annotations

import json

import click

from zotero_cli_cc.config import get_data_dir, get_prefs_js_path, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok


@click.group("attachment")
def attachment_group() -> None:
    """Inspect attachment metadata."""
    pass


@attachment_group.command("path")
@click.argument("item_key")
@click.pass_context
def attachment_path(ctx: click.Context, item_key: str) -> None:
    """Show the local path of the first PDF attachment for a parent item.

    \b
    Examples:
      zot attachment path ABC123
      zot --json attachment path ABC123
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    db_path = get_data_dir(cfg) / "zotero.sqlite"
    reader = ZoteroReader(
        db_path,
        library_id=resolve_library_id(db_path, ctx.obj),
        prefs_js_path=get_prefs_js_path(cfg),
    )
    try:
        if reader.get_item(item_key) is None:
            emit_error(
                "not_found",
                f"Item '{item_key}' not found",
                output_json=json_out,
                hint="Run 'zot search' to find valid item keys",
                context="attachment path",
            )

        attachment = reader.get_pdf_attachment(item_key)
        if attachment is None:
            emit_error(
                "not_found",
                f"No PDF attachment for '{item_key}'",
                output_json=json_out,
                hint="Check item details with: zot read KEY",
                context="attachment path",
            )

        pdf_path = attachment.path
        if not pdf_path or not pdf_path.exists():
            emit_error(
                "not_found",
                f"PDF file not found at {pdf_path or attachment.filename}",
                output_json=json_out,
                hint="The file may have been moved or the attachment path could not be resolved. "
                "Check Zotero storage directory",
                context="attachment path",
            )

        if json_out:
            click.echo(
                json.dumps(
                    envelope_ok(
                        {
                            "item_key": item_key,
                            "attachment_key": attachment.key,
                            "path": str(pdf_path),
                            "filename": attachment.filename,
                            "exists": True,
                            "mime_type": attachment.content_type,
                        }
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return

        click.echo(str(pdf_path))
    finally:
        reader.close()
