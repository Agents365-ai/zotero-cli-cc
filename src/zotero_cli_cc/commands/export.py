from __future__ import annotations

import json

import click

from zotero_cli_cc.commands._helpers import open_reader
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok


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
    json_out = ctx.obj.get("json", False)
    with open_reader(ctx) as reader:
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

            data = asdict(item)
            if json_out:
                click.echo(json.dumps(envelope_ok({"format": "json", "data": data}), indent=2, ensure_ascii=False))
            else:
                click.echo(json.dumps(data, indent=2, ensure_ascii=False))
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
            if json_out:
                click.echo(json.dumps(envelope_ok({"format": fmt, "data": result}), indent=2, ensure_ascii=False))
            else:
                click.echo(result)
