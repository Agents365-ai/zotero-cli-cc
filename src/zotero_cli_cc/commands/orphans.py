"""`zot orphans` — find and clean attachments whose stored file is missing locally.

A Web-API upload (``zot attach``) lands the file in zotero.org cloud storage,
so it never appears in the local ``storage/`` folder until a desktop file-sync
pulls it down. Failed retries can also leave attachment records pointing at a
file that exists nowhere. Those records make Zotero show "the attached file
could not be found". ``list`` scans for them (read-only); ``clean`` deletes the
truly dead ones via the Web API.
"""

from __future__ import annotations

import dataclasses
import json
import sys

import click

from zotero_cli_cc.commands._helpers import build_writer, open_reader
from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError
from zotero_cli_cc.exit_codes import EXIT_RUNTIME, emit_error
from zotero_cli_cc.formatter import envelope_ok, envelope_partial
from zotero_cli_cc.models import OrphanAttachment


@click.group("orphans")
def orphans_group() -> None:
    """Find / clean attachments whose stored file is missing from local storage."""


def _scan(ctx: click.Context) -> list[OrphanAttachment]:
    with open_reader(ctx) as reader:
        return reader.find_orphan_attachments()


def _counts(orphans: list[OrphanAttachment]) -> dict[str, int]:
    out = {"dead": 0, "recoverable": 0, "unknown": 0}
    for o in orphans:
        out[o.classification] = out.get(o.classification, 0) + 1
    return out


@orphans_group.command("list")
@click.option("--dead-only", is_flag=True, help="Only show 'dead' orphans (no copy anywhere); hide recoverable ones")
@click.pass_context
def orphans_list(ctx: click.Context, dead_only: bool) -> None:
    """List storage-backed attachments whose file is missing from local storage.

    Each is classified: 'dead' (no copy anywhere — safe to remove with
    `zot orphans clean`), 'recoverable' (the server still has it — run a Zotero
    file-sync or open the item to download it), or 'unknown' (sync state
    unavailable).

    \b
    Examples:
      zot orphans list
      zot orphans list --dead-only
      zot --json orphans list
    """
    json_out = ctx.obj.get("json", False)
    orphans = _scan(ctx)
    if dead_only:
        orphans = [o for o in orphans if o.classification == "dead"]

    data = {"orphans": [dataclasses.asdict(o) for o in orphans], "total": len(orphans), "counts": _counts(orphans)}
    if json_out:
        click.echo(json.dumps(envelope_ok(data), indent=2, ensure_ascii=False))
        return

    if not orphans:
        click.echo("No orphaned attachments found — every stored file is present locally.")
        return
    for o in orphans:
        parent = f" (parent {o.parent_key}: {o.parent_title})" if o.parent_key else " (top-level)"
        click.echo(f"[{o.classification}] {o.attachment_key}  {o.filename}{parent}")
    c = _counts(orphans)
    click.echo(
        f"\n{len(orphans)} orphan(s): {c['dead']} dead, {c['recoverable']} recoverable, {c['unknown']} unknown.",
        err=True,
    )
    if c["dead"]:
        click.echo("Remove the dead ones with: zot orphans clean", err=True)
    if c["recoverable"]:
        click.echo("Recoverable ones download on a Zotero file-sync (enable 'Sync attachment files').", err=True)


@orphans_group.command("clean")
@click.option(
    "--include-recoverable",
    is_flag=True,
    help="Also delete 'recoverable' orphans — DISCARDS the server copy too. Use with care.",
)
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without executing")
@click.option("--idempotency-key", default=None, help="Key so retries are safe; same key returns the original result")
@click.pass_context
def orphans_clean(
    ctx: click.Context,
    include_recoverable: bool,
    yes: bool,
    dry_run: bool,
    idempotency_key: str | None,
) -> None:
    """Delete orphaned attachment records via the Web API. MUTATES LIBRARY.

    By default only removes 'dead' orphans (no file anywhere). Pass
    --include-recoverable to also delete ones the server still holds (this
    discards the cloud copy too). Deletion goes through the Zotero Web API, so
    records that were never synced to the server return 'not_found' — remove
    those from the Zotero desktop instead.

    \b
    Examples:
      zot orphans clean --dry-run
      zot orphans clean --yes
      zot orphans clean --include-recoverable --dry-run
    """
    json_out = ctx.obj.get("json", False)
    orphans = _scan(ctx)
    targets = [o for o in orphans if o.classification == "dead" or (include_recoverable and o.classification != "dead")]
    keys = [o.attachment_key for o in targets]

    if dry_run:
        data = {"would_delete": keys, "count": len(keys), "targets": [dataclasses.asdict(o) for o in targets]}
        if json_out:
            click.echo(json.dumps(envelope_ok(data, extra={"dry_run": True}), indent=2, ensure_ascii=False))
        else:
            for o in targets:
                click.echo(f"[dry-run] Would delete [{o.classification}] {o.attachment_key} ({o.filename})")
            click.echo(f"[dry-run] {len(keys)} orphan(s) would be deleted.", err=True)
        return

    if not keys:
        msg = "No dead orphans to clean (pass --include-recoverable to target recoverable ones)."
        if json_out:
            click.echo(json.dumps(envelope_ok({"deleted": [], "count": 0}), indent=2, ensure_ascii=False))
        else:
            click.echo(msg)
        return

    cfg = load_config(profile=ctx.obj.get("profile"))
    writer = build_writer(ctx, cfg, json_out, context="orphans clean")

    no_interaction = ctx.obj.get("no_interaction", False)
    if not yes and not no_interaction:
        if not sys.stdin.isatty():
            emit_error(
                "confirmation_required",
                f"Refusing to delete {len(keys)} orphan(s) without confirmation on non-interactive stdin",
                output_json=json_out,
                hint="Pass --yes to confirm or use --dry-run to preview",
                context="orphans clean",
            )
        if not click.confirm(f"Delete {len(keys)} orphaned attachment(s)?"):
            if json_out:
                click.echo(json.dumps(envelope_ok({"cancelled": True}), indent=2, ensure_ascii=False))
            else:
                click.echo("Cancelled.", err=True)
            return

    from zotero_cli_cc.core.idempotency import get_cached, store_cached

    cache_scope = "orphans-clean:" + ",".join(sorted(keys))
    if idempotency_key:
        cached = get_cached(cache_scope, idempotency_key)
        if cached is not None:
            if json_out:
                click.echo(json.dumps(cached, indent=2, ensure_ascii=False))
            else:
                click.echo(f"Deleted {len(keys)} orphan(s) (cached).")
            return

    succeeded: list[dict] = []
    failed: list[dict] = []
    for key in keys:
        try:
            writer.delete_item(key)
            succeeded.append({"key": key})
            if not json_out:
                click.echo(f"Deleted orphan '{key}'.")
        except ZoteroWriteError as e:
            failed.append({"key": key, "error": {"code": e.code, "message": str(e), "retryable": e.retryable}})
            if not json_out:
                click.echo(f"Error: delete failed for '{key}': {e}", err=True)

    if json_out:
        if failed and succeeded:
            env = envelope_partial(succeeded, failed, meta={"sync_required": True})
        elif failed:
            click.echo(
                json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": "api_error",
                            "message": f"{len(failed)} delete(s) failed",
                            "retryable": True,
                            "failed": failed,
                        },
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            raise SystemExit(EXIT_RUNTIME)
        else:
            env = envelope_ok(
                {"deleted": [s["key"] for s in succeeded], "count": len(succeeded), "sync_required": True}
            )
        if idempotency_key and not failed:
            store_cached(cache_scope, idempotency_key, env)
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
    else:
        if not failed:
            click.echo(SYNC_REMINDER, err=True)
        if failed:
            raise SystemExit(EXIT_RUNTIME)
