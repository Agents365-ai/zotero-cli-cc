from __future__ import annotations

import json
import os
from pathlib import Path

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.local_bridge import LocalBridgeError, import_file
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok

_BRIDGE_HINT = "Start Zotero desktop; run 'zot bridge install' to (re)install the bridge plugin (import needs v0.3.0+)"


@click.command("attach")
@click.argument("key")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="File to upload")
@click.option(
    "--via-bridge",
    is_flag=True,
    help="Import through the running Zotero desktop (zot-cli-bridge plugin) so the "
    "file lands in local storage instead of cloud-only. Plays nice with zotero-attanger.",
)
@click.option("--dry-run", is_flag=True, help="Preview the upload without calling the API")
@click.option("--idempotency-key", default=None, help="Key so retries are safe; same key returns the original result")
@click.pass_context
def attach_cmd(
    ctx: click.Context,
    key: str,
    file_path: str,
    via_bridge: bool,
    dry_run: bool,
    idempotency_key: str | None,
) -> None:
    """Upload a file attachment to an existing Zotero item. MUTATES LIBRARY.

    The default path uploads via the Zotero Web API, which stores the file in
    zotero.org cloud storage — it only appears in your local `storage/` after
    the desktop syncs the file down (requires "Sync attachment files" enabled).
    Use `--via-bridge` to import through the running desktop instead, so the
    file is written to local storage immediately and cooperates with plugins
    that relocate attachments (e.g. zotero-attanger).

    \b
    Examples:
      zot attach ABC123 --file paper.pdf
      zot attach ABC123 --file paper.pdf --via-bridge   # store locally via desktop
      zot attach ABC123 --file ~/Downloads/supplement.pdf
      zot attach ABC123 --file paper.pdf --dry-run
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)

    fp = Path(file_path)
    size = fp.stat().st_size if fp.exists() else None

    if dry_run:
        sink = "Zotero desktop (local storage)" if via_bridge else "the Web API (cloud storage)"
        data = {"would": {"parent": key, "file": str(fp), "size_bytes": size, "via_bridge": via_bridge}}
        if json_out:
            click.echo(json.dumps(envelope_ok(data, extra={"dry_run": True}), indent=2, ensure_ascii=False))
        else:
            click.echo(f"[dry-run] Would attach {fp} ({size} bytes) to '{key}' via {sink}")
        return

    if via_bridge:
        try:
            result = import_file(key, str(fp.resolve()), title=fp.name)
        except LocalBridgeError as e:
            emit_error(e.code, str(e), output_json=json_out, retryable=e.retryable, hint=_BRIDGE_HINT, context="attach")
        att_key = result.get("attachment_key")
        env = envelope_ok(
            {"attachment_key": att_key, "parent_key": key, "file": str(fp), "stored": "local", "sync_required": True},
            extra={"next": [f"zot read {key}"]},
        )
        if json_out:
            click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        else:
            click.echo(f"Attachment imported to local storage: {att_key}")
            click.echo(SYNC_REMINDER, err=True)
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
        {"attachment_key": att_key, "parent_key": key, "file": str(fp), "stored": "cloud", "sync_required": True},
        extra={"next": [f"zot read {key}"]},
    )
    if idempotency_key:
        store_cached(cache_scope, idempotency_key, env)
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Attachment uploaded: {att_key}")
        click.echo(
            "Stored in zotero.org cloud; it reaches local storage/ only after a desktop file-sync. "
            "Use --via-bridge to import into local storage directly.",
            err=True,
        )
        click.echo(SYNC_REMINDER, err=True)
