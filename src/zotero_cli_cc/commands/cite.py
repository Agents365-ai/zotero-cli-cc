from __future__ import annotations

import subprocess
import sys

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_error
from zotero_cli_cc.models import ErrorInfo, Item


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        elif sys.platform == "win32":
            subprocess.run(["clip"], input=text.encode(), check=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _get_year(item: Item) -> str:
    """Extract 4-digit year from date string."""
    if not item.date:
        return "n.d."
    for part in item.date.replace("/", "-").split("-"):
        if len(part) == 4 and part.isdigit():
            return part
    return item.date


def _get_authors_apa(item: Item) -> str:
    """Format authors in APA style."""
    authors = [c for c in item.creators if c.creator_type == "author"]
    if not authors:
        return ""
    if len(authors) == 1:
        a = authors[0]
        first_initials = ". ".join(n[0] for n in a.first_name.split() if n) + "." if a.first_name else ""
        return f"{a.last_name}, {first_initials}" if first_initials else a.last_name
    if len(authors) == 2:
        parts = []
        for a in authors:
            first_initials = ". ".join(n[0] for n in a.first_name.split() if n) + "." if a.first_name else ""
            parts.append(f"{a.last_name}, {first_initials}" if first_initials else a.last_name)
        return f"{parts[0]} & {parts[1]}"
    # 3+ authors: first 19, then ... last (APA 7th)
    parts = []
    display = authors[:19] if len(authors) <= 20 else authors[:19]
    for a in display:
        first_initials = ". ".join(n[0] for n in a.first_name.split() if n) + "." if a.first_name else ""
        parts.append(f"{a.last_name}, {first_initials}" if first_initials else a.last_name)
    if len(authors) > 20:
        last = authors[-1]
        first_initials = ". ".join(n[0] for n in last.first_name.split() if n) + "." if last.first_name else ""
        last_str = f"{last.last_name}, {first_initials}" if first_initials else last.last_name
        return ", ".join(parts) + ", ... " + last_str
    return ", ".join(parts[:-1]) + ", & " + parts[-1]


def _get_authors_vancouver(item: Item) -> str:
    """Format authors in Vancouver style."""
    authors = [c for c in item.creators if c.creator_type == "author"]
    if not authors:
        return ""
    parts = []
    display = authors[:6]
    for a in display:
        initials = "".join(n[0].upper() for n in a.first_name.split() if n) if a.first_name else ""
        parts.append(f"{a.last_name} {initials}" if initials else a.last_name)
    result = ", ".join(parts)
    if len(authors) > 6:
        result += ", et al"
    return result


def _format_apa(item: Item) -> str:
    """Format citation in APA 7th edition style."""
    authors = _get_authors_apa(item)
    year = _get_year(item)
    title = item.title or ""
    journal = item.extra.get("publicationTitle", "")
    volume = item.extra.get("volume", "")
    issue = item.extra.get("issue", "")
    pages = item.extra.get("pages", "")
    doi = item.doi

    parts = []
    if authors:
        parts.append(f"{authors} ({year}).")
    else:
        parts.append(f"({year}).")
    parts.append(f"{title}.")
    if journal:
        vol_str = f", {volume}" if volume else ""
        issue_str = f"({issue})" if issue else ""
        pages_str = f", {pages}" if pages else ""
        parts.append(f"{journal}{vol_str}{issue_str}{pages_str}.")
    if doi:
        parts.append(f"https://doi.org/{doi}")

    return " ".join(parts)


def _format_nature(item: Item) -> str:
    """Format citation in Nature style."""
    authors = [c for c in item.creators if c.creator_type == "author"]
    if not authors:
        author_str = ""
    else:
        parts = []
        for a in authors:
            initials = " ".join(f"{n[0]}." for n in a.first_name.split() if n) if a.first_name else ""
            parts.append(f"{a.last_name}, {initials}".strip(", ") if initials else a.last_name)
        if len(parts) > 5:
            author_str = ", ".join(parts[:5]) + " et al."
        else:
            author_str = " & ".join([", ".join(parts[:-1]), parts[-1]]) if len(parts) > 1 else parts[0]

    title = item.title or ""
    journal = item.extra.get("publicationTitle", item.extra.get("journalAbbreviation", ""))
    volume = item.extra.get("volume", "")
    pages = item.extra.get("pages", "")
    year = _get_year(item)
    doi = item.doi

    result = f"{author_str} {title}." if author_str else f"{title}."
    if journal:
        result += f" {journal}"
        if volume:
            result += f" **{volume}**"
        if pages:
            result += f", {pages}"
        result += f" ({year})."
    else:
        result += f" ({year})."
    if doi:
        result += f" https://doi.org/{doi}"

    return result


def _format_vancouver(item: Item) -> str:
    """Format citation in Vancouver style."""
    authors = _get_authors_vancouver(item)
    title = item.title or ""
    journal = item.extra.get("journalAbbreviation", item.extra.get("publicationTitle", ""))
    year = _get_year(item)
    volume = item.extra.get("volume", "")
    issue = item.extra.get("issue", "")
    pages = item.extra.get("pages", "")
    doi = item.doi

    result = f"{authors}. {title}." if authors else f"{title}."
    if journal:
        result += f" {journal}. {year}"
        if volume:
            result += f";{volume}"
        if issue:
            result += f"({issue})"
        if pages:
            result += f":{pages}"
        result += "."
    else:
        result += f" {year}."
    if doi:
        result += f" doi:{doi}"

    return result


STYLES = {
    "apa": _format_apa,
    "nature": _format_nature,
    "vancouver": _format_vancouver,
}


@click.command("cite")
@click.argument("key")
@click.option(
    "--style",
    default="apa",
    type=click.Choice(["apa", "nature", "vancouver"]),
    help="Citation style (default: apa)",
)
@click.option("--no-copy", is_flag=True, help="Print only, do not copy to clipboard")
@click.pass_context
def cite_cmd(ctx: click.Context, key: str, style: str, no_copy: bool) -> None:
    """Format a citation and copy to clipboard.

    \b
    Examples:
      zot cite ABC123                    APA style (default)
      zot cite ABC123 --style nature     Nature style
      zot cite ABC123 --style vancouver  Vancouver style
      zot cite ABC123 --no-copy          Print without copying
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    json_out = ctx.obj.get("json", False)
    try:
        item = reader.get_item(key)
        if item is None:
            click.echo(
                format_error(
                    ErrorInfo(
                        message=f"Item '{key}' not found",
                        context="cite",
                        hint="Run 'zot search' to find valid item keys",
                    ),
                    output_json=json_out,
                )
            )
            return
        formatter = STYLES[style]
        citation = formatter(item)
        click.echo(citation)
        if not no_copy:
            if _copy_to_clipboard(citation):
                click.echo("(copied to clipboard)")
            else:
                click.echo("(clipboard not available)")
    finally:
        reader.close()
