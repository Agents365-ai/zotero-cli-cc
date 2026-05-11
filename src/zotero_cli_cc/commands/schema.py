"""`zot schema` — emit machine-readable schema for every command.

Derived from the Click command tree so the schema cannot drift from the actual CLI.
"""

from __future__ import annotations

import json
from typing import Any

import click

from zotero_cli_cc import __version__
from zotero_cli_cc.formatter import SCHEMA_VERSION, envelope_error, envelope_ok


def _param_type_name(param: click.Parameter) -> str:
    t = param.type
    name = getattr(t, "name", None) or type(t).__name__.lower()
    if isinstance(t, click.Choice):
        return "choice"
    if isinstance(t, click.Path):
        return "path"
    if isinstance(t, click.IntRange):
        return "integer"
    if name in ("integer", "int"):
        return "integer"
    if name in ("boolean", "bool"):
        return "boolean"
    if name == "float":
        return "number"
    return "string"


def _param_to_dict(param: click.Parameter) -> dict:
    d: dict[str, Any] = {
        "name": param.name,
        "kind": "argument" if isinstance(param, click.Argument) else "option",
        "type": _param_type_name(param),
        "required": bool(param.required),
    }
    if isinstance(param, click.Option):
        d["flags"] = list(param.opts) + list(param.secondary_opts)
        d["is_flag"] = bool(getattr(param, "is_flag", False))
        if param.help:
            d["help"] = param.help
    default = param.default
    if callable(default):
        try:
            default = default()
        except Exception:
            default = None
    if default is not None and default is not False and type(default).__name__ != "Sentinel":
        try:
            json.dumps(default)
            d["default"] = default
        except TypeError:
            d["default"] = str(default)
    if isinstance(param.type, click.Choice):
        d["choices"] = list(param.type.choices)
    if param.nargs and param.nargs != 1:
        d["nargs"] = param.nargs
    return d


_SAFETY_TIER: dict[str, str] = {
    # write
    "add": "write",
    "update": "write",
    "note": "write",
    "attach": "write",
    # destructive
    "delete": "destructive",
    "update-status": "destructive",
}


def _command_to_dict(cmd: click.Command, path: list[str]) -> dict:
    name = " ".join(path) if path else cmd.name or ""
    data: dict[str, Any] = {
        "name": name,
        "help": (cmd.help or "").strip().splitlines()[0] if cmd.help else "",
        "safety_tier": _SAFETY_TIER.get(path[0] if path else "", "read"),
        "since": "0.3.0",
        "deprecated": False,
    }
    params = [p for p in cmd.params if not (isinstance(p, click.Option) and p.name == "help")]
    data["params"] = [_param_to_dict(p) for p in params]
    if isinstance(cmd, click.Group):
        subs = {}
        for sub_name, sub_cmd in sorted(cmd.commands.items()):
            subs[sub_name] = _command_to_dict(sub_cmd, path + [sub_name])
        data["subcommands"] = subs
    return data


def _resolve_command(root: click.Command, target: str) -> click.Command | None:
    parts = target.replace(".", " ").split()
    current: click.Command = root
    for part in parts:
        if not isinstance(current, click.Group):
            return None
        nxt = current.commands.get(part)
        if nxt is None:
            return None
        current = nxt
    return current


def _flatten_commands(node: dict, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], dict]:
    out: dict[tuple[str, ...], dict] = {path: node}
    for sub_name, sub_node in node.get("subcommands", {}).items():
        out.update(_flatten_commands(sub_node, path + (sub_name,)))
    return out


def _option_flags(node: dict) -> set[str]:
    flags: set[str] = set()
    for p in node.get("params", []):
        if p.get("kind") == "option":
            flags.update(p.get("flags", []))
    return flags


def compute_schema_diff(before: dict, after: dict) -> dict[str, Any]:
    """Return a structural diff between two schema trees.

    Tracks added/removed commands (by dotted path) and added/removed option
    flags per surviving command. Type/help/default changes are intentionally
    out of scope to keep the diff useful and short.
    """
    before_cmds = _flatten_commands(before)
    after_cmds = _flatten_commands(after)
    before_paths = set(before_cmds)
    after_paths = set(after_cmds)

    def label(p: tuple[str, ...]) -> str:
        return ".".join(p) or "(root)"

    commands_added = sorted(label(p) for p in after_paths - before_paths)
    commands_removed = sorted(label(p) for p in before_paths - after_paths)

    commands_changed: dict[str, dict[str, list[str]]] = {}
    for path in sorted(before_paths & after_paths):
        added = sorted(_option_flags(after_cmds[path]) - _option_flags(before_cmds[path]))
        removed = sorted(_option_flags(before_cmds[path]) - _option_flags(after_cmds[path]))
        if added or removed:
            entry: dict[str, list[str]] = {}
            if added:
                entry["params_added"] = added
            if removed:
                entry["params_removed"] = removed
            commands_changed[label(path)] = entry

    return {
        "commands_added": commands_added,
        "commands_removed": commands_removed,
        "commands_changed": commands_changed,
    }


def _load_cached_schema(path: str) -> tuple[dict, dict[str, str]]:
    """Read a previously-emitted schema file. Accepts a full envelope or a bare data tree."""
    with open(path, encoding="utf-8") as f:
        loaded = json.load(f)
    if isinstance(loaded, dict) and "data" in loaded and isinstance(loaded["data"], dict):
        meta = loaded.get("meta") or {}
        version_info = {
            "schema_version": meta.get("schema_version", "unknown"),
            "cli_version": meta.get("cli_version", "unknown"),
        }
        return loaded["data"], version_info
    return loaded, {"schema_version": "unknown", "cli_version": "unknown"}


@click.command("schema")
@click.argument("command_path", nargs=-1)
@click.option(
    "--diff",
    "diff_path",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="Path to a previously-emitted schema. Output a structural diff against the current schema.",
)
@click.pass_context
def schema_cmd(ctx: click.Context, command_path: tuple[str, ...], diff_path: str | None) -> None:
    """Emit machine-readable schema for the CLI or one command.

    \b
    Examples:
      zot schema                       # full tree
      zot schema search                # schema for one command
      zot schema collection add        # nested subcommand
      zot schema --diff prev.json      # structural diff vs cached schema
    """
    root = ctx.find_root().command

    if command_path:
        joined = " ".join(command_path)
        target = _resolve_command(root, joined)
        if target is None:
            env = envelope_error(
                code="not_found",
                message=f"Command '{joined}' not found",
                retryable=False,
                hint="Run 'zot schema' to list all commands",
            )
            click.echo(json.dumps(env, indent=2, ensure_ascii=False))
            raise SystemExit(4)
        data = _command_to_dict(target, list(command_path))
    else:
        data = _command_to_dict(root, [])

    if diff_path is not None:
        try:
            before, before_versions = _load_cached_schema(diff_path)
        except (OSError, json.JSONDecodeError) as e:
            env = envelope_error(
                code="validation_error",
                message=f"Could not read cached schema at {diff_path!r}: {e}",
                retryable=False,
                hint="Provide a JSON file produced by `zot schema`",
            )
            click.echo(json.dumps(env, indent=2, ensure_ascii=False))
            raise SystemExit(3) from e
        data = {
            "from": before_versions,
            "to": {"schema_version": SCHEMA_VERSION, "cli_version": __version__},
            **compute_schema_diff(before, data),
        }

    env = envelope_ok(
        data,
        meta={
            "schema_version": SCHEMA_VERSION,
            "cli_version": __version__,
        },
    )
    click.echo(json.dumps(env, indent=2, ensure_ascii=False))
