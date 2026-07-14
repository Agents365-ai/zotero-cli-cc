from __future__ import annotations

import click

from zotero_cli_cc.commands._helpers import open_reader
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import format_item_detail


@click.command("read")
@click.argument("key")
@click.pass_context
def read_cmd(ctx: click.Context, key: str) -> None:
    """View item details (metadata, abstract, notes).

    \b
    Examples:
      zot read ABC123
      zot --json read ABC123
      zot --detail full read ABC123
    """
    json_out = ctx.obj.get("json", False)
    with open_reader(ctx) as reader:
        item = reader.get_item(key)
        if item is None:
            emit_error(
                "not_found",
                f"Item '{key}' not found",
                output_json=json_out,
                hint="Run 'zot search' to find valid item keys",
                context="read",
            )
        notes = reader.get_notes(key)
        detail = ctx.obj.get("detail", "standard")
        click.echo(format_item_detail(item, notes, output_json=json_out, detail=detail))
