from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_config_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def workspaces_dir() -> Path:
    return Path(user_config_dir("zot")) / "workspaces"


def validate_name(name: str) -> bool:
    return bool(_NAME_RE.match(name))


@dataclass
class WorkspaceItem:
    key: str
    title: str
    added: str


@dataclass
class Workspace:
    name: str
    created: str
    description: str = ""
    items: list[WorkspaceItem] = field(default_factory=list)

    def has_item(self, key: str) -> bool:
        return any(i.key == key for i in self.items)

    def add_item(self, key: str, title: str) -> bool:
        """Add item. Returns False if already present."""
        if self.has_item(key):
            return False
        self.items.append(WorkspaceItem(
            key=key,
            title=title,
            added=datetime.now(timezone.utc).isoformat(),
        ))
        return True

    def remove_item(self, key: str) -> bool:
        """Remove item. Returns False if not present."""
        before = len(self.items)
        self.items = [i for i in self.items if i.key != key]
        return len(self.items) < before


def _workspace_path(name: str) -> Path:
    return workspaces_dir() / f"{name}.toml"


def _escape_toml_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def save_workspace(ws: Workspace) -> None:
    path = _workspace_path(ws.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f'created = "{_escape_toml_string(ws.created)}"',
        f'description = "{_escape_toml_string(ws.description)}"',
        "",
    ]
    for item in ws.items:
        lines.append("[[items]]")
        lines.append(f'key = "{_escape_toml_string(item.key)}"')
        lines.append(f'title = "{_escape_toml_string(item.title)}"')
        lines.append(f'added = "{_escape_toml_string(item.added)}"')
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def load_workspace(name: str) -> Workspace:
    path = _workspace_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Workspace '{name}' not found")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    items = [
        WorkspaceItem(key=i["key"], title=i["title"], added=i["added"])
        for i in data.get("items", [])
    ]
    return Workspace(
        name=name,
        created=data.get("created", ""),
        description=data.get("description", ""),
        items=items,
    )


def list_workspaces() -> list[Workspace]:
    ws_dir = workspaces_dir()
    if not ws_dir.exists():
        return []
    result = []
    for path in sorted(ws_dir.glob("*.toml")):
        try:
            result.append(load_workspace(path.stem))
        except Exception:
            continue
    return result


def delete_workspace(name: str) -> None:
    path = _workspace_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Workspace '{name}' not found")
    path.unlink()


def workspace_exists(name: str) -> bool:
    return _workspace_path(name).exists()
