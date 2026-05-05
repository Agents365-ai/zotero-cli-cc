from __future__ import annotations

import json
import os

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.exit_codes import EXIT_RUNTIME, emit_error
from zotero_cli_cc.formatter import print_error
from zotero_cli_cc.models import ErrorInfo


@click.command("tag")
@click.argument("keys", nargs=-1, required=True)
@click.option("--add", "add_tag", default=None, help="Add a tag")
@click.option("--remove", "remove_tag", default=None, help="Remove a tag")
@click.option("--dry-run", is_flag=True, help="Show what would change without executing")
@click.pass_context
def tag_cmd(
    ctx: click.Context, keys: tuple[str, ...], add_tag: str | None, remove_tag: str | None, dry_run: bool
) -> None:
    """View or manage tags for one or more items.

    View tags: zot tag KEY
    Batch add: zot tag KEY1 KEY2 KEY3 --add "newtag"
    Batch remove: zot tag KEY1 KEY2 --remove "oldtag"
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)

    if dry_run and (add_tag or remove_tag):
        for key in keys:
            if add_tag:
                click.echo(f"[dry-run] Would add tag '{add_tag}' to '{key}'")
            if remove_tag:
                click.echo(f"[dry-run] Would remove tag '{remove_tag}' from '{key}'")
        return

    if add_tag or remove_tag:
        library_id: str | int | None = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
        api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
        library_type = ctx.obj.get("library_type", "user")
        if library_type == "group" and ctx.obj.get("group_id"):
            library_id = ctx.obj["group_id"]
        if not library_id or not api_key:
            emit_error(
                "auth_missing",
                "Write credentials not configured",
                output_json=json_out,
                hint="Run 'zot config init' to set up API credentials",
                context="tag",
            )
        writer = ZoteroWriter(library_id=str(library_id), api_key=api_key, library_type=library_type)
        failed = []
        for key in keys:
            try:
                if add_tag:
                    writer.add_tags(key, [add_tag])
                    click.echo(f"Tag '{add_tag}' added to '{key}'.")
                if remove_tag:
                    writer.remove_tags(key, [remove_tag])
                    click.echo(f"Tag '{remove_tag}' removed from '{key}'.")
            except ZoteroWriteError as e:
                failed.append(key)
                print_error(
                    ErrorInfo(message=str(e), context="tag", hint=f"Failed for key '{key}'"), output_json=json_out
                )
        if not failed:
            click.echo(SYNC_REMINDER)
        else:
            # Surface failures via typed exit so agents/scripts detect them.
            ctx.exit(EXIT_RUNTIME)
    else:
        # View mode — show tags for each key
        data_dir = get_data_dir(cfg)
        db_path = data_dir / "zotero.sqlite"
        library_id = resolve_library_id(db_path, ctx.obj)
        reader = ZoteroReader(db_path, library_id=library_id)
        try:
            for key in keys:
                item = reader.get_item(key)
                if item is None:
                    print_error(
                        ErrorInfo(
                            message=f"Item '{key}' not found",
                            context="tag",
                            hint="Run 'zot search' to find valid item keys",
                        ),
                        output_json=json_out,
                    )
                    continue
                if json_out:
                    click.echo(json.dumps({"key": key, "tags": item.tags}))
                else:
                    click.echo(f"Tags for {key}: {', '.join(item.tags) if item.tags else '(none)'}")
        finally:
            reader.close()
