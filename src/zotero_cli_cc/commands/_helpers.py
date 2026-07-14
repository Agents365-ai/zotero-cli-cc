"""Shared plumbing helpers for command modules."""

from __future__ import annotations

import os

import click

from zotero_cli_cc.config import AppConfig, get_data_dir, get_prefs_js_path, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import ZoteroWriter
from zotero_cli_cc.exit_codes import emit_error


def open_reader(ctx: click.Context, cfg: AppConfig | None = None) -> ZoteroReader:
    """Build a ZoteroReader from the Click context (config, data dir, library).

    Pass ``cfg`` when the caller already loaded the config (avoids a second load).
    """
    if cfg is None:
        cfg = load_config(profile=ctx.obj.get("profile"))
    db_path = get_data_dir(cfg) / "zotero.sqlite"
    return ZoteroReader(
        db_path,
        library_id=resolve_library_id(db_path, ctx.obj),
        prefs_js_path=get_prefs_js_path(cfg),
    )


def build_writer(ctx: click.Context, cfg: AppConfig, json_out: bool, context: str) -> ZoteroWriter:
    """Build a ZoteroWriter from config; exits via emit_error if credentials are missing."""
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
            context=context,
        )
    return ZoteroWriter(library_id=str(library_id), api_key=api_key, library_type=library_type)
