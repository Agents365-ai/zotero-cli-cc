"""Build the `zot-cli-bridge` plugin into an installable `.xpi`.

Zotero's AddonManager owns plugin installation: it rejects pointer-file and
hand-dropped `.xpi` sideloads (it deletes them on startup), so a CLI cannot
silently install a plugin into a modern Zotero. What it *can* do is package
the bundled plugin into an `.xpi` and hand it to Zotero's own installer
(Tools -> Plugins -> Install Plugin From File), which is the reliable path.
"""

from __future__ import annotations

import json
import zipfile
from importlib import resources
from pathlib import Path

# Files that make up the plugin (relative to the source dir). The manifest's
# `icons` entry must resolve, or Zotero 8/9 reject the install as
# "incompatible", so icon.png is mandatory, not decorative.
_PLUGIN_FILES = ("manifest.json", "bootstrap.js", "icon.png")


class BridgeInstallError(Exception):
    """Raised when the bridge `.xpi` cannot be built.

    `code` maps to a CLI exit code via exit_codes.CODE_TO_EXIT.
    """

    def __init__(self, message: str, *, code: str = "bridge_error") -> None:
        super().__init__(message)
        self.code = code


def bridge_source_dir() -> Path:
    """Locate the plugin asset directory (manifest.json + bootstrap.js + icon.png).

    Works both from a source checkout (repo `extension/` dir) and when
    pip-installed (assets bundled at `zotero_cli_cc/bridge_assets/`).
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


def default_xpi_path() -> Path:
    """Default location for the built `.xpi` (user cache)."""
    return Path.home() / ".cache" / "zot" / "zot-cli-bridge.xpi"


def build_xpi(dest: Path | None = None, source_dir: Path | None = None) -> Path:
    """Package the plugin files into an `.xpi` (a zip) at `dest`. Returns the path."""
    source_dir = source_dir or bridge_source_dir()
    dest = dest or default_xpi_path()
    dest.parent.mkdir(parents=True, exist_ok=True)

    missing = [f for f in _PLUGIN_FILES if not (source_dir / f).exists()]
    if missing:
        raise BridgeInstallError(
            f"Plugin assets incomplete (missing {', '.join(missing)}). Reinstall zotero-cli-cc.",
            code="bridge_error",
        )

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for name in _PLUGIN_FILES:
            z.write(source_dir / name, name)
    return dest
