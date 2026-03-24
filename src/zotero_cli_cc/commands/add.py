from __future__ import annotations

import os
from pathlib import Path

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.formatter import format_error
from zotero_cli_cc.models import ErrorInfo


@click.command("add")
@click.option("--doi", default=None, help="DOI to add")
@click.option("--url", default=None, help="URL to add")
@click.option(
    "--from-file",
    "from_file",
    default=None,
    type=click.Path(exists=True),
    help="File with one DOI or URL per line",
)
@click.option(
    "--pdf",
    "pdf_file",
    default=None,
    type=click.Path(exists=True),
    help="PDF file to extract DOI from and attach (metadata not auto-resolved by API)",
)
@click.pass_context
def add_cmd(ctx: click.Context, doi: str | None, url: str | None, from_file: str | None, pdf_file: str | None) -> None:
    """Add items to the Zotero library via DOI, URL, batch file, or PDF.

    Requires API credentials (run 'zot config init' first).

    \b
    Examples:
      zot add --doi "10.1038/s41586-023-06139-9"
      zot add --url "https://arxiv.org/abs/2301.00001"
      zot add --from-file dois.txt
      zot add --pdf paper.pdf
      zot add --pdf paper.pdf --doi "10.1234/override"
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
                    context="add",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        )
        return

    if pdf_file:
        _add_from_pdf(Path(pdf_file), doi, library_id, api_key, json_out, library_type=library_type)
        return

    if from_file:
        _add_from_file(Path(from_file), library_id, api_key, json_out, library_type=library_type)
        return

    if not doi and not url:
        click.echo(
            format_error(
                ErrorInfo(
                    message="Provide --doi, --url, or --from-file",
                    context="add",
                    hint="Example: zot add --doi '10.1038/...' or --from-file dois.txt",
                ),
                output_json=json_out,
            )
        )
        return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        key = writer.add_item(doi=doi, url=url)
        click.echo(f"Item added: {key}")
        click.echo(SYNC_REMINDER)
    except ZoteroWriteError as e:
        click.echo(
            format_error(
                ErrorInfo(message=str(e), context="add", hint="Check API credentials and network"), output_json=json_out
            )
        )


def _add_from_pdf(
    pdf_path: Path, doi_override: str | None, library_id: str, api_key: str, json_out: bool, library_type: str = "user"
) -> None:
    """Add item from PDF: extract DOI, create item, upload attachment."""
    from zotero_cli_cc.core.pdf_extractor import extract_doi

    doi = doi_override
    if not doi:
        doi = extract_doi(pdf_path)
    if not doi:
        click.echo(
            format_error(
                ErrorInfo(
                    message="No DOI found in PDF",
                    context="add",
                    hint="Use --doi to specify the DOI manually: zot add --pdf paper.pdf --doi '10.1234/...'",
                ),
                output_json=json_out,
            )
        )
        return

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        key = writer.add_item(doi=doi)
        click.echo(f"Item created: {key} (DOI: {doi})")
    except ZoteroWriteError as e:
        click.echo(format_error(ErrorInfo(message=str(e), context="add"), output_json=json_out))
        return

    try:
        att_key = writer.upload_attachment(key, pdf_path)
        click.echo(f"Attachment uploaded: {att_key}")
        click.echo(SYNC_REMINDER)
        click.echo("Note: Zotero API creates bare items. Sync and use Zotero desktop to retrieve full metadata.")
    except ZoteroWriteError as e:
        click.echo(f"Item created ({key}) but attachment upload failed: {e}")
        click.echo(f"Retry with: zot attach {key} --file {pdf_path}")


def _add_from_file(file_path: Path, library_id: str, api_key: str, json_out: bool, library_type: str = "user") -> None:
    """Batch add items from a file with one DOI or URL per line."""
    lines = [line.strip() for line in file_path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        click.echo(
            format_error(
                ErrorInfo(
                    message="File is empty or has no valid entries", context="add", hint="One DOI or URL per line"
                ),
                output_json=json_out,
            )
        )
        return

    click.echo(f"Adding {len(lines)} items from {file_path}...")
    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    added = 0
    failed = 0
    for i, entry in enumerate(lines, 1):
        is_doi = not entry.startswith("http")
        try:
            if is_doi:
                key = writer.add_item(doi=entry)
            else:
                key = writer.add_item(url=entry)
            click.echo(f"  [{i}/{len(lines)}] Added: {key} ({entry})")
            added += 1
        except ZoteroWriteError as e:
            click.echo(f"  [{i}/{len(lines)}] Failed: {entry} ({e})")
            failed += 1

    click.echo(f"\nDone: {added} added, {failed} failed")
    if added > 0:
        click.echo(SYNC_REMINDER)
