from __future__ import annotations

import json

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.pdf_extractor import extract_text_from_pdf
from zotero_cli_cc.formatter import format_error


@click.command("pdf")
@click.argument("key")
@click.option("--pages", default=None, help="Page range, e.g. '1-5'")
@click.pass_context
def pdf_cmd(ctx: click.Context, key: str, pages: str | None) -> None:
    """Extract text from the PDF attachment."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)
    page_range = None
    if pages:
        try:
            parts = pages.split("-")
            start = int(parts[0])
            end = int(parts[1]) if len(parts) > 1 else start
            if start < 1 or end < start:
                raise ValueError(f"invalid range: start={start}, end={end}")
            page_range = (start, end)
        except ValueError:
            click.echo(format_error(f"Invalid page range '{pages}'. Use e.g. '1-5'", output_json=json_out))
            return
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    try:
        att = reader.get_pdf_attachment(key)
        if att is None:
            click.echo(format_error(f"No PDF attachment found for '{key}'", output_json=json_out))
            return
        pdf_path = data_dir / "storage" / att.key / att.filename
        if not pdf_path.exists():
            click.echo(format_error(f"PDF file not found at {pdf_path}", output_json=json_out))
            return
        text = extract_text_from_pdf(pdf_path, pages=page_range)
        if json_out:
            click.echo(json.dumps({"key": key, "pages": pages, "text": text}, ensure_ascii=False))
        else:
            click.echo(text)
    finally:
        reader.close()
