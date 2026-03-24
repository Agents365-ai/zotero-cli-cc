from __future__ import annotations

import json
from dataclasses import asdict
from io import StringIO

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from zotero_cli_cc.models import Collection, ErrorInfo, Item, Note


def format_items(items: list[Item], output_json: bool = False, detail: str = "standard") -> str:
    if output_json:
        if detail == "minimal":
            minimal_keys = {"key", "item_type", "title", "creators", "date"}
            data = [{k: v for k, v in asdict(i).items() if k in minimal_keys} for i in items]
        else:
            data = [asdict(i) for i in items]
        return json.dumps(data, indent=2, ensure_ascii=False)
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


def format_item_detail(item: Item, notes: list[Note], output_json: bool = False, detail: str = "standard") -> str:
    if output_json:
        if detail == "minimal":
            minimal_keys = {"key", "item_type", "title", "creators", "date", "doi", "url"}
            data = {k: v for k, v in asdict(item).items() if k in minimal_keys}
        else:
            data = asdict(item)
            data["notes"] = [asdict(n) for n in notes]
            if detail == "full":
                # extra is already included via asdict; ensure it's present explicitly
                pass
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
    if detail != "minimal":
        if item.tags:
            console.print(f"Tags: {', '.join(item.tags)}")
        if detail == "full" and item.extra:
            display_keys = [
                ("publicationTitle", "Journal"),
                ("journalAbbreviation", "Journal Abbr"),
                ("volume", "Volume"),
                ("issue", "Issue"),
                ("pages", "Pages"),
                ("ISSN", "ISSN"),
                ("publisher", "Publisher"),
                ("language", "Language"),
                ("citationKey", "Citation Key"),
            ]
            shown = []
            for ekey, label in display_keys:
                val = item.extra.get(ekey)
                if val:
                    shown.append(f"  {label}: {val}")
            if shown:
                console.print("\n[bold]Metadata:[/bold]")
                for line in shown:
                    console.print(line)
            # Show remaining extra fields not in display_keys
            skip = {k for k, _ in display_keys} | {
                "libraryCatalog",
                "accessDate",
                "rights",
            }
            remaining = {k: v for k, v in item.extra.items() if k not in skip and v}
            if remaining:
                for rk, rv in remaining.items():
                    console.print(f"  {rk}: {rv}")
        if item.abstract:
            console.print(f"\n[bold]Abstract:[/bold]\n{item.abstract}")
        if notes:
            console.print(f"\n[bold]Notes ({len(notes)}):[/bold]")
            for n in notes:
                console.print(f"  [{n.key}] {n.content[:200]}")
    return buf.getvalue()


def format_collections(collections: list[Collection], output_json: bool = False) -> str:
    if output_json:
        return json.dumps(
            [_collection_to_dict(c) for c in collections],
            indent=2,
            ensure_ascii=False,
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


def format_error(error: str | ErrorInfo, output_json: bool = False) -> str:
    if isinstance(error, str):
        error = ErrorInfo(message=error)
    if output_json:
        data: dict[str, str] = {"error": error.message}
        if error.context:
            data["context"] = error.context
        if error.hint:
            data["hint"] = error.hint
        return json.dumps(data, ensure_ascii=False)
    lines = [f"Error: {error.message}"]
    if error.hint:
        lines.append(f"Hint: {error.hint}")
    return "\n".join(lines)


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
