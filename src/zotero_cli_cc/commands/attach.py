from __future__ import annotations

import json
import os
from pathlib import Path

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok


@click.command("attach")
@click.argument("key")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="File to upload")
@click.option("--dry-run", is_flag=True, help="Preview the upload without calling the API")
@click.option("--idempotency-key", default=None, help="Key so retries are safe; same key returns the original result")
@click.pass_context
def attach_cmd(
    ctx: click.Context,
    key: str,
    file_path: str,
    dry_run: bool,
    idempotency_key: str | None,
) -> None:
    """Upload a file attachment to an existing Zotero item. MUTATES LIBRARY.

    \b
    Examples:
      zot attach ABC123 --file paper.pdf
      zot attach ABC123 --file ~/Downloads/supplement.pdf
      zot attach ABC123 --file paper.pdf --dry-run
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)

    fp = Path(file_path)
    size = fp.stat().st_size if fp.exists() else None

    if dry_run:
        data = {"would": {"parent": key, "file": str(fp), "size_bytes": size}}
        if json_out:
            click.echo(json.dumps(envelope_ok(data, extra={"dry_run": True}), indent=2, ensure_ascii=False))
        else:
            click.echo(f"[dry-run] Would upload {fp} ({size} bytes) as attachment to '{key}'")
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
            context="attach",
        )

    from zotero_cli_cc.core.idempotency import get_cached, store_cached

    cache_scope = f"attach:{key}:{fp.name}"
    if idempotency_key:
        cached = get_cached(cache_scope, idempotency_key)
        if cached is not None:
            if json_out:
                click.echo(json.dumps(cached, indent=2, ensure_ascii=False))
            else:
                click.echo(f"Attachment uploaded: {cached.get('data', {}).get('attachment_key', '?')} (cached).")
            return

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        att_key = writer.upload_attachment(key, fp)
    except ZoteroWriteError as e:
        emit_error(
            e.code,
            str(e),
            output_json=json_out,
            retryable=e.retryable,
            hint="Check the item key and file path",
            context="attach",
        )

    env = envelope_ok(
        {"attachment_key": att_key, "parent_key": key, "file": str(fp), "sync_required": True},
        extra={"next": [f"zot read {key}"]},
    )
    if idempotency_key:
        store_cached(cache_scope, idempotency_key, env)
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Attachment uploaded: {att_key}")
        click.echo(SYNC_REMINDER, err=True)
