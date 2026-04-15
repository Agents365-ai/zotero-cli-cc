from __future__ import annotations

import json
import os
from pathlib import Path

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok, envelope_partial


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
        emit_error(
            "auth_missing",
            "Write credentials not configured",
            output_json=json_out,
            hint="Run 'zot config init' to set up API credentials",
            context="add",
        )

    if pdf_file:
        _add_from_pdf(Path(pdf_file), doi, library_id, api_key, json_out, library_type=library_type)
        return

    if from_file:
        _add_from_file(Path(from_file), library_id, api_key, json_out, library_type=library_type)
        return

    if not doi and not url:
        emit_error(
            "validation_error",
            "Provide --doi, --url, or --from-file",
            output_json=json_out,
            hint="Example: zot add --doi '10.1038/...' or --from-file dois.txt",
            context="add",
        )

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        key = writer.add_item(doi=doi, url=url)
    except ZoteroWriteError as e:
        emit_error("api_error", str(e), output_json=json_out, retryable=True, hint="Check API credentials and network", context="add")
    if json_out:
        click.echo(json.dumps(envelope_ok({"key": key, "doi": doi, "url": url, "sync_required": True}), indent=2, ensure_ascii=False))
    else:
        click.echo(f"Item added: {key}")
        click.echo(SYNC_REMINDER, err=True)


def _add_from_pdf(
    pdf_path: Path, doi_override: str | None, library_id: str, api_key: str, json_out: bool, library_type: str = "user"
) -> None:
    """Add item from PDF: extract DOI, create item, upload attachment."""
    from zotero_cli_cc.core.pdf_extractor import extract_doi

    doi = doi_override
    if not doi:
        doi = extract_doi(pdf_path)
    if not doi:
        emit_error(
            "validation_error",
            "No DOI found in PDF",
            output_json=json_out,
            hint="Use --doi to specify the DOI manually: zot add --pdf paper.pdf --doi '10.1234/...'",
            context="add",
        )

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        key = writer.add_item(doi=doi)
    except ZoteroWriteError as e:
        emit_error("api_error", str(e), output_json=json_out, retryable=True, context="add")

    att_key = None
    attach_error: str | None = None
    try:
        att_key = writer.upload_attachment(key, pdf_path)
    except ZoteroWriteError as e:
        attach_error = str(e)

    if json_out:
        data: dict = {"key": key, "doi": doi, "sync_required": True}
        if att_key:
            data["attachment_key"] = att_key
        if attach_error:
            data["attachment_error"] = attach_error
            data["next"] = [f"zot attach {key} --file {pdf_path}"]
        click.echo(json.dumps(envelope_ok(data), indent=2, ensure_ascii=False))
    else:
        click.echo(f"Item created: {key} (DOI: {doi})")
        if att_key:
            click.echo(f"Attachment uploaded: {att_key}")
            click.echo(SYNC_REMINDER, err=True)
            click.echo("Note: Zotero API creates bare items. Sync and use Zotero desktop to retrieve full metadata.", err=True)
        else:
            click.echo(f"Item created ({key}) but attachment upload failed: {attach_error}", err=True)
            click.echo(f"Retry with: zot attach {key} --file {pdf_path}", err=True)


def _add_from_file(file_path: Path, library_id: str, api_key: str, json_out: bool, library_type: str = "user") -> None:
    """Batch add items from a file with one DOI or URL per line."""
    lines = [line.strip() for line in file_path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        emit_error(
            "validation_error",
            "File is empty or has no valid entries",
            output_json=json_out,
            hint="One DOI or URL per line",
            context="add",
        )

    if not json_out:
        click.echo(f"Adding {len(lines)} items from {file_path}...", err=True)
    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    succeeded: list[dict] = []
    failed: list[dict] = []
    for i, entry in enumerate(lines, 1):
        is_doi = not entry.startswith("http")
        try:
            if is_doi:
                key = writer.add_item(doi=entry)
            else:
                key = writer.add_item(url=entry)
            succeeded.append({"entry": entry, "key": key})
            if not json_out:
                click.echo(f"  [{i}/{len(lines)}] Added: {key} ({entry})", err=True)
        except ZoteroWriteError as e:
            failed.append(
                {
                    "entry": entry,
                    "error": {"code": "api_error", "message": str(e), "retryable": True},
                }
            )
            if not json_out:
                click.echo(f"  [{i}/{len(lines)}] Failed: {entry} ({e})", err=True)

    if json_out:
        env = envelope_partial(succeeded, failed, meta={"total": len(lines), "sync_required": bool(succeeded)})
        if not failed:
            env["ok"] = True
            env["data"] = {"succeeded": succeeded, "failed": []}
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        return

    click.echo(f"\nDone: {len(succeeded)} added, {len(failed)} failed", err=True)
    if succeeded:
        click.echo(SYNC_REMINDER, err=True)
