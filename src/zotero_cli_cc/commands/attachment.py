from __future__ import annotations

import json

import click

from zotero_cli_cc.config import get_data_dir, get_prefs_js_path, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok
from zotero_cli_cc.models import Attachment


@click.group("attachment")
def attachment_group() -> None:
    """Inspect attachment metadata."""
    pass


@attachment_group.command("path")
@click.argument("item_key")
@click.option(
    "--all",
    "-a",
    "show_all",
    is_flag=True,
    help="List every PDF attachment (e.g. article + appendix), one path per line.",
)
@click.pass_context
def attachment_path(ctx: click.Context, item_key: str, show_all: bool) -> None:
    """Show the local path of a parent item's PDF attachment(s).

    By default prints the first PDF only (one bare path on stdout). Pass --all to
    list every PDF — useful when an item carries an appendix or supplementary file.

    \b
    Examples:
      zot attachment path ABC123            # first PDF
      zot attachment path ABC123 --all      # all PDFs, one per line
      zot --json attachment path ABC123 -a  # all PDFs as a JSON array
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

        pdfs = reader.get_pdf_attachments(item_key)
        if not pdfs:
            emit_error(
                "not_found",
                f"No PDF attachment for '{item_key}'",
                output_json=json_out,
                hint="Check item details with: zot read KEY",
                context="attachment path",
            )

        if show_all:
            _emit_all(item_key, pdfs, json_out)
            return

        _emit_first(item_key, pdfs[0], json_out)
    finally:
        reader.close()


def _emit_first(item_key: str, attachment: Attachment, json_out: bool) -> None:
    pdf_path = attachment.path
    if not pdf_path or not pdf_path.exists():
        emit_error(
            "not_found",
            f"PDF file not found at {pdf_path or attachment.filename}",
            output_json=json_out,
            hint="The file may have been moved or the attachment path could not be resolved. "
            "Check Zotero storage directory. Use --all to list every PDF on the item",
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


def _emit_all(item_key: str, pdfs: list[Attachment], json_out: bool) -> None:
    present = [att for att in pdfs if att.path and att.path.exists()]
    if not present:
        emit_error(
            "not_found",
            f"No local PDF file found for '{item_key}' ({len(pdfs)} attachment(s) recorded)",
            output_json=json_out,
            hint="The files may have been moved or not yet synced to local storage. Check the Zotero storage directory",
            context="attachment path",
        )

    if json_out:
        click.echo(
            json.dumps(
                envelope_ok(
                    {
                        "item_key": item_key,
                        "count": len(present),
                        "attachments": [
                            {
                                "attachment_key": att.key,
                                "path": str(att.path),
                                "filename": att.filename,
                                "exists": True,
                                "mime_type": att.content_type,
                            }
                            for att in present
                        ],
                    }
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    for att in present:
        click.echo(str(att.path))
