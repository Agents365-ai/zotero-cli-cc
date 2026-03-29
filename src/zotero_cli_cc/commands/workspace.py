from __future__ import annotations

import json
from datetime import datetime, timezone

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.workspace import (
    delete_workspace,
    list_workspaces,
    load_workspace,
    save_workspace,
    validate_name,
    workspace_exists,
    Workspace,
)
from zotero_cli_cc.formatter import format_error, format_items
from zotero_cli_cc.models import ErrorInfo


@click.group("workspace")
def workspace_group() -> None:
    """Manage local workspaces for organizing papers by topic."""
    pass


@workspace_group.command("new")
@click.argument("name")
@click.option("--description", "-d", default="", help="Workspace description (topic context)")
@click.pass_context
def workspace_new(ctx: click.Context, name: str, description: str) -> None:
    """Create a new workspace."""
    json_out = ctx.obj.get("json", False)
    if not validate_name(name):
        click.echo(
            format_error(
                ErrorInfo(
                    message=f"Invalid workspace name: '{name}'",
                    context="workspace new",
                    hint="Use kebab-case (e.g., llm-safety, protein-folding)",
                ),
                output_json=json_out,
            )
        )
        return
    if workspace_exists(name):
        click.echo(
            format_error(
                ErrorInfo(
                    message=f"Workspace '{name}' already exists",
                    context="workspace new",
                    hint=f"Use 'zot workspace show {name}' to view it",
                ),
                output_json=json_out,
            )
        )
        return
    ws = Workspace(
        name=name,
        created=datetime.now(timezone.utc).isoformat(),
        description=description,
    )
    save_workspace(ws)
    click.echo(f"Workspace created: {name}")


@workspace_group.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.pass_context
def workspace_delete(ctx: click.Context, name: str, yes: bool) -> None:
    """Delete a workspace."""
    json_out = ctx.obj.get("json", False)
    if not workspace_exists(name):
        click.echo(
            format_error(
                ErrorInfo(
                    message=f"Workspace '{name}' not found",
                    context="workspace delete",
                    hint="Use 'zot workspace list' to see available workspaces",
                ),
                output_json=json_out,
            )
        )
        return
    no_interaction = ctx.obj.get("no_interaction", False)
    if not yes and not no_interaction:
        if not click.confirm(f"Delete workspace '{name}'?"):
            click.echo("Cancelled.")
            return
    delete_workspace(name)
    click.echo(f"Workspace deleted: {name}")


@workspace_group.command("add")
@click.argument("name")
@click.argument("keys", nargs=-1, required=True)
@click.pass_context
def workspace_add(ctx: click.Context, name: str, keys: tuple[str, ...]) -> None:
    """Add items to a workspace by Zotero key."""
    json_out = ctx.obj.get("json", False)
    if not workspace_exists(name):
        click.echo(
            format_error(
                ErrorInfo(
                    message=f"Workspace '{name}' not found",
                    context="workspace add",
                    hint="Use 'zot workspace new' to create it first",
                ),
                output_json=json_out,
            )
        )
        return

    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        ws = load_workspace(name)
        added = 0
        for key in keys:
            item = reader.get_item(key)
            if item is None:
                click.echo(f"Warning: item '{key}' not found in Zotero library, skipped")
                continue
            if ws.add_item(key, item.title):
                added += 1
            else:
                click.echo(f"Skipped: '{key}' already in workspace")
        save_workspace(ws)
        click.echo(f"Added {added} item(s) to workspace '{name}'")
    finally:
        reader.close()


@workspace_group.command("remove")
@click.argument("name")
@click.argument("keys", nargs=-1, required=True)
@click.pass_context
def workspace_remove(ctx: click.Context, name: str, keys: tuple[str, ...]) -> None:
    """Remove items from a workspace by key."""
    json_out = ctx.obj.get("json", False)
    if not workspace_exists(name):
        click.echo(
            format_error(
                ErrorInfo(
                    message=f"Workspace '{name}' not found",
                    context="workspace remove",
                    hint="Use 'zot workspace list' to see available workspaces",
                ),
                output_json=json_out,
            )
        )
        return
    ws = load_workspace(name)
    removed = 0
    for key in keys:
        if ws.remove_item(key):
            removed += 1
    save_workspace(ws)
    click.echo(f"Removed {removed} item(s) from workspace '{name}'")


@workspace_group.command("list")
@click.pass_context
def workspace_list(ctx: click.Context) -> None:
    """List all workspaces."""
    json_out = ctx.obj.get("json", False)
    workspaces = list_workspaces()
    if not workspaces:
        click.echo("No workspaces found. Create one with: zot workspace new <name>")
        return
    if json_out:
        data = [
            {
                "name": ws.name,
                "description": ws.description,
                "items": len(ws.items),
                "created": ws.created,
            }
            for ws in workspaces
        ]
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    from io import StringIO

    from rich.console import Console
    from rich.table import Table

    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Description", width=50)
    table.add_column("Items", justify="right", width=8)
    table.add_column("Created", width=20)
    for ws in workspaces:
        desc = ws.description[:47] + "..." if len(ws.description) > 50 else ws.description
        created = ws.created[:10] if len(ws.created) >= 10 else ws.created
        table.add_row(ws.name, desc, str(len(ws.items)), created)
    console.print(table)
    click.echo(buf.getvalue().rstrip())


@workspace_group.command("show")
@click.argument("name")
@click.pass_context
def workspace_show(ctx: click.Context, name: str) -> None:
    """Show items in a workspace."""
    json_out = ctx.obj.get("json", False)
    detail = ctx.obj.get("detail", "standard")
    limit = ctx.obj.get("limit", 50)

    if not workspace_exists(name):
        click.echo(
            format_error(
                ErrorInfo(
                    message=f"Workspace '{name}' not found",
                    context="workspace show",
                    hint="Use 'zot workspace list' to see available workspaces",
                ),
                output_json=json_out,
            )
        )
        return

    ws = load_workspace(name)
    if not ws.items:
        click.echo(f"Workspace '{name}' is empty. Use 'zot workspace add {name} KEY' to add items.")
        return

    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        items = []
        missing = []
        for ws_item in ws.items[:limit]:
            item = reader.get_item(ws_item.key)
            if item is not None:
                items.append(item)
            else:
                missing.append(ws_item.key)
        if items:
            click.echo(format_items(items, output_json=json_out, detail=detail))
        for key in missing:
            click.echo(f"Warning: item '{key}' not found in Zotero library (may have been deleted)")
    finally:
        reader.close()
