from __future__ import annotations

from pathlib import Path

import click

import re

from zotero_cli_cc.config import AppConfig, load_config, save_config, CONFIG_FILE, list_profiles, get_default_profile


@click.group("config")
def config_group() -> None:
    """Manage zot configuration."""
    pass


@config_group.command("init")
@click.option("--config-path", type=click.Path(), default=None, help="Config file path")
@click.option("--library-id", default=None, help="Zotero library ID")
@click.option("--api-key", default=None, help="Zotero API key")
@click.pass_context
def config_init(ctx: click.Context, config_path: str | None, library_id: str | None, api_key: str | None) -> None:
    """Initialize configuration interactively."""
    path = Path(config_path) if config_path else CONFIG_FILE
    no_interaction = ctx.obj.get("no_interaction", False) if ctx.obj else False
    json_out = ctx.obj.get("json", False) if ctx.obj else False
    if no_interaction:
        if not library_id or not api_key:
            from zotero_cli_cc.models import ErrorInfo
            from zotero_cli_cc.formatter import format_error
            click.echo(format_error(
                ErrorInfo(
                    message="--library-id and --api-key required with --no-interaction",
                    context="config init",
                    hint="Provide --library-id and --api-key, or run without --no-interaction",
                ),
                output_json=json_out,
            ))
            ctx.exit(1)
            return
    else:
        library_id = library_id or click.prompt("Zotero library ID")
        api_key = api_key or click.prompt("Zotero API key")
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


@config_group.group("profile")
def profile_group() -> None:
    """Manage configuration profiles."""
    pass


@profile_group.command("list")
@click.option("--config-path", type=click.Path(), default=None)
def profile_list(config_path: str | None) -> None:
    """List all profiles."""
    path = Path(config_path) if config_path else CONFIG_FILE
    profiles = list_profiles(path)
    default = get_default_profile(path)
    if not profiles:
        click.echo("No profiles configured.")
        return
    for p in profiles:
        marker = " (default)" if p == default else ""
        click.echo(f"  {p}{marker}")


@config_group.group("cache")
def cache_group() -> None:
    """Manage PDF text cache."""
    pass


@cache_group.command("clear")
def cache_clear() -> None:
    """Clear the PDF text cache."""
    from zotero_cli_cc.core.pdf_cache import PdfCache
    cache = PdfCache()
    stats = cache.stats()
    cache.clear()
    cache.close()
    click.echo(f"Cache cleared. Removed {stats['entries']} entries.")


@cache_group.command("stats")
def cache_stats() -> None:
    """Show PDF cache statistics."""
    from zotero_cli_cc.core.pdf_cache import PdfCache
    cache = PdfCache()
    stats = cache.stats()
    cache.close()
    click.echo(f"Cached PDFs: {stats['entries']}")
    click.echo(f"Total chars: {stats['total_chars']:,}")


@profile_group.command("set")
@click.argument("name")
@click.option("--config-path", type=click.Path(), default=None)
def profile_set(name: str, config_path: str | None) -> None:
    """Set the default profile."""
    path = Path(config_path) if config_path else CONFIG_FILE
    from zotero_cli_cc.formatter import format_error
    profiles = list_profiles(path)
    if name not in profiles:
        click.echo(format_error(f"Profile '{name}' not found. Available: {', '.join(profiles)}"))
        return
    content = path.read_text()
    if '[default]' in content:
        content = re.sub(r'(profile\s*=\s*)"[^"]*"', f'\\1"{name}"', content)
    else:
        content = f'[default]\nprofile = "{name}"\n\n' + content
    path.write_text(content)
    click.echo(f"Default profile set to '{name}'.")
