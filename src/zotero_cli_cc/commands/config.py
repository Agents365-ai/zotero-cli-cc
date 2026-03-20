from __future__ import annotations

from pathlib import Path

import click

from zotero_cli_cc.config import AppConfig, load_config, save_config, CONFIG_FILE


@click.group("config")
def config_group() -> None:
    """Manage zot configuration."""
    pass


@config_group.command("init")
@click.option("--config-path", type=click.Path(), default=None, help="Config file path")
def config_init(config_path: str | None) -> None:
    """Initialize configuration interactively."""
    path = Path(config_path) if config_path else CONFIG_FILE
    library_id = click.prompt("Zotero library ID")
    api_key = click.prompt("Zotero API key")
    cfg = AppConfig(library_id=library_id, api_key=api_key)
    save_config(cfg, path)
    click.echo(f"Configuration saved to {path}")


@config_group.command("show")
@click.option("--config-path", type=click.Path(), default=None, help="Config file path")
def config_show(config_path: str | None) -> None:
    """Show current configuration."""
    path = Path(config_path) if config_path else CONFIG_FILE
    cfg = load_config(path)
    click.echo(f"Library ID: {cfg.library_id}")
    click.echo(f"API Key:    {'***' + cfg.api_key[-4:] if len(cfg.api_key) > 4 else '(not set)'}")
    click.echo(f"Data Dir:   {cfg.data_dir or '(auto-detect)'}")
    click.echo(f"Format:     {cfg.default_format}")
    click.echo(f"Limit:      {cfg.default_limit}")
    click.echo(f"Export:     {cfg.default_export_style}")
