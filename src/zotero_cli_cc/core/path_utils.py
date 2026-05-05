from __future__ import annotations

import re


def is_wsl_environment() -> bool:
    """Return True if running inside WSL2."""
    try:
        with open("/proc/version") as f:
            content = f.read().lower()
            return "microsoft" in content or "wsl" in content
    except OSError:
        return False


def windows_to_wsl_path(windows_path: str) -> str:
    """Convert Windows path to WSL path.

    Examples:
        C:\\Users\\name\\file.pdf -> /mnt/c/Users/name/file.pdf
        \\\\server\\share\\file.pdf -> /mnt/server/share/file.pdf
        /mnt/c/already/wsl.pdf -> /mnt/c/already/wsl.pdf (pass-through)
    """
    if not windows_path:
        return ""

    # Already a WSL path
    if windows_path.startswith("/mnt/"):
        return windows_path

    # UNC path: \\server\share\...
    if windows_path.startswith("\\\\"):
        path = windows_path[2:]
        parts = path.split("\\")
        if len(parts) >= 2:
            return "/mnt/" + "/".join(parts)
        return windows_path

    # Drive letter path: C:\Users\...
    match = re.match(r"^([A-Za-z]):\\(.+)$", windows_path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2)
        parts = rest.replace("\\", "/").split("/")
        return "/mnt/" + drive + "/" + "/".join(parts)

    return windows_path
