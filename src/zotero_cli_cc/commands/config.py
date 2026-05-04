from __future__ import annotations

import json
import re
from pathlib import Path

import click

from zotero_cli_cc.config import (
    CONFIG_FILE,
    AppConfig,
    detect_zotero_data_dir,
    get_default_profile,
    list_profiles,
    load_config,
    save_config,
)


@click.group("config")
def config_group() -> None:
    """Manage zot configuration."""
    pass


@config_group.command("init")
@click.option("--config-path", type=click.Path(), default=None, help="Config file path")
@click.option("--data-dir", "data_dir", default=None, help="Zotero data directory (auto-detected if not set)")
@click.option("--library-id", default=None, help="Zotero library ID")
@click.option("--api-key", default=None, help="Zotero API key")
@click.pass_context
def config_init(
    ctx: click.Context,
    config_path: str | None,
    data_dir: str | None,
    library_id: str | None,
    api_key: str | None,
) -> None:
    """Initialize configuration interactively."""
    path = Path(config_path) if config_path else CONFIG_FILE
    no_interaction = ctx.obj.get("no_interaction", False) if ctx.obj else False

    detected_dir = detect_zotero_data_dir(AppConfig())

    if no_interaction:
        library_id = library_id or ""
        api_key = api_key or ""
        data_dir = data_dir or str(detected_dir)
    else:
        library_id = library_id or click.prompt("Zotero library ID", default="")
        api_key = api_key or click.prompt("Zotero API key", default="")
        if data_dir is None:
            data_dir = click.prompt(
                "Zotero data directory",
                default=str(detected_dir),
            )

    # Normalize path (resolve ~, convert to absolute) to avoid Windows backslash issues
    if data_dir:
        data_dir = str(Path(data_dir).expanduser().resolve())

    cfg = AppConfig(
        data_dir=data_dir or "",
        library_id=library_id or "",
        api_key=api_key or "",
    )
    save_config(cfg, path)
    click.echo(f"Configuration saved to {path}")
    click.echo(f"  Data directory: {cfg.data_dir or '(auto-detect)'}")

    # Validate the data directory
    if cfg.data_dir:
        dd = Path(cfg.data_dir)
        if not dd.exists():
            click.echo(click.style(f"  WARNING: Directory does not exist: {dd}", fg="yellow"))
        elif not (dd / "zotero.sqlite").exists():
            click.echo(click.style(f"  WARNING: zotero.sqlite not found in {dd}", fg="yellow"))


@config_group.command("show")
@click.option("--config-path", type=click.Path(), default=None, help="Config file path")
def config_show(config_path: str | None) -> None:
    """Show current configuration."""
    from zotero_cli_cc.config import get_data_dir

    path = Path(config_path) if config_path else CONFIG_FILE
    cfg = load_config(path)
    click.echo(f"Library ID: {cfg.library_id}")
    click.echo(f"API Key:    {'***' + cfg.api_key[-4:] if len(cfg.api_key) > 4 else '(not set)'}")
    click.echo(f"Data Dir:   {cfg.data_dir or '(auto-detect)'}")
    click.echo(f"Format:     {cfg.default_format}")
    click.echo(f"Limit:      {cfg.default_limit}")
    click.echo(f"Export:     {cfg.default_export_style}")

    # Path validation
    data_dir = get_data_dir(cfg)
    db_file = data_dir / "zotero.sqlite"
    if not data_dir.exists():
        click.echo(click.style(f"\nWARNING: Data directory not found: {data_dir}", fg="yellow"))
    elif not db_file.exists():
        click.echo(click.style(f"\nWARNING: zotero.sqlite not found in {data_dir}", fg="yellow"))
    else:
        click.echo(click.style(f"\nDatabase:   {db_file} (OK)", fg="green"))


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
    import sqlite3

    from zotero_cli_cc.core.pdf_cache import PdfCache

    try:
        cache = PdfCache()
    except (sqlite3.OperationalError, OSError) as e:
        click.echo(f"Error: Could not open cache database: {e}", err=True)
        raise SystemExit(1)
    try:
        stats = cache.stats()
        cache.clear()
        click.echo(f"Cache cleared. Removed {stats['entries']} entries.")
    except sqlite3.OperationalError as e:
        click.echo(f"Error: Could not modify cache database: {e}", err=True)
        raise SystemExit(1)
    finally:
        cache.close()


@cache_group.command("stats")
def cache_stats() -> None:
    """Show PDF cache statistics."""
    import sqlite3

    from zotero_cli_cc.core.pdf_cache import PdfCache

    try:
        cache = PdfCache()
    except (sqlite3.OperationalError, OSError) as e:
        click.echo(f"Error: Could not open cache database: {e}", err=True)
        raise SystemExit(1)
    try:
        stats = cache.stats()
        click.echo(f"Cached PDFs: {stats['entries']}")
        click.echo(f"Total chars: {stats['total_chars']:,}")
    finally:
        cache.close()


@cache_group.command("list")
@click.pass_context
def cache_list(ctx: click.Context) -> None:
    """List all cached PDF entries."""
    import sqlite3

    from zotero_cli_cc.core.pdf_cache import PdfCache

    json_out = ctx.obj.get("json", False) if ctx.obj else False

    try:
        cache = PdfCache()
    except (sqlite3.OperationalError, OSError) as e:
        click.echo(f"Error: Could not open cache database: {e}", err=True)
        raise SystemExit(1)
    try:
        rows = cache._conn.execute(
            "SELECT pdf_path, extractor, LENGTH(content), content, extracted_at FROM pdf_cache ORDER BY pdf_path"
        ).fetchall()

        if not rows:
            click.echo("Cache is empty.")
            return

        if json_out:
            data = [
                {
                    "pdf_basename": row[0],
                    "extractor": row[1],
                    "text_length": row[2],
                    "preview": row[3][:100],
                    "extracted_at": row[4],
                }
                for row in rows
            ]
            click.echo(json.dumps(data, ensure_ascii=False))
            return

        from io import StringIO

        from rich.console import Console
        from rich.table import Table

        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        table = Table(show_header=True, header_style="bold")
        table.add_column("PDF Path", style="cyan", width=30)
        table.add_column("Extractor", width=10)
        table.add_column("Length", justify="right", width=10)
        table.add_column("Preview", width=50)
        table.add_column("Time", width=20)

        for row in rows:
            pdf_path, extractor, length, content, extracted_at = row
            preview = content[:100] + "..." if len(content) > 100 else content
            preview = preview.replace("\n", " ").replace("\r", " ")
            table.add_row(Path(pdf_path).name, extractor, f"{length:,}", preview, extracted_at[:19])
        console.print(table)
        click.echo(buf.getvalue().rstrip())

    except sqlite3.OperationalError as e:
        click.echo(f"Error: Could not query cache database: {e}", err=True)
        raise SystemExit(1)
    finally:
        cache.close()


@profile_group.command("set")
@click.argument("name")
@click.option("--config-path", type=click.Path(), default=None)
def profile_set(name: str, config_path: str | None) -> None:
    """Set the default profile."""
    path = Path(config_path) if config_path else CONFIG_FILE
    from zotero_cli_cc.formatter import print_error
    from zotero_cli_cc.models import ErrorInfo

    profiles = list_profiles(path)
    if name not in profiles:
        print_error(
            ErrorInfo(
                message=f"Profile '{name}' not found",
                context="config",
                hint=f"Available profiles: {', '.join(profiles)}",
            )
        )
        return
    content = path.read_text()
    if "[default]" in content:
        content = re.sub(r'(profile\s*=\s*)"[^"]*"', f'\\1"{name}"', content)
    else:
        content = f'[default]\nprofile = "{name}"\n\n' + content
    path.write_text(content)
    click.echo(f"Default profile set to '{name}'.")
