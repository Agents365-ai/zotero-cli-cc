from __future__ import annotations

import json

import click

from zotero_cli_cc.commands._helpers import build_writer, open_reader
from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok


@click.command("tag")
@click.argument("keys", nargs=-1, required=True)
@click.option("--add", "add_tag", default=None, help="Add a tag")
@click.option("--remove", "remove_tag", default=None, help="Remove a tag")
@click.option("--dry-run", is_flag=True, help="Show what would change without executing")
@click.option("--idempotency-key", default=None, help="Key so retries are safe; same key returns the original result")
@click.pass_context
def tag_cmd(
    ctx: click.Context,
    keys: tuple[str, ...],
    add_tag: str | None,
    remove_tag: str | None,
    dry_run: bool,
    idempotency_key: str | None,
) -> None:
    """View or manage tags for one or more items.

    View tags: zot tag KEY
    Batch add: zot tag KEY1 KEY2 KEY3 --add "newtag"
    Batch remove: zot tag KEY1 KEY2 --remove "oldtag"
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)

    if dry_run and (add_tag or remove_tag):
        for key in keys:
            if add_tag:
                click.echo(f"[dry-run] Would add tag '{add_tag}' to '{key}'")
            if remove_tag:
                click.echo(f"[dry-run] Would remove tag '{remove_tag}' from '{key}'")
        return

    if add_tag or remove_tag:
        from zotero_cli_cc.core.idempotency import get_cached, store_cached

        op = "add" if add_tag else "remove"
        tag_val = add_tag or remove_tag or ""
        cache_scope = f"tag_{op}:{':'.join(sorted(keys))}:{tag_val}"
        if idempotency_key:
            cached = get_cached(cache_scope, idempotency_key)
            if cached is not None:
                if json_out:
                    click.echo(json.dumps(cached, indent=2, ensure_ascii=False))
                else:
                    count = len(cached.get("data", {}).get("keys", []))
                    click.echo(f"Tag '{tag_val}' {op}ed on {count} item(s) (cached).")
                return

        writer = build_writer(ctx, cfg, json_out, context="tag")
        for key in keys:
            try:
                if add_tag:
                    writer.add_tags(key, [add_tag])
                    click.echo(f"Tag '{add_tag}' added to '{key}'.")
                if remove_tag:
                    writer.remove_tags(key, [remove_tag])
                    click.echo(f"Tag '{remove_tag}' removed from '{key}'.")
            except ZoteroWriteError as e:
                emit_error("runtime_error", str(e), output_json=json_out, context="tag")

        env = envelope_ok({"keys": list(keys), "tag": tag_val, "operation": op})
        if idempotency_key:
            store_cached(cache_scope, idempotency_key, env)
        if json_out:
            click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        click.echo(SYNC_REMINDER)
    else:
        # View mode — show tags for each key
        with open_reader(ctx, cfg) as reader:
            for key in keys:
                item = reader.get_item(key)
                if item is None:
                    click.echo(f"Warning: Item '{key}' not found, skipping.", err=True)
                    continue
                if json_out:
                    click.echo(json.dumps(envelope_ok({"key": key, "tags": item.tags}), indent=2, ensure_ascii=False))
                else:
                    click.echo(f"Tags for {key}: {', '.join(item.tags) if item.tags else '(none)'}")
