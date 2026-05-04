from __future__ import annotations

import json

import click

from zotero_cli_cc.config import get_data_dir, get_prefs_js_path, load_config, resolve_library_id
from zotero_cli_cc.core.pdf_extractor import BasePdfExtractor, PdfExtractionError, get_extractor
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import print_error
from zotero_cli_cc.models import ErrorInfo


@click.command("pdf")
@click.argument("key")
@click.option("--pages", default=None, help="Page range, e.g. '1-5'")
@click.option("--extractor", default=None, help="PDF extractor to use (mineru, pymupdf). Defaults to auto-detect.")
@click.option("--annotations", is_flag=True, help="Extract annotations (highlights, notes) instead of text")
@click.pass_context
def pdf_cmd(ctx: click.Context, key: str, pages: str | None, extractor: str | None, annotations: bool) -> None:
    """Extract text from the PDF attachment.

    Full text is cached locally for fast repeated access.

    \b
    Examples:
      zot pdf ABC123                Extract full text
      zot pdf ABC123 --pages 1-5    Extract pages 1-5
      zot --json pdf ABC123         JSON output with metadata
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    page_range = None
    if extractor is None:
        from zotero_cli_cc.config import load_pdf_config
        extractor = load_pdf_config().extractor
    if pages:
        try:
            parts = pages.split("-")
            start = int(parts[0])
            end = int(parts[1]) if len(parts) > 1 else start
            if start < 1 or end < start:
                raise ValueError(f"invalid range: start={start}, end={end}")
            page_range = (start, end)
        except ValueError:
            print_error(
                ErrorInfo(
                    message=f"Invalid page range '{pages}'",
                    context="pdf",
                    hint="Use format: '1-5' or '3' for a single page",
                ),
                output_json=json_out,
            )
            return
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id, prefs_js_path=get_prefs_js_path(cfg))
    try:
        att = reader.get_pdf_attachment(key)
        if att is None:
            print_error(
                ErrorInfo(
                    message=f"No PDF attachment found for '{key}'",
                    context="pdf",
                    hint="Check item details with: zot read KEY",
                ),
                output_json=json_out,
            )
            return
        pdf_path = att.path
        if not pdf_path or not pdf_path.exists():
            print_error(
                ErrorInfo(
                    message=f"PDF file not found at {pdf_path or att.filename}",
                    context="pdf",
                    hint="The file may have been moved or the attachment path could not be resolved. Check Zotero storage directory",
                ),
                output_json=json_out,
            )
            return
        if annotations:
            from zotero_cli_cc.core.pdf_extractor import extract_annotations

            try:
                annots = extract_annotations(pdf_path)
            except PdfExtractionError as e:
                print_error(ErrorInfo(message=str(e), context="pdf"), output_json=json_out)
                return
            if not annots:
                if json_out:
                    click.echo("[]")
                else:
                    click.echo("No annotations found.")
                return
            if json_out:
                click.echo(json.dumps(annots, ensure_ascii=False, indent=2))
            else:
                for a in annots:
                    line = f"[p.{a['page']}] {a['type']}"
                    if a.get("quote"):
                        line += f': "{a["quote"]}"'
                    if a.get("content"):
                        line += f" -- {a['content']}"
                    click.echo(line)
            return
        from zotero_cli_cc.core.pdf_cache import PdfCache

        cache = PdfCache()
        try:
            if page_range is None:
                cached = cache.get(pdf_path, extractor)
                if cached is not None:
                    text = cached
                else:
                    pdf_extractor = get_extractor(extractor)
                    try:
                        text = pdf_extractor.extract_text(pdf_path)
                        cache.put(pdf_path, extractor, text)
                    except PdfExtractionError:
                        if extractor == "mineru":
                            pdf_extractor = get_extractor("pymupdf")
                            text = pdf_extractor.extract_text(pdf_path)
                            cache.put(pdf_path, "pymupdf", text)
                        else:
                            raise
            else:
                pdf_extractor = get_extractor(extractor)
                try:
                    text = pdf_extractor.extract_text(pdf_path, pages=page_range)
                except PdfExtractionError:
                    if extractor == "mineru":
                        pdf_extractor = get_extractor("pymupdf")
                        text = pdf_extractor.extract_text(pdf_path, pages=page_range)
                    else:
                        raise
        except PdfExtractionError as e:
            cache.close()
            print_error(
                ErrorInfo(message=str(e), context="pdf", hint="The PDF may be corrupted or password-protected"),
                output_json=json_out,
            )
            return
        cache.close()
        if json_out:
            click.echo(json.dumps({"key": key, "pages": pages, "text": text}, ensure_ascii=False))
        else:
            click.echo(text)
    finally:
        reader.close()
