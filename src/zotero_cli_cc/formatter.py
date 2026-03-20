from __future__ import annotations

import json
from dataclasses import asdict
from io import StringIO

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from zotero_cli_cc.models import Collection, Item, Note


def format_items(items: list[Item], output_json: bool = False) -> str:
    if output_json:
        return json.dumps([asdict(i) for i in items], indent=2, ensure_ascii=False)
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    table = Table(show_header=True, header_style="bold")
    table.add_column("Key", style="cyan", width=10)
    table.add_column("Title", width=50)
    table.add_column("Authors", width=25)
    table.add_column("Year", width=6)
    table.add_column("Type", width=15)
    for item in items:
        authors = ", ".join(c.full_name for c in item.creators[:3])
        if len(item.creators) > 3:
            authors += " et al."
        table.add_row(item.key, item.title, authors, item.date or "", item.item_type)
    console.print(table)
    return buf.getvalue()


def format_item_detail(
    item: Item, notes: list[Note], output_json: bool = False
) -> str:
    if output_json:
        data = asdict(item)
        data["notes"] = [asdict(n) for n in notes]
        return json.dumps(data, indent=2, ensure_ascii=False)
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    console.print(f"[bold cyan]{item.title}[/bold cyan]")
    console.print(f"Key: {item.key}  |  Type: {item.item_type}  |  Date: {item.date or 'N/A'}")
    console.print(f"Authors: {', '.join(c.full_name for c in item.creators)}")
    if item.doi:
        console.print(f"DOI: {item.doi}")
    if item.url:
        console.print(f"URL: {item.url}")
    if item.tags:
        console.print(f"Tags: {', '.join(item.tags)}")
    if item.abstract:
        console.print(f"\n[bold]Abstract:[/bold]\n{item.abstract}")
    if notes:
        console.print(f"\n[bold]Notes ({len(notes)}):[/bold]")
        for n in notes:
            console.print(f"  [{n.key}] {n.content[:200]}")
    return buf.getvalue()


def format_collections(
    collections: list[Collection], output_json: bool = False
) -> str:
    if output_json:
        return json.dumps(
            [_collection_to_dict(c) for c in collections],
            indent=2, ensure_ascii=False,
        )
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    tree = Tree("[bold]Collections[/bold]")
    for c in collections:
        _add_collection_to_tree(tree, c)
    console.print(tree)
    return buf.getvalue()


def format_notes(notes: list[Note], output_json: bool = False) -> str:
    if output_json:
        return json.dumps([asdict(n) for n in notes], indent=2, ensure_ascii=False)
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    for n in notes:
        console.print(f"[bold cyan][{n.key}][/bold cyan]")
        console.print(n.content)
        console.print()
    return buf.getvalue()


def format_error(message: str, output_json: bool = False) -> str:
    if output_json:
        return json.dumps({"error": message}, ensure_ascii=False)
    return f"Error: {message}"


def _collection_to_dict(c: Collection) -> dict:
    return {
        "key": c.key,
        "name": c.name,
        "parent_key": c.parent_key,
        "children": [_collection_to_dict(ch) for ch in c.children],
    }


def _add_collection_to_tree(parent: Tree, c: Collection) -> None:
    node = parent.add(f"[cyan]{c.name}[/cyan] ({c.key})")
    for ch in c.children:
        _add_collection_to_tree(node, ch)
