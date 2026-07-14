from __future__ import annotations

import json
import re

import click

from zotero_cli_cc.commands._helpers import open_reader
from zotero_cli_cc.core.pdf_extractor import PdfExtractionError, get_extractor
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import format_pdf_annotations, format_pdf_text


def _parse_outline(markdown: str) -> list[tuple[int, str, int]]:
    """Parse markdown headings and return numbered outline.

    Returns:
        List of tuples: (sequential_number, heading_text, level)
        where level is 1-6 for # to ######
    """
    pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    outline: list[tuple[int, str, int]] = []
    seq_num = 0
    for match in pattern.finditer(markdown):
        hashes, text = match.groups()
        level = len(hashes)
        seq_num += 1
        outline.append((seq_num, text.strip(), level))
    return outline


def _extract_section(markdown: str, section_num: int) -> str:
    """Extract content under the N-th heading.

    Args:
        markdown: Full markdown text
        section_num: 1-based section number from outline

    Returns:
        Content from that heading until the next heading of equal or higher level.
        Returns empty string if section_num is out of range.
    """
    pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(markdown))

    if section_num < 1 or section_num > len(matches):
        return ""

    target_match = matches[section_num - 1]
    target_level = len(target_match.group(1))
    target_start = target_match.start()

    # Find the next heading of same or higher level
    end_pos = len(markdown)
    for match in matches[section_num:]:
        level = len(match.group(1))
        if level <= target_level:
            end_pos = match.start()
            break

    return markdown[target_start:end_pos].strip()


@click.command("pdf")
@click.option("--pages", default=None, help="Page range, e.g. '1-5'")
@click.option("--extractor", default=None, help="PDF extractor to use (mineru, pymupdf). Defaults to auto-detect.")
@click.option("--annotations", is_flag=True, help="Extract annotations (highlights, notes) instead of text")
@click.option(
    "--references",
    is_flag=True,
    help="Extract the parsed reference list (requires a running GROBID service)",
)
@click.option(
    "--tables",
    is_flag=True,
    help="Extract tables (requires the optional pdfplumber extractor)",
)
@click.option("--outline", is_flag=True, help="Extract and list all headings as a numbered outline")
@click.option("--section", type=int, default=None, help="Extract content under the N-th heading from outline")
@click.argument("key")
@click.pass_context
def pdf_cmd(
    ctx: click.Context,
    pages: str | None,
    extractor: str | None,
    annotations: bool,
    references: bool,
    tables: bool,
    outline: bool,
    section: int | None,
    key: str,
) -> None:
    """Extract text from the PDF attachment.

    Full text is cached locally for fast repeated access.

    \b
    Examples:
      zot pdf ABC123                Extract full text
      zot pdf ABC123 --pages 1-5    Extract pages 1-5
      zot pdf ABC123 --outline      List all headings as numbered outline
      zot pdf ABC123 --section 3    Extract content under 3rd heading
      zot pdf ABC123 --references   Parsed reference list (needs GROBID)
      zot pdf ABC123 --tables       Extract tables (needs pdfplumber)
      zot --json pdf ABC123         JSON output with metadata
    """
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
            emit_error(
                "validation_error",
                f"Invalid page range '{pages}'",
                output_json=json_out,
                hint="Use format: '1-5' or '3' for a single page",
                context="pdf",
            )
    with open_reader(ctx) as reader:
        att = reader.get_pdf_attachment(key)
        if att is None:
            emit_error(
                "not_found",
                f"No PDF attachment found for '{key}'",
                output_json=json_out,
                hint="Check item details with: zot read KEY",
                context="pdf",
            )
        pdf_path = att.path
        if not pdf_path or not pdf_path.exists():
            emit_error(
                "not_found",
                f"PDF file not found at {pdf_path or att.filename}",
                output_json=json_out,
                hint="The file may have been moved or the attachment path could not be resolved. "
                "Check Zotero storage directory",
                context="pdf",
            )
        if annotations:
            # Annotation extraction is a pymupdf-only capability.
            try:
                annots = get_extractor("pymupdf").extract_annotations(pdf_path)
            except PdfExtractionError as e:
                emit_error("runtime_error", str(e), output_json=json_out, context="pdf")
            if not annots:
                if json_out:
                    click.echo("[]")
                else:
                    click.echo("No annotations found.")
                return
            click.echo(format_pdf_annotations(annots, output_json=json_out))
            return
        if references:
            # References are a structure tier; only the grobid backend supports them.
            try:
                refs = get_extractor("grobid").extract_references(pdf_path)
            except PdfExtractionError as e:
                emit_error(
                    "runtime_error",
                    str(e),
                    output_json=json_out,
                    hint="Reference parsing needs a running GROBID service "
                    "(default http://localhost:8070; set pdf.grobid_url or ZOT_GROBID_URL)",
                    context="pdf",
                )
            if not refs:
                click.echo("[]" if json_out else "No references found.")
                return
            if json_out:
                click.echo(json.dumps({"key": key, "references": refs}, ensure_ascii=False))
            else:
                lines = []
                for i, r in enumerate(refs, 1):
                    authors = ", ".join(r["authors"][:3]) + (" et al." if len(r["authors"]) > 3 else "")
                    head = " — ".join(p for p in (authors or None, r.get("year") or None) if p)
                    doi = f"  doi:{r['doi']}" if r.get("doi") else ""
                    lines.append(f"{i}. {r.get('title') or '(no title)'}" + (f" [{head}]" if head else "") + doi)
                click.echo("\n".join(lines))
            return
        if tables:
            # Tables come from the pure-Python pdfplumber backend.
            try:
                extracted = get_extractor("pdfplumber").extract_tables(pdf_path, pages=page_range)
            except PdfExtractionError as e:
                emit_error(
                    "runtime_error",
                    str(e),
                    output_json=json_out,
                    hint="Install the pdfplumber extra: pip install 'zotero-cli-cc[pdfplumber]'",
                    context="pdf",
                )
            if not extracted:
                click.echo("[]" if json_out else "No tables found.")
                return
            if json_out:
                click.echo(json.dumps({"key": key, "tables": extracted}, ensure_ascii=False))
            else:
                blocks = []
                for t in extracted:
                    header = f"Table (page {t['page']}, #{t['index'] + 1})"
                    body = "\n".join("\t".join(row) for row in t["rows"])
                    blocks.append(f"{header}\n{body}")
                click.echo("\n\n".join(blocks))
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
                            pdf_extractor = get_extractor("pdfium")
                            text = pdf_extractor.extract_text(pdf_path)
                            cache.put(pdf_path, "pdfium", text)
                        else:
                            raise
            else:
                pdf_extractor = get_extractor(extractor)
                try:
                    text = pdf_extractor.extract_text(pdf_path, pages=page_range)
                except PdfExtractionError:
                    if extractor == "mineru":
                        pdf_extractor = get_extractor("pdfium")
                        text = pdf_extractor.extract_text(pdf_path, pages=page_range)
                    else:
                        raise
        except PdfExtractionError as e:
            cache.close()
            emit_error(
                "runtime_error",
                str(e),
                output_json=json_out,
                hint="The PDF may be corrupted or password-protected",
                context="pdf",
            )
        cache.close()
        if outline or section is not None:
            if section is not None:
                content = _extract_section(text, section)
                if not content:
                    emit_error(
                        "not_found",
                        f"Section {section} not found (document has fewer than {section} headings)",
                        output_json=json_out,
                        hint="Use --outline first to see available sections",
                        context="pdf",
                    )
                click.echo(format_pdf_text(key, pages, section=section, content=content, output_json=json_out))
            else:
                outline_data = _parse_outline(text)
                if not outline_data:
                    if json_out:
                        click.echo(json.dumps({"key": key, "pages": pages, "outline": []}, ensure_ascii=False))
                    else:
                        click.echo("No headings found in document.")
                    return
                outline_json = [{"number": n, "text": t, "level": lvl} for n, t, lvl in outline_data]
                click.echo(format_pdf_text(key, pages, outline=outline_json, output_json=json_out))
            return
        click.echo(format_pdf_text(key, pages, text=text, output_json=json_out))
