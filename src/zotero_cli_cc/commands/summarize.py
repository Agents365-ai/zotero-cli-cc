from __future__ import annotations

import json

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.exit_codes import emit_error


@click.command("summarize")
@click.argument("key")
@click.pass_context
def summarize_cmd(ctx: click.Context, key: str) -> None:
    """Output a structured summary for Claude Code consumption.

    \b
    Examples:
      zot summarize ABC123
      zot --json summarize ABC123
      zot --detail minimal summarize ABC123
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        item = reader.get_item(key)
        if item is None:
            emit_error(
                "not_found",
                f"Item '{key}' not found",
                output_json=json_out,
                hint="Run 'zot search' to find valid item keys",
                context="summarize",
            )
        notes = reader.get_notes(key)
        detail = ctx.obj.get("detail", "standard")
        if json_out:
            data: dict = {
                "title": item.title,
                "authors": [c.full_name for c in item.creators],
                "year": item.date,
                "doi": item.doi,
            }
            if detail != "minimal":
                data["abstract"] = item.abstract
                data["tags"] = item.tags
                data["notes"] = [n.content[:500] for n in notes]
            click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            click.echo(f"Title: {item.title}")
            click.echo(f"Authors: {', '.join(c.full_name for c in item.creators)}")
            click.echo(f"Year: {item.date or 'N/A'}")
            if item.doi:
                click.echo(f"DOI: {item.doi}")
            if item.url:
                click.echo(f"URL: {item.url}")
            if detail != "minimal":
                if item.tags:
                    click.echo(f"Tags: {', '.join(item.tags)}")
                if item.extra:
                    journal = item.extra.get("publicationTitle")
                    volume = item.extra.get("volume", "")
                    issue = item.extra.get("issue", "")
                    pages = item.extra.get("pages", "")
                    parts = [
                        p
                        for p in [
                            journal,
                            f"vol.{volume}" if volume else "",
                            f"({issue})" if issue else "",
                            f"pp.{pages}" if pages else "",
                        ]
                        if p
                    ]
                    if parts:
                        click.echo(f"Source: {' '.join(parts)}")
                if item.abstract:
                    click.echo(f"\nAbstract:\n{item.abstract}")
                if notes:
                    click.echo(f"\nNotes ({len(notes)}):")
                    for n in notes:
                        click.echo(f"  {n.content[:500]}")
    finally:
        reader.close()
