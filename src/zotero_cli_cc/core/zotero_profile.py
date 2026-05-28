"""Locate the Zotero desktop *profile* directory (distinct from the data dir).

The data directory (auto-detected elsewhere) holds `zotero.sqlite` and
`storage/`. The *profile* directory holds `extensions/` and `prefs.js`, and is
where a plugin is sideloaded. Zotero stores it under an OS-specific app-support
path and records the active profile in `profiles.ini` (Mozilla/Firefox format).
"""

from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path


class ProfileNotFoundError(Exception):
    """Raised when the Zotero profile directory cannot be resolved."""


def profiles_base_dir() -> Path:
    """OS-specific directory that contains `profiles.ini`."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Zotero"
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Zotero" / "Zotero"
    return Path.home() / ".zotero" / "zotero"


def _resolve_path(base: Path, raw_path: str, is_relative: bool) -> Path:
    p = Path(raw_path)
    if is_relative or not p.is_absolute():
        return (base / raw_path).resolve()
    return p


def find_profile_dir(override: Path | None = None, *, base: Path | None = None) -> Path:
    """Resolve the active Zotero profile directory.

    Resolution: an explicit `override` wins; otherwise parse `profiles.ini`,
    preferring an `[Install*]` section's `Default=`, then a `[Profile*]` marked
    `Default=1`, then a lone profile. Raises ProfileNotFoundError if none of
    these resolve to an existing directory.
    """
    if override is not None:
        if not override.is_dir():
            raise ProfileNotFoundError(f"Profile directory does not exist: {override}")
        return override

    base = base or profiles_base_dir()
    ini = base / "profiles.ini"
    if not ini.exists():
        raise ProfileNotFoundError(
            f"profiles.ini not found at {ini} — is Zotero installed? Pass --profile to point at it directly."
        )

    parser = configparser.ConfigParser()
    parser.read(ini, encoding="utf-8")

    candidates: list[Path] = []

    # An [Install*] section names the profile the running app actually uses.
    for section in parser.sections():
        if section.startswith("Install") and parser.has_option(section, "Default"):
            candidates.append(_resolve_path(base, parser.get(section, "Default"), is_relative=True))

    # Fall back to [Profile*] sections (Default=1 first, then any single one).
    profile_sections = [s for s in parser.sections() if s.startswith("Profile")]
    default_profiles = []
    for section in profile_sections:
        raw = parser.get(section, "Path", fallback=None)
        if not raw:
            continue
        is_rel = parser.get(section, "IsRelative", fallback="1") == "1"
        resolved = _resolve_path(base, raw, is_relative=is_rel)
        if parser.get(section, "Default", fallback="0") == "1":
            default_profiles.append(resolved)
    candidates.extend(default_profiles)
    if not default_profiles and len(profile_sections) == 1:
        raw = parser.get(profile_sections[0], "Path", fallback=None)
        if raw:
            is_rel = parser.get(profile_sections[0], "IsRelative", fallback="1") == "1"
            candidates.append(_resolve_path(base, raw, is_relative=is_rel))

    for cand in candidates:
        if cand.is_dir():
            return cand

    raise ProfileNotFoundError(
        f"Could not resolve an existing profile directory from {ini}. Pass --profile to point at it directly."
    )
