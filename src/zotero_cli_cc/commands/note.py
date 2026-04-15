from __future__ import annotations

import json
import os

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok, format_notes


@click.command("note")
@click.argument("key")
@click.option("--add", "content", default=None, help="Add a new note")
@click.option("--dry-run", is_flag=True, help="Preview the note addition without executing (only with --add)")
@click.option("--idempotency-key", default=None, help="Key so retries are safe; same key returns the original result")
@click.pass_context
def note_cmd(
    ctx: click.Context,
    key: str,
    content: str | None,
    dry_run: bool,
    idempotency_key: str | None,
) -> None:
    """View or add notes for an item. `--add` MUTATES LIBRARY.

    \b
    Examples:
      zot note ABC123                            View notes
      zot note ABC123 --add "Key finding: ..."   Add a note
      zot note ABC123 --add "..." --dry-run      Preview addition
      zot --json note ABC123                     JSON output
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)

    if content:
        if dry_run:
            data = {"would": {"parent": key, "content_preview": content[:200]}}
            if json_out:
                click.echo(json.dumps(envelope_ok(data, extra={"dry_run": True}), indent=2, ensure_ascii=False))
            else:
                click.echo(f"[dry-run] Would add note to '{key}': {content[:80]}...")
            return

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
                context="note",
            )

        from zotero_cli_cc.core.idempotency import get_cached, store_cached

        cache_scope = f"note:{key}"
        if idempotency_key:
            cached = get_cached(cache_scope, idempotency_key)
            if cached is not None:
                if json_out:
                    click.echo(json.dumps(cached, indent=2, ensure_ascii=False))
                else:
                    click.echo(f"Note added: {cached.get('data', {}).get('note_key', '?')} (cached).")
                return

        writer = ZoteroWriter(library_id=str(library_id), api_key=api_key, library_type=library_type)
        try:
            note_key = writer.add_note(key, content)
        except ZoteroWriteError as e:
            emit_error(
                e.code,
                str(e),
                output_json=json_out,
                retryable=e.retryable,
                hint="Check item key and API credentials",
                context="note",
            )

        env = envelope_ok(
            {"note_key": note_key, "parent_key": key, "sync_required": True},
            extra={"next": [f"zot note {key}"]},
        )
        if idempotency_key:
            store_cached(cache_scope, idempotency_key, env)
        if json_out:
            click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        else:
            click.echo(f"Note added: {note_key}")
            click.echo(SYNC_REMINDER, err=True)
    else:
        data_dir = get_data_dir(cfg)
        db_path = data_dir / "zotero.sqlite"
        library_id = resolve_library_id(db_path, ctx.obj)
        reader = ZoteroReader(db_path, library_id=library_id)
        try:
            notes = reader.get_notes(key)
            if not notes:
                emit_error(
                    "not_found",
                    f"No notes found for '{key}'",
                    output_json=json_out,
                    hint="Add one with: zot note KEY --add 'content'",
                    context="note",
                )
            click.echo(format_notes(notes, output_json=json_out))
        finally:
            reader.close()
