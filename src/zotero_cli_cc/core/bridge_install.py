"""Sideload the `zot-cli-bridge` Zotero plugin into a profile.

Zotero scans `<profile>/extensions/` at launch. The supported developer
sideload is a "proxy file" named exactly the plugin id whose contents are the
absolute path to the plugin source root. Zotero does not require plugins to be
signed, so this is sufficient — but the app must be (re)started to pick it up,
and editing the profile while Zotero is running is unsafe (Zotero rewrites
`prefs.js` on shutdown).
"""

from __future__ import annotations

import json
import socket
from importlib import resources
from pathlib import Path

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 23119


class BridgeInstallError(Exception):
    """Raised when the bridge cannot be installed/uninstalled.

    `code` maps to a CLI exit code via exit_codes.CODE_TO_EXIT.
    """

    def __init__(self, message: str, *, code: str = "bridge_error") -> None:
        super().__init__(message)
        self.code = code


def bridge_source_dir() -> Path:
    """Locate the plugin asset directory (manifest.json + bootstrap.js).

    Works both when running from a source checkout (repo `extension/` dir) and
    when pip-installed (assets bundled at `zotero_cli_cc/bridge_assets/`).
    """
    try:
        packaged = resources.files("zotero_cli_cc") / "bridge_assets"
        p = Path(str(packaged))
        if (p / "manifest.json").exists():
            return p
    except (ModuleNotFoundError, AttributeError, TypeError):
        pass

    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root / "extension" / "zot-cli-bridge"
    if (candidate / "manifest.json").exists():
        return candidate

    raise BridgeInstallError(
        "Cannot locate the bundled zot-cli-bridge plugin files. Reinstall zotero-cli-cc.",
        code="bridge_error",
    )


def plugin_id(source_dir: Path | None = None) -> str:
    """Read the plugin id from the bundled manifest (`applications.zotero.id`)."""
    source_dir = source_dir or bridge_source_dir()
    try:
        manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
        pid = manifest["applications"]["zotero"]["id"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise BridgeInstallError(f"Malformed plugin manifest: {e}", code="bridge_error") from e
    if not isinstance(pid, str) or not pid:
        raise BridgeInstallError("Plugin manifest is missing applications.zotero.id", code="bridge_error")
    return pid


def is_zotero_running() -> bool:
    """True if something is listening on Zotero's local server port."""
    try:
        with socket.create_connection((LOCAL_HOST, LOCAL_PORT), timeout=1.0):
            return True
    except OSError:
        return False


def _refresh_prefs(profile_dir: Path) -> bool:
    """Drop `extensions.lastAppBuildId`/`lastAppVersion` so Zotero rescans extensions/.

    Returns True if prefs.js was modified.
    """
    prefs = profile_dir / "prefs.js"
    if not prefs.exists():
        return False
    text = prefs.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    kept = [ln for ln in lines if "extensions.lastAppBuildId" not in ln and "extensions.lastAppVersion" not in ln]
    if len(kept) == len(lines):
        return False
    prefs.write_text("".join(kept), encoding="utf-8")
    return True


def install_bridge(profile_dir: Path, source_dir: Path | None = None) -> dict[str, object]:
    """Write the proxy file and refresh prefs so Zotero loads the bridge on next launch."""
    source_dir = source_dir or bridge_source_dir()
    pid = plugin_id(source_dir)

    ext_dir = profile_dir / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    proxy = ext_dir / pid
    proxy.write_text(str(source_dir.resolve()), encoding="utf-8")

    prefs_refreshed = _refresh_prefs(profile_dir)
    return {
        "plugin_id": pid,
        "profile": str(profile_dir),
        "proxy_file": str(proxy),
        "source": str(source_dir.resolve()),
        "prefs_refreshed": prefs_refreshed,
    }


def uninstall_bridge(profile_dir: Path, source_dir: Path | None = None) -> dict[str, object]:
    """Remove the proxy file (and any copied .xpi) for the bridge plugin."""
    pid = plugin_id(source_dir)
    ext_dir = profile_dir / "extensions"
    removed: list[str] = []
    for target in (ext_dir / pid, ext_dir / f"{pid}.xpi"):
        if target.exists():
            target.unlink()
            removed.append(str(target))
    return {"plugin_id": pid, "profile": str(profile_dir), "removed": removed}
