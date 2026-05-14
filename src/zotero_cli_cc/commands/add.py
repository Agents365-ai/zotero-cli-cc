from __future__ import annotations

import json
import os
from pathlib import Path

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.metadata_resolver import MetadataResolveError, resolve_doi
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import emit_progress, envelope_ok, envelope_partial


def _resolve_metadata(doi: str) -> tuple[dict | None, str | None]:
    """Resolve DOI → Zotero fields via Crossref. Returns (fields, warning).

    On success: (fields_dict, None). On miss: (None, "no_match"). On error:
    (None, "<error message>"). The caller is responsible for surfacing the
    warning; resolution never aborts the add, the item is still created (bare
    or partially populated) so retries don't lose work.
    """
    try:
        fields = resolve_doi(doi)
    except MetadataResolveError as e:
        return None, str(e)
    if fields is None:
        return None, "no_match"
    return fields, None


def _resolved_summary(fields: dict) -> dict:
    """Compact summary of the resolved metadata for JSON envelopes / human output."""
    summary: dict = {}
    if "title" in fields:
        summary["title"] = fields["title"]
    creators = fields.get("creators") or []
    if creators:
        first = creators[0]
        last = first.get("lastName") or first.get("name") or ""
        suffix = " et al." if len(creators) > 1 else ""
        summary["author"] = f"{last}{suffix}".strip()
    if "publicationTitle" in fields:
        summary["journal"] = fields["publicationTitle"]
    if "date" in fields:
        summary["date"] = fields["date"]
    return summary


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
@click.option("--dry-run", is_flag=True, help="Preview what would be added without calling the API")
@click.option("--idempotency-key", default=None, help="Key so retries are safe; same key returns the original result")
@click.option(
    "--no-resolve",
    "no_resolve",
    is_flag=True,
    help="Skip Crossref DOI metadata lookup (faster, but creates a bare item)",
)
@click.pass_context
def add_cmd(
    ctx: click.Context,
    doi: str | None,
    url: str | None,
    from_file: str | None,
    pdf_file: str | None,
    dry_run: bool,
    idempotency_key: str | None,
    no_resolve: bool,
) -> None:
    """Add items to the Zotero library via DOI, URL, batch file, or PDF. MUTATES LIBRARY.

    For --doi inputs, metadata (title, authors, journal, year, ...) is
    fetched from Crossref before posting so the created item is not a bare
    shell. Pass --no-resolve to skip the lookup. Requires API credentials
    (run 'zot config init' first).

    \b
    Examples:
      zot add --doi "10.1038/s41586-023-06139-9"
      zot add --doi "10.1038/s41586-023-06139-9" --no-resolve   # skip Crossref
      zot add --url "https://arxiv.org/abs/2301.00001"
      zot add --from-file dois.txt
      zot add --pdf paper.pdf
      zot add --pdf paper.pdf --doi "10.1234/override"
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)

    if dry_run:
        would: dict = {}
        if pdf_file:
            would = {"source": "pdf", "pdf": str(pdf_file), "doi_override": doi, "resolve_metadata": not no_resolve}
        elif from_file:
            would = {"source": "file", "path": str(from_file), "resolve_metadata": not no_resolve}
        elif doi:
            would = {"source": "doi", "doi": doi, "resolve_metadata": not no_resolve}
        elif url:
            would = {"source": "url", "url": url}
        else:
            emit_error(
                "validation_error",
                "Provide --doi, --url, --from-file, or --pdf",
                output_json=json_out,
                hint="Example: zot add --doi '10.1038/...' --dry-run",
                context="add",
            )
        if json_out:
            click.echo(json.dumps(envelope_ok({"would": would}, extra={"dry_run": True}), indent=2, ensure_ascii=False))
        else:
            click.echo(f"[dry-run] Would add: {would}")
        return

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
        _add_from_pdf(
            Path(pdf_file), doi, library_id, api_key, json_out, library_type=library_type, resolve=not no_resolve
        )
        return

    if from_file:
        _add_from_file(
            Path(from_file), library_id, api_key, json_out, library_type=library_type, resolve=not no_resolve
        )
        return

    if not doi and not url:
        emit_error(
            "validation_error",
            "Provide --doi, --url, or --from-file",
            output_json=json_out,
            hint="Example: zot add --doi '10.1038/...' or --from-file dois.txt",
            context="add",
        )

    from zotero_cli_cc.core.idempotency import get_cached, store_cached

    cache_scope = f"add:{'doi:' + doi if doi else 'url:' + (url or '')}"
    if idempotency_key:
        cached = get_cached(cache_scope, idempotency_key)
        if cached is not None:
            if json_out:
                click.echo(json.dumps(cached, indent=2, ensure_ascii=False))
            else:
                click.echo(f"Item added: {cached.get('data', {}).get('key', '?')} (cached).")
            return

    extra_fields: dict | None = None
    resolved_summary: dict | None = None
    resolve_warning: str | None = None
    if doi and not no_resolve:
        extra_fields, resolve_warning = _resolve_metadata(doi)
        if extra_fields:
            resolved_summary = _resolved_summary(extra_fields)
            if not json_out:
                bits = [f"Resolved via Crossref: {resolved_summary.get('title', '(no title)')}"]
                meta = " · ".join(
                    v
                    for v in (
                        resolved_summary.get("author"),
                        resolved_summary.get("journal"),
                        resolved_summary.get("date"),
                    )
                    if v
                )
                if meta:
                    bits.append(f"  {meta}")
                click.echo("\n".join(bits), err=True)
        elif not json_out:
            if resolve_warning == "no_match":
                click.echo("Crossref has no record for this DOI — creating a bare item (no metadata).", err=True)
            else:
                click.echo(
                    f"Could not resolve metadata via Crossref ({resolve_warning}); creating bare item.",
                    err=True,
                )

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        key = writer.add_item(doi=doi, url=url, extra_fields=extra_fields)
    except ZoteroWriteError as e:
        emit_error(
            e.code,
            str(e),
            output_json=json_out,
            retryable=e.retryable,
            hint="Check API credentials and network",
            context="add",
        )
    data: dict = {"key": key, "doi": doi, "url": url, "sync_required": True}
    if resolved_summary is not None:
        data["resolved"] = resolved_summary
    elif doi and not no_resolve:
        data["resolved"] = None
        data["resolve_warning"] = resolve_warning
    env = envelope_ok(
        data,
        extra={"next": [f"zot read {key}", f"zot attach {key} --file <path>"]},
    )
    if idempotency_key:
        store_cached(cache_scope, idempotency_key, env)
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Item added: {key}")
        click.echo(SYNC_REMINDER, err=True)


def _add_from_pdf(
    pdf_path: Path,
    doi_override: str | None,
    library_id: str,
    api_key: str,
    json_out: bool,
    library_type: str = "user",
    resolve: bool = True,
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

    extra_fields: dict | None = None
    resolved_summary: dict | None = None
    resolve_warning: str | None = None
    if doi and resolve:
        extra_fields, resolve_warning = _resolve_metadata(doi)
        if extra_fields:
            resolved_summary = _resolved_summary(extra_fields)

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        key = writer.add_item(doi=doi, extra_fields=extra_fields)
    except ZoteroWriteError as e:
        emit_error(e.code, str(e), output_json=json_out, retryable=e.retryable, context="add")

    att_key = None
    attach_error: str | None = None
    try:
        att_key = writer.upload_attachment(key, pdf_path)
    except ZoteroWriteError as e:
        attach_error = str(e)

    if json_out:
        data: dict = {"key": key, "doi": doi, "sync_required": True}
        if resolved_summary is not None:
            data["resolved"] = resolved_summary
        elif resolve:
            data["resolved"] = None
            data["resolve_warning"] = resolve_warning
        if att_key:
            data["attachment_key"] = att_key
        if attach_error:
            data["attachment_error"] = attach_error
            data["next"] = [f"zot attach {key} --file {pdf_path}"]
        click.echo(json.dumps(envelope_ok(data), indent=2, ensure_ascii=False))
    else:
        click.echo(f"Item created: {key} (DOI: {doi})")
        if resolved_summary:
            meta = " · ".join(
                v
                for v in (resolved_summary.get("author"), resolved_summary.get("journal"), resolved_summary.get("date"))
                if v
            )
            click.echo(f"  {resolved_summary.get('title', '')}", err=True)
            if meta:
                click.echo(f"  {meta}", err=True)
        elif resolve and resolve_warning:
            if resolve_warning == "no_match":
                click.echo("Crossref has no record for this DOI — item created without metadata.", err=True)
            else:
                click.echo(f"Crossref lookup failed ({resolve_warning}); item created without metadata.", err=True)
        if att_key:
            click.echo(f"Attachment uploaded: {att_key}")
            click.echo(SYNC_REMINDER, err=True)
        else:
            click.echo(f"Item created ({key}) but attachment upload failed: {attach_error}", err=True)
            click.echo(f"Retry with: zot attach {key} --file {pdf_path}", err=True)


def _add_from_file(
    file_path: Path,
    library_id: str,
    api_key: str,
    json_out: bool,
    library_type: str = "user",
    resolve: bool = True,
) -> None:
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

    emit_progress("start", phase="batch_add", total=len(lines), source=str(file_path))
    if not json_out:
        click.echo(f"Adding {len(lines)} items from {file_path}...", err=True)
    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    succeeded: list[dict] = []
    failed: list[dict] = []
    for i, entry in enumerate(lines, 1):
        emit_progress("progress", phase="batch_add", done=i - 1, total=len(lines))
        is_doi = not entry.startswith("http")
        try:
            if is_doi:
                extra_fields: dict | None = None
                resolved_summary: dict | None = None
                resolve_warning: str | None = None
                if resolve:
                    extra_fields, resolve_warning = _resolve_metadata(entry)
                    if extra_fields:
                        resolved_summary = _resolved_summary(extra_fields)
                key = writer.add_item(doi=entry, extra_fields=extra_fields)
                row: dict = {"entry": entry, "key": key}
                if resolved_summary is not None:
                    row["resolved"] = resolved_summary
                elif resolve:
                    row["resolved"] = None
                    row["resolve_warning"] = resolve_warning
                succeeded.append(row)
            else:
                key = writer.add_item(url=entry)
                succeeded.append({"entry": entry, "key": key})
            if not json_out:
                click.echo(f"  [{i}/{len(lines)}] Added: {key} ({entry})", err=True)
        except ZoteroWriteError as e:
            failed.append(
                {
                    "entry": entry,
                    "error": {"code": e.code, "message": str(e), "retryable": e.retryable},
                }
            )
            if not json_out:
                click.echo(f"  [{i}/{len(lines)}] Failed: {entry} ({e})", err=True)

    emit_progress(
        "complete", phase="batch_add", done=len(lines), total=len(lines), succeeded=len(succeeded), failed=len(failed)
    )
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
