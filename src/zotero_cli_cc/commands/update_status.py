"""Check and update publication status of preprints via Semantic Scholar."""

from __future__ import annotations

import json
import os

import click

from zotero_cli_cc.config import get_data_dir, load_config, resolve_library_id
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.semantic_scholar import PreprintInfo, SemanticScholarClient, extract_preprint_info
from zotero_cli_cc.core.writer import SYNC_REMINDER, ZoteroWriteError, ZoteroWriter


@click.command("update-status")
@click.argument("key", required=False, default=None)
@click.option("--apply", is_flag=True, help="Actually update Zotero (default is dry-run)")
@click.option(
    "--api-key",
    "ss_api_key",
    default=None,
    help="Semantic Scholar API key (or set S2_API_KEY env var)",
)
@click.option("--collection", default=None, help="Only check items in this collection")
@click.option("--limit", default=None, type=int, help="Max items to check")
@click.pass_context
def update_status_cmd(
    ctx: click.Context,
    key: str | None,
    apply: bool,
    ss_api_key: str | None,
    collection: str | None,
    limit: int | None,
) -> None:
    """Check if preprints (arXiv, bioRxiv, medRxiv) have been formally published.

    Uses the Semantic Scholar API to look up publication status.
    By default runs in dry-run mode — use --apply to update Zotero.

    \b
    API key (optional, increases rate limit):
      --api-key KEY                                Pass directly
      export S2_API_KEY=KEY                        Official Semantic Scholar env var
      export SEMANTIC_SCHOLAR_API_KEY=KEY           Alternative env var
      config.toml: semantic_scholar_api_key         Set in zot config
    Apply at https://www.semanticscholar.org/product/api#api-key-form

    \b
    Examples:
      zot update-status                    # check all preprints (dry-run)
      zot update-status --apply            # update published items in Zotero
      zot update-status ABC123             # check a single item
      zot update-status --collection "NLP" # check items in a collection
      zot update-status --limit 10         # check at most 10 items
    """
    cfg = load_config(profile=ctx.obj.get("profile"))
    json_out = ctx.obj.get("json", False)
    limit = limit if limit is not None else ctx.obj.get("limit", 50)

    # Resolve Semantic Scholar API key: flag > env (S2_API_KEY or SEMANTIC_SCHOLAR_API_KEY) > config
    api_key = (
        ss_api_key
        or os.environ.get("S2_API_KEY", "")
        or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        or cfg.semantic_scholar_api_key
    )
    if not api_key:
        rate_msg = "No API key — rate limited to ~1 request/3s. Set S2_API_KEY for faster queries."
        if not json_out:
            click.echo(rate_msg, err=True)

    # Read items from local DB
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)

    try:
        if key:
            item = reader.get_item(key)
            if not item:
                click.echo(f"Error: Item '{key}' not found.", err=True)
                raise SystemExit(1)
            items = [item]
        else:
            try:
                items = reader.get_arxiv_preprints(collection=collection, limit=limit)
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)
                raise SystemExit(1)
    finally:
        reader.close()

    if not items:
        if json_out:
            click.echo("[]")
        else:
            click.echo("No preprints found.")
        return

    # Extract preprint identifiers (arXiv, bioRxiv, medRxiv)
    preprint_items: list[tuple[str, PreprintInfo, str]] = []  # (item_key, info, title)
    for item in items:
        info = extract_preprint_info(
            url=item.url,
            doi=item.doi,
            extra=item.extra.get("extra") if item.extra else None,
        )
        if info:
            preprint_items.append((item.key, info, item.title))

    if not preprint_items:
        if json_out:
            click.echo("[]")
        else:
            click.echo("No items with preprint IDs found.")
        return

    # Count by source
    arxiv_count = sum(1 for _, info, _ in preprint_items if info.source == "arxiv")
    biorxiv_count = len(preprint_items) - arxiv_count

    if not json_out:
        parts = []
        if arxiv_count:
            parts.append(f"{arxiv_count} arXiv")
        if biorxiv_count:
            parts.append(f"{biorxiv_count} bioRxiv/medRxiv")
        click.echo(f"Checking {' + '.join(parts)} preprint(s)...")
        if not api_key:
            est_time = len(preprint_items) * 3
            click.echo(f"Estimated time: ~{est_time}s (use API key to speed up)")
        click.echo()

    # Query Semantic Scholar
    client = SemanticScholarClient(api_key=api_key or None)
    results: list[dict] = []
    published_count = 0

    try:
        for i, (item_key, info, title) in enumerate(preprint_items):
            if not json_out:
                label = f"[{i + 1}/{len(preprint_items)}]"
                short_title = title[:60] + ("..." if len(title) > 60 else "")
                click.echo(f"{label} {short_title}", nl=False)

            status = client.check_publication(info)

            if status and status.is_published:
                published_count += 1
                result = {
                    "key": item_key,
                    "preprint_id": info.preprint_id,
                    "source": info.source,
                    "title": title,
                    "published": True,
                    "venue": status.venue,
                    "journal": status.journal_name,
                    "doi": status.doi,
                    "date": status.publication_date,
                }
                results.append(result)
                if not json_out:
                    venue = status.venue or status.journal_name or "Unknown venue"
                    click.echo(f" → Published in {venue}")
            else:
                result = {
                    "key": item_key,
                    "preprint_id": info.preprint_id,
                    "source": info.source,
                    "title": title,
                    "published": False,
                }
                results.append(result)
                if not json_out:
                    if status is None:
                        click.echo(" → Not found on Semantic Scholar")
                    else:
                        click.echo(" → Not yet published")
    finally:
        client.close()

    if json_out:
        click.echo(json.dumps(results, indent=2))
        return

    click.echo()
    click.echo(f"Found {published_count}/{len(preprint_items)} published paper(s).")

    if published_count == 0:
        return

    if not apply:
        click.echo("\nDry-run mode. Use --apply to update Zotero metadata.")
        return

    # Apply updates via Zotero Web API
    zot_library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    zot_api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    library_type = ctx.obj.get("library_type", "user")
    if library_type == "group" and ctx.obj.get("group_id"):
        zot_library_id = ctx.obj["group_id"]

    if not zot_library_id or not zot_api_key:
        click.echo(
            "\nError: Zotero write credentials not configured. Run 'zot config init' to set up API credentials.",
            err=True,
        )
        raise SystemExit(1)

    writer = ZoteroWriter(library_id=zot_library_id, api_key=zot_api_key, library_type=library_type)
    updated = 0
    for r in results:
        if not r["published"]:
            continue
        fields: dict[str, str] = {}
        if r.get("doi"):
            fields["DOI"] = r["doi"]
        if r.get("venue"):
            fields["publicationTitle"] = r["venue"]
        elif r.get("journal"):
            fields["publicationTitle"] = r["journal"]
        if r.get("date"):
            fields["date"] = r["date"]
        if not fields:
            continue
        try:
            writer.update_item(r["key"], fields)
            updated += 1
            click.echo(f"  Updated {r['key']}: {r['title'][:50]}...")
        except ZoteroWriteError as e:
            click.echo(f"  Failed {r['key']}: {e}", err=True)

    click.echo(f"\nUpdated {updated} item(s).")
    if updated > 0:
        click.echo(SYNC_REMINDER)
