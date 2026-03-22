from __future__ import annotations

import json

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_error
from zotero_cli_cc.models import ErrorInfo


@click.command("export")
@click.argument("key")
@click.option("--format", "fmt", default="bibtex", type=click.Choice(["bibtex", "csl-json", "json"]), help="Export format")
@click.pass_context
def export_cmd(ctx: click.Context, key: str, fmt: str) -> None:
    """Export citation."""
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    json_out = ctx.obj.get("json", False)
    try:
        if fmt == "json":
            item = reader.get_item(key)
            if item is None:
                click.echo(format_error(ErrorInfo(message=f"Item '{key}' not found", context="export", hint="Run 'zot search' to find valid item keys"), output_json=json_out))
                return
            from dataclasses import asdict
            click.echo(json.dumps(asdict(item), indent=2, ensure_ascii=False))
        else:
            result = reader.export_citation(key, fmt=fmt)
            if result is None:
                click.echo(format_error(ErrorInfo(message=f"Item '{key}' not found", context="export", hint="Run 'zot search' to find valid item keys"), output_json=json_out))
                return
            click.echo(result)
    finally:
        reader.close()
