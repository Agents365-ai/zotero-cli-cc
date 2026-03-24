from __future__ import annotations

import os

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.formatter import format_collections, format_error, format_items
from zotero_cli_cc.models import ErrorInfo


@click.group("collection")
def collection_group() -> None:
    """Manage Zotero collections."""
    pass


@collection_group.command("list")
@click.pass_context
def collection_list(ctx: click.Context) -> None:
    """List all collections."""
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        collections = reader.get_collections()
        click.echo(format_collections(collections, output_json=ctx.obj.get("json", False)))
    finally:
        reader.close()


@collection_group.command("items")
@click.argument("key")
@click.pass_context
def collection_items(ctx: click.Context, key: str) -> None:
    """List items in a collection."""
    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        items = reader.get_collection_items(key)
        click.echo(format_items(items, output_json=ctx.obj.get("json", False)))
    finally:
        reader.close()


@collection_group.command("create")
@click.argument("name")
@click.option("--parent", default=None, help="Parent collection key")
@click.pass_context
def collection_create(ctx: click.Context, name: str, parent: str | None) -> None:
    """Create a new collection."""
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        click.echo(
            format_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="collection",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        )
        return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        key = writer.create_collection(name, parent_key=parent)
        click.echo(f"Collection created: {key}")
        click.echo(SYNC_REMINDER)
    except ZoteroWriteError as e:
        click.echo(
            format_error(
                ErrorInfo(message=str(e), context="collection create", hint="Check API credentials and network"),
                output_json=json_out,
            )
        )


@collection_group.command("move")
@click.argument("item_key")
@click.argument("collection_key")
@click.pass_context
def collection_move(ctx: click.Context, item_key: str, collection_key: str) -> None:
    """Move an item to a collection."""
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        click.echo(
            format_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="collection",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        )
        return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        writer.move_to_collection(item_key, collection_key)
        click.echo(f"Item {item_key} moved to collection {collection_key}")
        click.echo(SYNC_REMINDER)
    except ZoteroWriteError as e:
        click.echo(
            format_error(
                ErrorInfo(message=str(e), context="collection move", hint="Check item and collection keys"),
                output_json=json_out,
            )
        )


@collection_group.command("delete")
@click.argument("key")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without executing")
@click.pass_context
def collection_delete(ctx: click.Context, key: str, dry_run: bool) -> None:
    """Delete a collection."""
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    if dry_run:
        click.echo(f"[dry-run] Would delete collection '{key}'")
        return
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        click.echo(
            format_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="collection",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        )
        return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        writer.delete_collection(key)
        click.echo(f"Collection {key} deleted")
        click.echo(SYNC_REMINDER)
    except ZoteroWriteError as e:
        click.echo(
            format_error(
                ErrorInfo(message=str(e), context="collection delete", hint="Check collection key"),
                output_json=json_out,
            )
        )


@collection_group.command("reorganize")
@click.argument("plan_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview the plan without executing")
@click.pass_context
def collection_reorganize(ctx: click.Context, plan_file: str, dry_run: bool) -> None:
    """Batch create collections and move items based on a JSON plan file.

    The plan file should be a JSON file with this structure:

    {"collections": [{"name": "Topic A", "items": ["KEY1", "KEY2"]}, ...]}

    Optional "parent" field creates subcollections.
    """
    import json
    from pathlib import Path

    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)

    plan_path = Path(plan_file)
    plan = json.loads(plan_path.read_text())
    collections = plan.get("collections", [])
    if not collections:
        click.echo("No collections in plan.")
        return

    if dry_run:
        for coll in collections:
            name = coll["name"]
            parent_name = coll.get("parent")
            items = coll.get("items", [])
            parent_str = f" (under '{parent_name}')" if parent_name else ""
            click.echo(f"[dry-run] Would create collection '{name}'{parent_str}")
            for item_key in items:
                click.echo(f"[dry-run]   Would move {item_key} -> '{name}'")
        click.echo(f"\n[dry-run] Total: {len(collections)} collections to create")
        return

    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        click.echo(
            format_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="collection reorganize",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        )
        return

    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    created_collections: dict[str, str] = {}  # name -> key mapping for parent lookups

    for coll in collections:
        name = coll["name"]
        parent_name = coll.get("parent")
        parent_key = created_collections.get(parent_name) if parent_name else None
        items = coll.get("items", [])

        try:
            col_key = writer.create_collection(name, parent_key=parent_key)
            created_collections[name] = col_key
            click.echo(f"Created collection '{name}' ({col_key})")

            for item_key in items:
                try:
                    writer.move_to_collection(item_key, col_key)
                    click.echo(f"  Moved {item_key} -> '{name}'")
                except ZoteroWriteError as e:
                    click.echo(f"  Failed to move {item_key}: {e}")
        except ZoteroWriteError as e:
            click.echo(f"Failed to create collection '{name}': {e}")

    click.echo(f"\nDone. Created {len(created_collections)} collections.")
    click.echo(SYNC_REMINDER)


@collection_group.command("rename")
@click.argument("key")
@click.argument("new_name")
@click.pass_context
def collection_rename(ctx: click.Context, key: str, new_name: str) -> None:
    """Rename a collection."""
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        click.echo(
            format_error(
                ErrorInfo(
                    message="Write credentials not configured",
                    context="collection",
                    hint="Run 'zot config init' to set up API credentials",
                ),
                output_json=json_out,
            )
        )
        return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)
    try:
        writer.rename_collection(key, new_name)
        click.echo(f"Collection {key} renamed to '{new_name}'")
        click.echo(SYNC_REMINDER)
    except ZoteroWriteError as e:
        click.echo(
            format_error(
                ErrorInfo(message=str(e), context="collection rename", hint="Check collection key"),
                output_json=json_out,
            )
        )
