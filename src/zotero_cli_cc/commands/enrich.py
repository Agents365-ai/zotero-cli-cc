"""`zot enrich <KEY>...` — write journal metrics (IF/quartile/partition/...) into an item's Extra field.

Source-neutral: values come from `--set` flags or a user-maintained
`--from-map` TOML table, never from a bundled dataset or third-party API.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from zotero_cli_cc.config import AppConfig, get_data_dir, get_prefs_js_path, load_config, resolve_library_id
from zotero_cli_cc.core.enrich import EnrichError, load_journal_map, merge_extra, metrics_for, parse_set_pairs
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import envelope_ok

_ABORT_CODES = {"auth_missing", "auth_invalid", "network_error"}


@click.command("enrich")
@click.argument("item_keys", nargs=-1, required=True)
@click.option("--set", "set_pairs", multiple=True, help='Metric as "Label=value" (repeatable), e.g. --set "SCI IF=5.8"')
@click.option(
    "--from-map",
    "map_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="TOML table of journal name -> {metric: value}; applied by the item's journal",
)
@click.option("--dry-run", is_flag=True, help="Preview the Extra changes without writing")
@click.pass_context
def enrich_cmd(
    ctx: click.Context,
    item_keys: tuple[str, ...],
    set_pairs: tuple[str, ...],
    map_path: Path | None,
    dry_run: bool,
) -> None:
    """Write journal metrics into an item's Extra field. MUTATES LIBRARY.

    Source-neutral — `zot` only writes the values you supply (inline `--set`
    or a `--from-map` table you maintain); it ships no journal data and calls
    no third-party API. Metrics go into a delimited `<!-- zot:metrics -->`
    block in Extra, so re-running replaces just that block. Re-running is
    idempotent.

    \b
    Examples:
      zot enrich ABCD1234 --set "SCI IF=5.8" --set "JCR=Q1" --dry-run
      zot enrich ABCD1234 --set "中科院分区=2区"
      zot enrich ABCD1234 EFGH5678 --from-map journals.toml
      zot enrich ABCD1234 --from-map journals.toml --set "JCR=Q1"   # --set overrides the map
    """
    json_out = ctx.obj.get("json", False)
    try:
        pairs = parse_set_pairs(set_pairs)
        journal_map = load_journal_map(map_path) if map_path else {}
    except EnrichError as e:
        emit_error(e.code, str(e), output_json=json_out, context="enrich")

    if not pairs and not journal_map:
        emit_error(
            "validation_error",
            "Nothing to write — provide --set key=value and/or --from-map FILE",
            output_json=json_out,
            context="enrich",
        )

    cfg = load_config(profile=ctx.obj.get("profile"))
    db_path = get_data_dir(cfg) / "zotero.sqlite"
    reader = ZoteroReader(
        db_path, library_id=resolve_library_id(db_path, ctx.obj), prefs_js_path=get_prefs_js_path(cfg)
    )

    writer: ZoteroWriter | None = None
    results: list[dict] = []
    updated = 0
    for key in item_keys:
        item = reader.get_item(key)
        if item is None:
            results.append({"key": key, "error": "item not found", "code": "not_found"})
            continue
        metrics = metrics_for(item, journal_map, pairs)
        if not metrics:
            results.append({"key": key, "warning": "no metrics (journal not in map and no --set given)"})
            continue
        if dry_run:
            preview = merge_extra(item.extra.get("extra", ""), metrics)
            results.append({"key": key, "metrics": metrics, "status": "dry-run", "extra_preview": preview})
            continue
        if writer is None:
            writer = _build_writer(ctx, cfg, json_out)
        try:
            writer.update_extra_metrics(key, metrics)
            results.append({"key": key, "metrics": metrics, "status": "updated"})
            updated += 1
        except ZoteroWriteError as e:
            if e.code in _ABORT_CODES:
                emit_error(e.code, str(e), output_json=json_out, retryable=e.retryable, context="enrich")
            results.append({"key": key, "status": "error", "error": str(e), "code": e.code})

    _emit(json_out, results, updated=updated, dry_run=dry_run)


def _build_writer(ctx: click.Context, cfg: AppConfig, json_out: bool) -> ZoteroWriter:
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        library_id = ctx.obj["group_id"]
    if not library_id or not api_key:
        emit_error(
            "auth_missing",
            "Write credentials not configured",
            output_json=json_out,
            hint="Run 'zot config init' to set up API credentials",
            context="enrich",
        )
    return ZoteroWriter(library_id=library_id, api_key=api_key, library_type=library_type)


def _emit(json_out: bool, results: list[dict], *, updated: int, dry_run: bool) -> None:
    data = {"results": results, "updated_count": updated, "sync_required": updated > 0}
    env = envelope_ok(data, extra={"dry_run": True} if dry_run else None)
    if json_out:
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
        return
    for item in results:
        click.echo(f"{item['key']}:")
        if item.get("error"):
            click.echo(f"  error: {item['error']}", err=True)
        elif item.get("warning"):
            click.echo(f"  {item['warning']}", err=True)
        else:
            for k, v in item.get("metrics", {}).items():
                click.echo(f"  {k}: {v}")
            click.echo(f"  ({item['status']})")
    if dry_run:
        click.echo("[dry-run] no items changed", err=True)
    elif updated:
        click.echo(SYNC_REMINDER, err=True)
