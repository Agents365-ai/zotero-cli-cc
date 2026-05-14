"""`zot find-pdf <KEY>` — trigger Zotero's Find Full Text via the local bridge plugin."""

from __future__ import annotations

import json

import click

from zotero_cli_cc.core.local_bridge import DEFAULT_TIMEOUT, LocalBridgeError, find_pdf, ping
from zotero_cli_cc.core.writer import SYNC_REMINDER
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok


@click.command("find-pdf")
@click.argument("item_key")
@click.option(
    "--library-id",
    type=int,
    default=None,
    help="Override the Zotero library ID (default: user library on the desktop)",
)
@click.option(
    "--timeout",
    type=float,
    default=DEFAULT_TIMEOUT,
    help=f"Seconds to wait for resolvers to finish (default {DEFAULT_TIMEOUT:.0f}s)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Only verify the bridge is reachable; do not trigger Find Full Text",
)
@click.pass_context
def find_pdf_cmd(ctx: click.Context, item_key: str, library_id: int | None, timeout: float, dry_run: bool) -> None:
    """Find and attach the full-text PDF for an item via Zotero desktop. MUTATES LIBRARY.

    Requires Zotero desktop to be running with the `zot-cli-bridge` plugin
    installed (see `extension/zot-cli-bridge/README.md`). The plugin lets
    `zot` reuse the desktop's configured PDF resolvers AND the authenticated
    sessions / institutional proxies set up there — that's the part that the
    Zotero Web API alone cannot do, so this command is the only way to reach
    paywalled content from the CLI.

    \b
    Examples:
      zot find-pdf ABCD1234
      zot find-pdf ABCD1234 --dry-run             # check bridge reachability
      zot find-pdf ABCD1234 --timeout 180         # give slow resolvers more time
    """
    json_out = ctx.obj.get("json", False)

    if dry_run:
        try:
            info = ping()
        except LocalBridgeError as e:
            emit_error(
                e.code,
                str(e),
                output_json=json_out,
                retryable=e.retryable,
                hint="Start Zotero desktop and install the zot-cli-bridge plugin",
                context="find-pdf",
            )
        env = envelope_ok({"key": item_key, "bridge": info}, extra={"dry_run": True})
        if json_out:
            click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        else:
            click.echo(
                f"[dry-run] Bridge reachable: Zotero {info.get('zotero_version', '?')}, plugin {info.get('bridge_version', '?')}"
            )
        return

    try:
        result = find_pdf(item_key, library_id=library_id, timeout=timeout)
    except LocalBridgeError as e:
        emit_error(
            e.code,
            str(e),
            output_json=json_out,
            retryable=e.retryable,
            hint="Start Zotero desktop; install the zot-cli-bridge plugin if 'bridge_missing'",
            context="find-pdf",
        )

    found = bool(result.get("found"))
    data: dict = {
        "key": item_key,
        "found": found,
        "sync_required": found,
    }
    if found:
        data["attachment_key"] = result.get("attachment_key")
        data["filename"] = result.get("filename")
        data["content_type"] = result.get("content_type")
    else:
        data["message"] = result.get("message", "No PDF found via configured resolvers")

    env = envelope_ok(
        data,
        extra={"next": [f"zot read {item_key}", f"zot pdf {item_key}"]} if found else None,
    )

    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        return

    if found:
        click.echo(f"PDF attached: {data['attachment_key']} ({data.get('content_type') or '?'})")
        click.echo(SYNC_REMINDER, err=True)
    else:
        click.echo(data["message"], err=True)
