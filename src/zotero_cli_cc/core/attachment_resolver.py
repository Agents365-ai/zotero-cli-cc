from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from zotero_cli_cc.core.path_utils import is_wsl_environment, windows_to_wsl_path


class AttachmentResolver:
    """Resolves Zotero attachment paths to filesystem paths.

    Supports 4 formats:
    - 'storage:filename.pdf' — Zotero-managed storage
    - 'file:///path/to/file.pdf' — Linked file as URL
    - '/absolute/path/to/file.pdf' — Linked file as absolute path
    - 'attachments:relative/path.pdf' — Zotero linked attachment base dir
    """

    def __init__(self, db_path: Path, prefs_js_path: Path | None = None) -> None:
        self._db_path = db_path
        self._prefs_js_path = prefs_js_path
        self._base_attachment_path: Path | None | bool = (
            None  # None = not read yet, False = not found
        )

    @property
    def storage_dir(self) -> Path:
        """Return the Zotero storage directory path based on database location."""
        return self._db_path.parent / "storage"

    def _read_base_attachment_path(self) -> Path:
        if self._base_attachment_path is not None and not isinstance(self._base_attachment_path, bool):
            return self._base_attachment_path  # type: ignore[return-value]

        import glob

        prefs_locations: list[Path] = []
        if self._prefs_js_path:
            prefs_locations.append(self._prefs_js_path)
        prefs_locations.extend([
            self._db_path.parent / "prefs.js",
        ])
        zotero_profiles_dir = Path.home() / ".zotero" / "zotero"
        if zotero_profiles_dir.exists():
            prefs_locations.extend(Path(p) for p in glob.glob(str(zotero_profiles_dir / "*/prefs.js")))

        for prefs_path in prefs_locations:
            if prefs_path.exists():
                try:
                    text = prefs_path.read_text(encoding="utf-8", errors="replace")
                    m = re.search(
                        r'user_pref\("extensions\.zotero\.baseAttachmentPath",\s*"([^"]+)"\)',
                        text,
                    )
                    if m:
                        base = Path(m.group(1))
                        if is_wsl_environment():
                            self._base_attachment_path = Path(windows_to_wsl_path(str(base)))
                        else:
                            self._base_attachment_path = base
                        return self._base_attachment_path
                except Exception:
                    pass

        self._base_attachment_path = self._db_path.parent
        return self._base_attachment_path

    def resolve(self, attachment_key: str, zotero_path: str) -> Path | None:
        """Resolve a Zotero attachment path to a filesystem path.

        Args:
            attachment_key: The attachment item key from Zotero DB.
            zotero_path: The path field from itemAttachments table.

        Returns:
            Resolved filesystem Path, or None if the path cannot be resolved.
        """
        if not zotero_path:
            return None

        # Zotero-managed storage: 'storage:filename.pdf'
        if zotero_path.startswith("storage:"):
            rel = zotero_path.split(":", 1)[1]
            parts = [p for p in rel.split("/") if p]
            return self.storage_dir / attachment_key / Path(*parts)

        # Linked file as URL: 'file:///path/to/file.pdf'
        if zotero_path.startswith("file://"):
            parsed = urlparse(zotero_path)
            decoded_path = unquote(parsed.path or "")
            # file:///C:/... on Windows
            if os.name == "nt" and decoded_path.startswith("/") and len(decoded_path) > 2 and decoded_path[2] == ":":
                decoded_path = decoded_path[1:]
            if not decoded_path:
                return None
            result = Path(decoded_path)
            if is_wsl_environment():
                result = Path(windows_to_wsl_path(str(result)))
            return result

        # Linked file as absolute path: '/Users/me/papers/file.pdf'
        if os.path.isabs(zotero_path):
            result = Path(zotero_path)
            if is_wsl_environment():
                result = Path(windows_to_wsl_path(str(result)))
            return result

        # Zotero 'attachments:' relative path — resolve against the linked
        # attachment base directory configured in Zotero preferences.
        if zotero_path.startswith("attachments:"):
            rel = zotero_path.split(":", 1)[1]
            parts = [p for p in rel.split("/") if p]
            base = self._read_base_attachment_path()
            if base and base.exists():
                return base / Path(*parts)
            return None

        return None