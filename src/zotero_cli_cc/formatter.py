from __future__ import annotations

import contextvars
import json
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from io import StringIO
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from zotero_cli_cc import __version__
from zotero_cli_cc.models import Collection, DuplicateGroup, ErrorInfo, Item, Note

SCHEMA_VERSION = "1.0.0"

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("_request_id", default=None)
_request_start: contextvars.ContextVar[float | None] = contextvars.ContextVar("_request_start", default=None)


@contextmanager
def request_scope() -> Iterator[str]:
    """Bind a request_id and start time to the current context.

    Envelopes emitted inside this scope automatically carry request_id and
    latency_ms in meta, so commands don't have to pass them explicitly.
    """
    rid = uuid.uuid4().hex[:12]
    rid_tok = _request_id.set(rid)
    start_tok = _request_start.set(time.monotonic())
    try:
        yield rid
    finally:
        _request_id.reset(rid_tok)
        _request_start.reset(start_tok)


def _base_meta() -> dict[str, Any]:
    meta: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "cli_version": __version__}
    rid = _request_id.get()
    if rid:
        meta["request_id"] = rid
    start = _request_start.get()
    if start is not None:
        meta["latency_ms"] = int((time.monotonic() - start) * 1000)
    return meta


def envelope_ok(data: Any, meta: dict | None = None, extra: dict | None = None) -> dict:
    env: dict[str, Any] = {"ok": True, "data": data}
    if extra:
        env.update(extra)
    env["meta"] = {**_base_meta(), **(meta or {})}
    return env


def envelope_error(
    code: str,
    message: str,
    retryable: bool = False,
    **extra: Any,
) -> dict:
    err: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    for k, v in extra.items():
        if v is not None and v != "":
            err[k] = v
    return {
        "ok": False,
        "error": err,
        "meta": _base_meta(),
    }


def envelope_partial(succeeded: list, failed: list, meta: dict | None = None) -> dict:
    return {
        "ok": "partial",
        "data": {"succeeded": succeeded, "failed": failed},
        "meta": {**_base_meta(), **(meta or {})},
    }


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def format_items(items: list[Item], output_json: bool = False, detail: str = "standard") -> str:
    if output_json:
        if detail == "minimal":
            minimal_keys = {"key", "item_type", "title", "creators", "date"}
            data = [{k: v for k, v in asdict(i).items() if k in minimal_keys} for i in items]
        else:
            data = [asdict(i) for i in items]
        return _dump(envelope_ok(data, meta={"count": len(items)}))
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
        return _dump(envelope_ok(data))
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
        data = [_collection_to_dict(c) for c in collections]
        return _dump(envelope_ok(data, meta={"count": len(collections)}))
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    tree = Tree("[bold]Collections[/bold]")
    for c in collections:
        _add_collection_to_tree(tree, c)
    console.print(tree)
    return buf.getvalue()


def format_notes(notes: list[Note], output_json: bool = False) -> str:
    if output_json:
        data = [asdict(n) for n in notes]
        return _dump(envelope_ok(data, meta={"count": len(notes)}))
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    for n in notes:
        console.print(f"[bold cyan][{n.key}][/bold cyan]")
        console.print(n.content)
        console.print()
    return buf.getvalue()


def format_duplicates(groups: list[DuplicateGroup], output_json: bool = False) -> str:
    if output_json:
        data = []
        for i, g in enumerate(groups, 1):
            data.append(
                {
                    "group": i,
                    "match_type": g.match_type,
                    "score": g.score,
                    "items": [asdict(item) for item in g.items],
                }
            )
        return _dump(envelope_ok(data, meta={"count": len(groups)}))
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    table = Table(show_header=True, header_style="bold")
    table.add_column("Group", width=6)
    table.add_column("Keys", width=20)
    table.add_column("Title", width=50)
    table.add_column("Match", width=8)
    table.add_column("Score", width=6)
    for i, g in enumerate(groups, 1):
        keys = ", ".join(item.key for item in g.items)
        title = g.items[0].title if g.items else ""
        table.add_row(str(i), keys, title, g.match_type, f"{g.score:.2f}")
    console.print(table)
    return buf.getvalue()


def format_error(error: str | ErrorInfo, output_json: bool = False) -> str:
    if isinstance(error, str):
        error = ErrorInfo(message=error)
    if output_json:
        env = envelope_error(
            code=error.code or "runtime_error",
            message=error.message,
            retryable=error.retryable,
            hint=error.hint,
            context=error.context,
        )
        return _dump(env)
    lines = [f"Error: {error.message}"]
    if error.hint:
        lines.append(f"Hint: {error.hint}")
    return "\n".join(lines)


def emit_progress(
    event: str,
    *,
    phase: str = "",
    done: int | None = None,
    total: int | None = None,
    **extra: Any,
) -> None:
    """Emit a structured progress event on stderr, one JSON object per line.

    Agents read stderr to track liveness without blocking on the single final
    stdout envelope. Silent multi-minute waits become detectable because the
    absence of `progress` events is itself a signal.
    """
    import sys as _sys

    payload: dict[str, Any] = {"event": event}
    rid = _request_id.get()
    if rid:
        payload["request_id"] = rid
    start = _request_start.get()
    if start is not None:
        payload["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    if phase:
        payload["phase"] = phase
    if done is not None:
        payload["done"] = done
    if total is not None:
        payload["total"] = total
    for k, v in extra.items():
        if v is not None:
            payload[k] = v
    _sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _sys.stderr.flush()


def stream_items(items: list[Item], detail: str = "standard") -> str:
    """Emit items as NDJSON: one JSON envelope per line, then a summary line.

    Designed for agents processing long result sets incrementally: they can
    read one record, act on it, and keep going without loading the full
    response into memory. The final summary line carries the total count and
    has_more=False so the agent knows when streaming is complete.
    """
    lines: list[str] = []
    for item in items:
        if detail == "minimal":
            minimal_keys = {"key", "item_type", "title", "creators", "date"}
            payload = {k: v for k, v in asdict(item).items() if k in minimal_keys}
        else:
            payload = asdict(item)
        lines.append(json.dumps({"ok": True, "data": payload}, ensure_ascii=False))
    summary = {
        "ok": True,
        "summary": {"count": len(items), "has_more": False},
        "meta": _base_meta(),
    }
    lines.append(json.dumps(summary, ensure_ascii=False))
    return "\n".join(lines)


def print_error(error: str | ErrorInfo, output_json: bool = False) -> None:
    """Emit a structured error to the correct channel.

    JSON mode: envelope to stdout (parseable result for agents).
    Text mode: human line(s) to stderr (human-facing diagnostic).

    Does not exit. Use zotero_cli_cc.exit_codes.emit_error when you want to exit.
    """
    import sys as _sys

    import click

    rendered = format_error(error, output_json=output_json)
    if output_json:
        click.echo(rendered)
    else:
        click.echo(rendered, err=True)
    _sys.stdout.flush() if output_json else _sys.stderr.flush()


def format_success(data: Any, output_json: bool = False, human_text: str = "", meta: dict | None = None) -> str:
    """Format a success result. JSON mode emits envelope; text mode emits `human_text`."""
    if output_json:
        return _dump(envelope_ok(data, meta=meta))
    return human_text


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
