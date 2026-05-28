"""`zot bridge` — package and check the zot-cli-bridge Zotero plugin.

Zotero's AddonManager won't accept a silently sideloaded plugin on modern
builds, so `install` *builds* the `.xpi` and hands it to Zotero's own
installer (Tools -> Plugins -> Install Plugin From File). `status` pings the
running bridge; `uninstall` points at Zotero's plugin manager.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from zotero_cli_cc.core.bridge_install import (
    BridgeInstallError,
    build_xpi,
    plugin_id,
)
from zotero_cli_cc.core.local_bridge import LocalBridgeError, ping
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok

_INSTALL_STEPS = [
    "In Zotero: Tools -> Plugins",
    "Click the gear (top-right) -> Install Plugin From File...",
    "Select the .xpi above, then restart Zotero if prompted",
    "Verify with: zot bridge status",
]


@click.group("bridge")
def bridge_group() -> None:
    """Package / check the zot-cli-bridge Zotero plugin (enables 'zot find-pdf')."""


@bridge_group.command("install")
@click.option(
    "--output",
    "output",
    type=click.Path(),
    default=None,
    help="Where to write the .xpi (default: ~/.cache/zot/zot-cli-bridge.xpi)",
)
@click.pass_context
def bridge_install(ctx: click.Context, output: str | None) -> None:
    """Build the bridge plugin .xpi to install via Zotero's plugin manager.

    Zotero won't accept a CLI-sideloaded plugin, so this packages the `.xpi`
    and prints the two-click install steps.

    \b
    Examples:
      zot bridge install
      zot bridge install --output ~/Desktop/zot-cli-bridge.xpi
    """
    json_out = ctx.obj.get("json", False)
    try:
        xpi = build_xpi(Path(output) if output else None)
        pid = plugin_id()
    except BridgeInstallError as e:
        emit_error(e.code, str(e), output_json=json_out, context="bridge install")

    data = {"xpi": str(xpi), "plugin_id": pid, "install_steps": _INSTALL_STEPS}
    env = envelope_ok(data, extra={"next": ["zot bridge status"]})
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        return
    click.echo(f"Built bridge plugin: {xpi}")
    click.echo("\nInstall it in Zotero:", err=True)
    for i, step in enumerate(_INSTALL_STEPS, 1):
        click.echo(f"  {i}. {step}", err=True)


@bridge_group.command("status")
@click.pass_context
def bridge_status(ctx: click.Context) -> None:
    """Check whether Zotero + the bridge plugin are reachable.

    \b
    Examples:
      zot bridge status
      zot --json bridge status
    """
    json_out = ctx.obj.get("json", False)
    try:
        info = ping()
    except LocalBridgeError as e:
        emit_error(
            e.code,
            str(e),
            output_json=json_out,
            retryable=e.retryable,
            hint="Run 'zot bridge install' and install the .xpi via Tools -> Plugins if it's missing.",
            context="bridge status",
        )

    env = envelope_ok({"installed": True, "bridge": info})
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        return
    click.echo(f"Bridge OK — Zotero {info.get('zotero_version', '?')}, plugin {info.get('bridge_version', '?')}")


@bridge_group.command("uninstall")
@click.pass_context
def bridge_uninstall(ctx: click.Context) -> None:
    """Show how to remove the bridge plugin via Zotero's plugin manager."""
    json_out = ctx.obj.get("json", False)
    try:
        pid = plugin_id()
    except BridgeInstallError as e:
        emit_error(e.code, str(e), output_json=json_out, context="bridge uninstall")

    steps = [
        "In Zotero: Tools -> Plugins",
        f"Find '{pid}' (Zot CLI Bridge) and click Remove",
        "Restart Zotero",
    ]
    env = envelope_ok({"plugin_id": pid, "uninstall_steps": steps})
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        return
    click.echo("Zotero manages plugin removal — do it from the plugin manager:")
    for i, step in enumerate(steps, 1):
        click.echo(f"  {i}. {step}", err=True)
