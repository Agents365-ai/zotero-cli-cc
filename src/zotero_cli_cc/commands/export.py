from __future__ import annotations

import json

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.exit_codes import emit_error


@click.command("export")
@click.argument("key")
@click.option(
    "--format", "fmt", default="bibtex", type=click.Choice(["bibtex", "csl-json", "ris", "json"]), help="Export format"
)
@click.pass_context
def export_cmd(ctx: click.Context, key: str, fmt: str) -> None:
    """Export citation in BibTeX, CSL-JSON, RIS, or raw JSON format.

    \b
    Examples:
      zot export ABC123                    BibTeX (default)
      zot export ABC123 --format csl-json  CSL-JSON
      zot export ABC123 --format ris       RIS
      zot export ABC123 --format json      Raw JSON metadata
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    json_out = ctx.obj.get("json", False)
    try:
        if fmt == "json":
            item = reader.get_item(key)
            if item is None:
                emit_error(
                    "not_found",
                    f"Item '{key}' not found",
                    output_json=json_out,
                    hint="Run 'zot search' to find valid item keys",
                    context="export",
                )
            from dataclasses import asdict

            click.echo(json.dumps(asdict(item), indent=2, ensure_ascii=False))
        else:
            result = reader.export_citation(key, fmt=fmt)
            if result is None:
                emit_error(
                    "not_found",
                    f"Item '{key}' not found",
                    output_json=json_out,
                    hint="Run 'zot search' to find valid item keys",
                    context="export",
                )
            click.echo(result)
    finally:
        reader.close()
