"""`zot schema` — emit machine-readable schema for every command.

Derived from the Click command tree so the schema cannot drift from the actual CLI.
"""
from __future__ import annotations

import json
import sys
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


def _command_to_dict(cmd: click.Command, path: list[str]) -> dict:
    data: dict[str, Any] = {
        "name": " ".join(path) if path else cmd.name or "",
        "help": (cmd.help or "").strip().splitlines()[0] if cmd.help else "",
    }
    params = [p for p in cmd.params if not (isinstance(p, click.Option) and p.name == "help")]
    data["params"] = [_param_to_dict(p) for p in params]
    if isinstance(cmd, click.Group):
        subs = {}
        for sub_name, sub_cmd in sorted(cmd.commands.items()):
            subs[sub_name] = _command_to_dict(sub_cmd, path + [sub_name])
        data["subcommands"] = subs
    return data


def _resolve_command(root: click.Group, target: str) -> click.Command | None:
    parts = target.replace(".", " ").split()
    current: click.Command = root
    for part in parts:
        if not isinstance(current, click.Group):
            return None
        current = current.commands.get(part)
        if current is None:
            return None
    return current


@click.command("schema")
@click.argument("command_path", nargs=-1)
@click.pass_context
def schema_cmd(ctx: click.Context, command_path: tuple[str, ...]) -> None:
    """Emit machine-readable schema for the CLI or one command.

    \b
    Examples:
      zot schema                    # full tree
      zot schema search             # schema for one command
      zot schema collection add     # nested subcommand
    """
    root = ctx.find_root().command
    json_out = True  # schema is always JSON

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

    env = envelope_ok(
        data,
        meta={
            "schema_version": SCHEMA_VERSION,
            "cli_version": __version__,
        },
    )
    click.echo(json.dumps(env, indent=2, ensure_ascii=False))
