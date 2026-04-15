"""Check PyPI for newer versions of zotero-cli-cc."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.request import urlopen

_CACHE_DIR = Path.home() / ".config" / "zot"
_CACHE_FILE = _CACHE_DIR / ".version_check"
_CHECK_INTERVAL = 86400  # 24 hours
_PYPI_URL = "https://pypi.org/pypi/zotero-cli-cc/json"
_TIMEOUT = 3  # seconds


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse version string into tuple for comparison."""
    return tuple(int(x) for x in v.strip().split(".") if x.isdigit())


def check_for_update(current_version: str) -> str | None:
    """Check if a newer version is available on PyPI.

    Returns the latest version string if newer, or None.
    Uses a file-based cache to avoid hitting PyPI on every invocation.
    """
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Check cache first
        if _CACHE_FILE.exists():
            cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            if time.time() - cache.get("checked_at", 0) < _CHECK_INTERVAL:
                latest = cache.get("latest_version", "")
                if latest and _parse_version(latest) > _parse_version(current_version):
                    return str(latest)
                return None

        # Fetch from PyPI
        with urlopen(_PYPI_URL, timeout=_TIMEOUT) as resp:  # noqa: S310
            data = json.loads(resp.read())
        latest = data["info"]["version"]

        # Update cache
        _CACHE_FILE.write_text(
            json.dumps({"latest_version": latest, "checked_at": time.time()}),
            encoding="utf-8",
        )

        if _parse_version(latest) > _parse_version(current_version):
            return str(latest)
        return None
    except Exception:
        return None
