from __future__ import annotations

import json
import os

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok


@click.command("update")
@click.argument("key")
@click.option("--title", default=None, help="New title")
@click.option("--date", default=None, help="New date (e.g. 2025-01-01)")
@click.option("--field", multiple=True, help="Set field as key=value (repeatable)")
@click.option("--dry-run", is_flag=True, help="Preview the update without executing")
@click.option("--idempotency-key", default=None, help="Key so retries are safe; same key returns the original result")
@click.pass_context
def update_cmd(
    ctx: click.Context,
    key: str,
    title: str | None,
    date: str | None,
    field: tuple[str, ...],
    dry_run: bool,
    idempotency_key: str | None,
) -> None:
    """Update item metadata fields via the Zotero API. MUTATES LIBRARY.

    \b
    Examples:
      zot update ABC123 --title "New Title"
      zot update ABC123 --date "2025-01-01"
      zot update ABC123 --field volume=42 --field pages=1-10
      zot update ABC123 --title "Title" --field abstractNote="New abstract"
      zot update ABC123 --title "New" --dry-run
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)

    fields: dict[str, str] = {}
    if title:
        fields["title"] = title
    if date:
        fields["date"] = date
    for f in field:
        if "=" not in f:
            emit_error(
                "validation_error",
                f"Invalid field format: '{f}'",
                output_json=json_out,
                hint="Use key=value format",
                context="update",
            )
        k, v = f.split("=", 1)
        fields[k] = v

    if not fields:
        emit_error(
            "validation_error",
            "No fields to update",
            output_json=json_out,
            hint="Use --title, --date, or --field key=value",
            context="update",
        )

    if dry_run:
        data = {"would": {"key": key, "fields": fields, "field_count": len(fields)}}
        if json_out:
            click.echo(json.dumps(envelope_ok(data, extra={"dry_run": True}), indent=2, ensure_ascii=False))
        else:
            click.echo(f"[dry-run] Would update '{key}' with {len(fields)} field(s): {list(fields.keys())}")
        return

    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
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
            context="update",
        )

    # Idempotency cache check
    from zotero_cli_cc.core.idempotency import get_cached, store_cached

    cache_scope = f"update:{key}"
    if idempotency_key:
        cached = get_cached(cache_scope, idempotency_key)
        if cached is not None:
            click.echo(json.dumps(cached, indent=2, ensure_ascii=False) if json_out else f"Updated '{key}' (cached).")
            return

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        writer.update_item(key, fields)
    except ZoteroWriteError as e:
        emit_error(
            e.code,
            str(e),
            output_json=json_out,
            retryable=e.retryable,
            context="update",
            hint=f"Failed to update '{key}'",
        )

    env = envelope_ok(
        {"key": key, "fields": fields, "sync_required": True},
        extra={"next": [f"zot read {key}"]},
    )
    if idempotency_key:
        store_cached(cache_scope, idempotency_key, env)
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Updated {len(fields)} field(s) for '{key}'.")
        click.echo(SYNC_REMINDER, err=True)
