"""`zot bridge` — install / check / remove the zot-cli-bridge Zotero plugin.

Installing sideloads the plugin into the Zotero *profile* (writes a proxy file
into `extensions/` and refreshes `prefs.js`). Zotero must be restarted before
the bridge goes live, and editing the profile while Zotero runs is unsafe, so
install/uninstall refuse to run against a live Zotero unless `--force`.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from zotero_cli_cc.core.bridge_install import (
    BridgeInstallError,
    bridge_source_dir,
    install_bridge,
    is_zotero_running,
    uninstall_bridge,
)
from zotero_cli_cc.core.local_bridge import LocalBridgeError, ping
from zotero_cli_cc.core.zotero_profile import ProfileNotFoundError, find_profile_dir
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok


@click.group("bridge")
def bridge_group() -> None:
    """Manage the zot-cli-bridge Zotero plugin (enables 'zot find-pdf'). MUTATES LOCAL CONFIG."""


def _guard_running(force: bool, json_out: bool, context: str) -> None:
    if is_zotero_running() and not force:
        emit_error(
            "validation_error",
            "Zotero appears to be running. Quit it first so the profile isn't overwritten, then retry.",
            output_json=json_out,
            hint="Close Zotero and rerun, or pass --force to proceed anyway.",
            context=context,
        )


@bridge_group.command("install")
@click.option(
    "--profile", "profile", type=click.Path(), default=None, help="Zotero profile dir (auto-detected if omitted)"
)
@click.option("--force", is_flag=True, help="Install even if Zotero is currently running")
@click.pass_context
def bridge_install(ctx: click.Context, profile: str | None, force: bool) -> None:
    """Sideload the bridge plugin into the Zotero profile. MUTATES LOCAL CONFIG.

    \b
    Examples:
      zot bridge install
      zot bridge install --profile ~/Library/Application\\ Support/Zotero/Profiles/abcd.default
    """
    json_out = ctx.obj.get("json", False)
    _guard_running(force, json_out, "bridge install")

    try:
        source_dir = bridge_source_dir()
    except BridgeInstallError as e:
        emit_error(e.code, str(e), output_json=json_out, context="bridge install")

    try:
        profile_dir = find_profile_dir(Path(profile) if profile else None)
    except ProfileNotFoundError as e:
        emit_error(
            "not_found",
            str(e),
            output_json=json_out,
            hint="Pass --profile with the path to your Zotero profile directory.",
            context="bridge install",
        )

    try:
        info = install_bridge(profile_dir, source_dir)
    except BridgeInstallError as e:
        emit_error(e.code, str(e), output_json=json_out, context="bridge install")

    env = envelope_ok(info, extra={"next": ["Restart Zotero, then run: zot bridge status"]})
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        return
    click.echo(f"Installed bridge into profile: {info['profile']}")
    click.echo(f"  plugin id:  {info['plugin_id']}")
    click.echo(f"  proxy file: {info['proxy_file']}")
    click.echo(f"  points to:  {info['source']}")
    click.echo("Restart Zotero, then verify with: zot bridge status", err=True)


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
            hint="Run 'zot bridge install' (then restart Zotero) if the plugin is missing.",
            context="bridge status",
        )

    env = envelope_ok({"installed": True, "bridge": info})
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        return
    click.echo(f"Bridge OK — Zotero {info.get('zotero_version', '?')}, plugin {info.get('bridge_version', '?')}")


@bridge_group.command("uninstall")
@click.option(
    "--profile", "profile", type=click.Path(), default=None, help="Zotero profile dir (auto-detected if omitted)"
)
@click.option("--force", is_flag=True, help="Uninstall even if Zotero is currently running")
@click.pass_context
def bridge_uninstall(ctx: click.Context, profile: str | None, force: bool) -> None:
    """Remove the bridge plugin's proxy file from the Zotero profile. MUTATES LOCAL CONFIG."""
    json_out = ctx.obj.get("json", False)
    _guard_running(force, json_out, "bridge uninstall")

    try:
        profile_dir = find_profile_dir(Path(profile) if profile else None)
    except ProfileNotFoundError as e:
        emit_error(
            "not_found",
            str(e),
            output_json=json_out,
            hint="Pass --profile with the path to your Zotero profile directory.",
            context="bridge uninstall",
        )

    try:
        info = uninstall_bridge(profile_dir)
    except BridgeInstallError as e:
        emit_error(e.code, str(e), output_json=json_out, context="bridge uninstall")

    env = envelope_ok(info)
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        return
    removed = info["removed"]
    if removed:
        click.echo(f"Removed bridge from profile: {info['profile']}")
        click.echo("Restart Zotero to fully unload the plugin.", err=True)
    else:
        click.echo("Bridge was not installed in this profile (nothing to remove).")
