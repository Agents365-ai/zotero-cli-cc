from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

CONFIG_DIR = Path(user_config_dir("zot"))
CONFIG_FILE = CONFIG_DIR / "config.toml"


def _detect_zotero_data_dir_from_registry() -> Path | None:
    """Detect Zotero data directory from Windows Registry.

    Zotero stores custom data directory in:
    HKEY_CURRENT_USER\\Software\\Zotero\\Zotero\\dataDir

    Returns None if not found or not on Windows.
    """
    if sys.platform != "win32":
        return None

    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Zotero\Zotero") as key:
            data_dir, _ = winreg.QueryValueEx(key, "dataDir")
            if data_dir and Path(data_dir).exists():
                return Path(data_dir)
    except (OSError, FileNotFoundError, ImportError):
        pass

    return None


@dataclass
class AppConfig:
    data_dir: str = ""
    library_id: str = ""
    api_key: str = ""
    default_format: str = "table"
    default_limit: int = 50
    default_export_style: str = "bibtex"

    @property
    def has_write_credentials(self) -> bool:
        return bool(self.library_id and self.api_key)


def load_config(path: Path | None = None, profile: str | None = None) -> AppConfig:
    path = path or CONFIG_FILE
    if not path.exists():
        return AppConfig()
    with open(path, "rb") as f:
        data = tomllib.load(f)

    # New profile-based config
    if "profile" in data:
        profile_name = profile or data.get("default", {}).get("profile", "")
        if profile_name and profile_name in data["profile"]:
            p = data["profile"][profile_name]
            output = p.get("output", data.get("output", {}))
            export = p.get("export", data.get("export", {}))
            return AppConfig(
                data_dir=p.get("data_dir", ""),
                library_id=p.get("library_id", ""),
                api_key=p.get("api_key", ""),
                default_format=output.get("default_format", "table"),
                default_limit=output.get("limit", 50),
                default_export_style=export.get("default_style", "bibtex"),
            )

    # Backward-compatible flat config
    zotero = data.get("zotero", {})
    output = data.get("output", {})
    export = data.get("export", {})
    return AppConfig(
        data_dir=zotero.get("data_dir", ""),
        library_id=zotero.get("library_id", ""),
        api_key=zotero.get("api_key", ""),
        default_format=output.get("default_format", "table"),
        default_limit=output.get("limit", 50),
        default_export_style=export.get("default_style", "bibtex"),
    )


def list_profiles(path: Path | None = None) -> list[str]:
    """List all profile names from config."""
    path = path or CONFIG_FILE
    if not path.exists():
        return []
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return list(data.get("profile", {}).keys())


def get_default_profile(path: Path | None = None) -> str:
    """Get the default profile name from config."""
    path = path or CONFIG_FILE
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return str(data.get("default", {}).get("profile", ""))


def save_config(config: AppConfig, path: Path | None = None) -> None:
    path = path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "[zotero]",
        f"data_dir = '{config.data_dir}'",
        f"library_id = '{config.library_id}'",
        f"api_key = '{config.api_key}'",
        "",
        "[output]",
        f"default_format = '{config.default_format}'",
        f"limit = {config.default_limit}",
        "",
        "[export]",
        f"default_style = '{config.default_export_style}'",
        "",
    ]
    path.write_text("\n".join(lines))


def detect_zotero_data_dir(config: AppConfig) -> Path:
    if config.data_dir:
        return Path(config.data_dir).expanduser()

    if sys.platform == "win32":
        registry_dir = _detect_zotero_data_dir_from_registry()
        if registry_dir:
            return registry_dir

        appdata = Path(os.environ.get("APPDATA", ""))
        if appdata and (appdata / "Zotero").exists():
            return appdata / "Zotero"

        local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
        if local_appdata and (local_appdata / "Zotero").exists():
            return local_appdata / "Zotero"

        return appdata / "Zotero"

    return Path.home() / "Zotero"


def get_data_dir(config: AppConfig) -> Path:
    """Get Zotero data dir: env override > config > default."""
    env_dir = os.environ.get("ZOT_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return detect_zotero_data_dir(config)


def resolve_library_id(db_path: Path, ctx_obj: dict) -> int:
    """Resolve the library_id from ctx.obj, defaulting to 1 (user library)."""
    if ctx_obj.get("library_type") != "group" or not ctx_obj.get("group_id"):
        return 1
    from zotero_cli_cc.core.reader import ZoteroReader

    reader = ZoteroReader(db_path)
    try:
        resolved = reader.resolve_group_library_id(int(ctx_obj["group_id"]))
    finally:
        reader.close()
    if resolved is None:
        import click

        raise click.ClickException(f"Group '{ctx_obj['group_id']}' not found in local database")
    return resolved
