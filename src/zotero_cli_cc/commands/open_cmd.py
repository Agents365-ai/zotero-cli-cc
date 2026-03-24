from __future__ import annotations

import subprocess
import sys

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_error
from zotero_cli_cc.models import ErrorInfo


def _open_path(path: str) -> None:
    """Open a file or URL with the system default handler."""
    if sys.platform == "darwin":
        subprocess.run(["open", path], check=True)
    elif sys.platform == "win32":
        subprocess.run(["start", path], shell=True, check=True)
    else:
        subprocess.run(["xdg-open", path], check=True)


@click.command("open")
@click.argument("key")
@click.option("--url", "open_url", is_flag=True, help="Open the item URL in browser instead of PDF")
@click.pass_context
def open_cmd(ctx: click.Context, key: str, open_url: bool) -> None:
    """Open the PDF or URL of a Zotero item in the default app.

    \b
    Examples:
      zot open ABC123          Open PDF in default viewer
      zot open ABC123 --url    Open DOI/URL in browser
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
                        context="open",
                        hint="Run 'zot search' to find valid item keys",
                    ),
                    output_json=json_out,
                )
            )
            return

        if open_url:
            target = item.url or item.doi
            if item.doi and not item.url:
                target = f"https://doi.org/{item.doi}"
            if not target:
                click.echo(
                    format_error(
                        ErrorInfo(
                            message=f"No URL or DOI for item '{key}'",
                            context="open",
                        ),
                        output_json=json_out,
                    )
                )
                return
            click.echo(f"Opening {target}")
            _open_path(target)
            return

        # Default: open PDF
        att = reader.get_pdf_attachment(key)
        if att is None:
            click.echo(
                format_error(
                    ErrorInfo(
                        message=f"No PDF attachment for '{key}'",
                        context="open",
                        hint="Use --url to open the item URL instead",
                    ),
                    output_json=json_out,
                )
            )
            return
        pdf_path = data_dir / "storage" / att.key / att.filename
        if not pdf_path.exists():
            click.echo(
                format_error(
                    ErrorInfo(
                        message=f"PDF file not found at {pdf_path}",
                        context="open",
                    ),
                    output_json=json_out,
                )
            )
            return
        click.echo(f"Opening {pdf_path}")
        _open_path(str(pdf_path))
    finally:
        reader.close()
