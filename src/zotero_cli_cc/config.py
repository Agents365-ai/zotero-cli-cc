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


def load_config(path: Path | None = None) -> AppConfig:
    path = path or CONFIG_FILE
    if not path.exists():
        return AppConfig()
    with open(path, "rb") as f:
        data = tomllib.load(f)
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


def save_config(config: AppConfig, path: Path | None = None) -> None:
    path = path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "[zotero]",
        f'data_dir = "{config.data_dir}"',
        f'library_id = "{config.library_id}"',
        f'api_key = "{config.api_key}"',
        "",
        "[output]",
        f'default_format = "{config.default_format}"',
        f"limit = {config.default_limit}",
        "",
        "[export]",
        f'default_style = "{config.default_export_style}"',
        "",
    ]
    path.write_text("\n".join(lines))


def detect_zotero_data_dir(config: AppConfig) -> Path:
    if config.data_dir:
        return Path(config.data_dir).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "Zotero"
    return Path.home() / "Zotero"


def get_data_dir(config: AppConfig) -> Path:
    """Get Zotero data dir: env override > config > default."""
    env_dir = os.environ.get("ZOT_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return detect_zotero_data_dir(config)
