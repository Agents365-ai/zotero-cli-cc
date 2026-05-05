from __future__ import annotations

import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import click

from zotero_cli_cc.config import get_data_dir, get_prefs_js_path, load_config, load_embedding_config, resolve_library_id
from zotero_cli_cc.core.rag import (
    bm25_score_chunks,
    build_metadata_chunk,
    chunk_text,
    compute_term_frequencies,
    convert_pdf_to_text,
    convert_pdfs_to_text,
    embed_texts,
    reciprocal_rank_fusion,
    semantic_score_chunks,
    tokenize,
)
from zotero_cli_cc.core.rag_index import RagIndex
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.workspace import (
    Workspace,
    delete_workspace,
    list_workspaces,
    load_workspace,
    save_workspace,
    validate_name,
    workspace_exists,
    workspaces_dir,
)
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import format_items, format_workspace_list, format_workspace_query
from zotero_cli_cc.models import Collection, Item


@click.group("workspace")
def workspace_group() -> None:
    """Manage local workspaces for organizing papers by topic."""
    pass


@workspace_group.command("new")
@click.argument("name")
@click.option("--description", "-d", default="", help="Workspace description (topic context)")
@click.pass_context
def workspace_new(ctx: click.Context, name: str, description: str) -> None:
    """Create a new workspace."""
    json_out = ctx.obj.get("json", False)
    if not validate_name(name):
        emit_error(
            "validation_error",
            f"Invalid workspace name: '{name}'",
            output_json=json_out,
            hint="Use kebab-case (e.g., llm-safety, protein-folding)",
            context="workspace new",
        )
    if workspace_exists(name):
        emit_error(
            "conflict",
            f"Workspace '{name}' already exists",
            output_json=json_out,
            hint=f"Use 'zot workspace show {name}' to view it",
            context="workspace new",
        )
    ws = Workspace(
        name=name,
        created=datetime.now(timezone.utc).isoformat(),
        description=description,
    )
    save_workspace(ws)
    click.echo(f"Workspace created: {name}")


@workspace_group.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.pass_context
def workspace_delete(ctx: click.Context, name: str, yes: bool) -> None:
    """Delete a workspace."""
    json_out = ctx.obj.get("json", False)
    if not workspace_exists(name):
        emit_error(
            "not_found",
            f"Workspace '{name}' not found",
            output_json=json_out,
            hint="Use 'zot workspace list' to see available workspaces",
            context="workspace delete",
        )
    no_interaction = ctx.obj.get("no_interaction", False)
    if not yes and not no_interaction:
        if not click.confirm(f"Delete workspace '{name}'?"):
            click.echo("Cancelled.")
            return
    delete_workspace(name)
    click.echo(f"Workspace deleted: {name}")


@workspace_group.command("add")
@click.argument("name")
@click.argument("keys", nargs=-1, required=True)
@click.pass_context
def workspace_add(ctx: click.Context, name: str, keys: tuple[str, ...]) -> None:
    """Add items to a workspace by Zotero key."""
    json_out = ctx.obj.get("json", False)
    if not workspace_exists(name):
        emit_error(
            "not_found",
            f"Workspace '{name}' not found",
            output_json=json_out,
            hint="Use 'zot workspace new' to create it first",
            context="workspace add",
        )

    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        ws = load_workspace(name)
        added = 0
        for key in keys:
            item = reader.get_item(key)
            if item is None:
                click.echo(f"Warning: item '{key}' not found in Zotero library, skipped")
                continue
            if ws.add_item(key, item.title):
                added += 1
            else:
                click.echo(f"Skipped: '{key}' already in workspace")
        save_workspace(ws)
        click.echo(f"Added {added} item(s) to workspace '{name}'")
    finally:
        reader.close()


@workspace_group.command("remove")
@click.argument("name")
@click.argument("keys", nargs=-1, required=True)
@click.pass_context
def workspace_remove(ctx: click.Context, name: str, keys: tuple[str, ...]) -> None:
    """Remove items from a workspace by key."""
    json_out = ctx.obj.get("json", False)
    if not workspace_exists(name):
        emit_error(
            "not_found",
            f"Workspace '{name}' not found",
            output_json=json_out,
            hint="Use 'zot workspace list' to see available workspaces",
            context="workspace remove",
        )
    ws = load_workspace(name)
    removed = 0
    for key in keys:
        if ws.remove_item(key):
            removed += 1
    save_workspace(ws)
    click.echo(f"Removed {removed} item(s) from workspace '{name}'")


@workspace_group.command("list")
@click.pass_context
def workspace_list(ctx: click.Context) -> None:
    """List all workspaces."""
    json_out = ctx.obj.get("json", False)
    workspaces = list_workspaces()
    if not workspaces:
        click.echo("No workspaces found. Create one with: zot workspace new <name>")
        return
    click.echo(format_workspace_list(workspaces, output_json=json_out))


@workspace_group.command("show")
@click.argument("name")
@click.pass_context
def workspace_show(ctx: click.Context, name: str) -> None:
    """Show items in a workspace."""
    json_out = ctx.obj.get("json", False)
    detail = ctx.obj.get("detail", "standard")
    limit = ctx.obj.get("limit", 50)

    if not workspace_exists(name):
        emit_error(
            "not_found",
            f"Workspace '{name}' not found",
            output_json=json_out,
            hint="Use 'zot workspace list' to see available workspaces",
            context="workspace show",
        )

    ws = load_workspace(name)
    if not ws.items:
        click.echo(f"Workspace '{name}' is empty. Use 'zot workspace add {name} KEY' to add items.")
        return

    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        items = []
        missing = []
        for ws_item in ws.items[:limit]:
            item = reader.get_item(ws_item.key)
            if item is not None:
                items.append(item)
            else:
                missing.append(ws_item.key)
        if items:
            click.echo(format_items(items, output_json=json_out, detail=detail))
        for key in missing:
            click.echo(f"Warning: item '{key}' not found in Zotero library (may have been deleted)")
    finally:
        reader.close()


@workspace_group.command("export")
@click.argument("name")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "markdown", "bibtex"]),
    default="markdown",
    help="Export format (default: markdown)",
)
@click.pass_context
def workspace_export(ctx: click.Context, name: str, fmt: str) -> None:
    """Export workspace items for external use."""
    json_out = ctx.obj.get("json", False)
    if not workspace_exists(name):
        emit_error(
            "not_found",
            f"Workspace '{name}' not found",
            output_json=json_out,
            hint="Use 'zot workspace list' to see available workspaces",
            context="workspace export",
        )

    ws = load_workspace(name)
    if not ws.items:
        click.echo(f"Workspace '{name}' is empty.")
        return

    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        items = []
        for ws_item in ws.items:
            item = reader.get_item(ws_item.key)
            if item is not None:
                items.append(item)

        if not items:
            click.echo("No items could be resolved from Zotero library.")
            return

        if fmt == "json":
            click.echo(format_items(items, output_json=True))
        elif fmt == "bibtex":
            entries = []
            for item in items:
                bib = reader.export_citation(item.key, fmt="bibtex")
                if bib:
                    entries.append(bib)
            click.echo("\n\n".join(entries))
        else:
            # markdown (default)
            lines = [f"# Workspace: {name}"]
            desc_part = f" {ws.description}" if ws.description else ""
            lines.append(f"> {desc_part.strip()} ({len(items)} items)")
            lines.append("")
            for i, item in enumerate(items, 1):
                lines.append("---")
                lines.append(f"## {i}. {item.title}")
                authors = ", ".join(c.full_name for c in item.creators[:3])
                if len(item.creators) > 3:
                    authors += " et al."
                year = item.date or "N/A"
                lines.append(f"**Authors:** {authors} | **Year:** {year} | **Key:** {item.key}")
                if item.tags:
                    lines.append(f"**Tags:** {', '.join(item.tags)}")
                if item.abstract:
                    lines.append(f"**Abstract:** {item.abstract}")
                lines.append("")
            click.echo("\n".join(lines))
    finally:
        reader.close()


@workspace_group.command("import")
@click.argument("name")
@click.option("--collection", default=None, help="Import all items from a Zotero collection (name or key)")
@click.option("--tag", default=None, help="Import all items with this tag")
@click.option("--search", "search_query", default=None, help="Import items matching a search query")
@click.pass_context
def workspace_import_cmd(
    ctx: click.Context, name: str, collection: str | None, tag: str | None, search_query: str | None
) -> None:
    """Bulk import items into a workspace from collection, tag, or search."""
    json_out = ctx.obj.get("json", False)
    if not workspace_exists(name):
        emit_error(
            "not_found",
            f"Workspace '{name}' not found",
            output_json=json_out,
            hint="Use 'zot workspace new' to create it first",
            context="workspace import",
        )

    if not collection and not tag and not search_query:
        emit_error(
            "validation_error",
            "Must specify at least one of --collection, --tag, or --search",
            output_json=json_out,
            hint="Example: zot workspace import my-ws --search 'attention'",
            context="workspace import",
        )

    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        ws = load_workspace(name)
        items_to_import: list[Item] = []

        if collection:
            # Resolve collection name to key
            col_key = _resolve_collection_key(reader, collection)
            if col_key is None:
                emit_error(
                    "not_found",
                    f"Collection '{collection}' not found",
                    output_json=json_out,
                    hint="Use 'zot collections' to list available collections",
                    context="workspace import",
                )
            items_to_import.extend(reader.get_collection_items(col_key))

        if tag:
            # Search specifically for items with this tag
            result = reader.search(tag, limit=500)
            for item in result.items:
                if tag.lower() in [t.lower() for t in item.tags]:
                    items_to_import.append(item)

        if search_query:
            result = reader.search(search_query, limit=500)
            items_to_import.extend(result.items)

        # Dedup by key
        seen: set[str] = set()
        unique_items: list[Item] = []
        for item in items_to_import:
            if item.key not in seen:
                seen.add(item.key)
                unique_items.append(item)

        added = 0
        skipped = 0
        for item in unique_items:
            if ws.add_item(item.key, item.title):
                added += 1
            else:
                skipped += 1

        save_workspace(ws)
        click.echo(
            f"Imported {added} item(s) into workspace '{name}'"
            + (f" ({skipped} skipped, already present)" if skipped else "")
        )
    finally:
        reader.close()


@workspace_group.command("search")
@click.argument("query")
@click.option("--workspace", "ws_name", required=True, help="Workspace to search")
@click.pass_context
def workspace_search(ctx: click.Context, query: str, ws_name: str) -> None:
    """Search items within a workspace by title, author, or abstract."""
    json_out = ctx.obj.get("json", False)
    detail = ctx.obj.get("detail", "standard")
    limit = ctx.obj.get("limit", 50)

    if not workspace_exists(ws_name):
        emit_error(
            "not_found",
            f"Workspace '{ws_name}' not found",
            output_json=json_out,
            hint="Use 'zot workspace list' to see available workspaces",
            context="workspace search",
        )

    ws = load_workspace(ws_name)
    if not ws.items:
        click.echo(f"Workspace '{ws_name}' is empty.")
        return

    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id)
    try:
        query_lower = query.lower()
        matches = []
        for ws_item in ws.items:
            item = reader.get_item(ws_item.key)
            if item is None:
                continue
            # Case-insensitive substring match across title, authors, abstract, tags
            searchable = " ".join(
                filter(
                    None,
                    [
                        item.title,
                        " ".join(c.full_name for c in item.creators),
                        item.abstract or "",
                        " ".join(item.tags),
                    ],
                )
            ).lower()
            if query_lower in searchable:
                matches.append(item)

        if not matches:
            click.echo("No matching items found.")
            return

        click.echo(format_items(matches[:limit], output_json=json_out, detail=detail))
    finally:
        reader.close()


def _resolve_collection_key(reader: ZoteroReader, name_or_key: str) -> str | None:
    """Resolve a collection name or key to a collection key."""
    collections = reader.get_collections()

    def _search(colls: list[Collection]) -> str | None:
        for c in colls:
            if c.key == name_or_key or c.name.lower() == name_or_key.lower():
                return c.key
            found = _search(c.children)
            if found:
                return found
        return None

    return _search(collections)


@workspace_group.command("index")
@click.argument("name")
@click.option("--force", is_flag=True, help="Rebuild index from scratch")
@click.option("--extractor", default=None, help="PDF text extractor to use")
@click.pass_context
def workspace_index(ctx: click.Context, name: str, force: bool, extractor: str | None) -> None:
    """Build RAG index for a workspace."""
    json_out = ctx.obj.get("json", False)
    if extractor is None:
        from zotero_cli_cc.config import load_pdf_config

        extractor = load_pdf_config().extractor
    if not workspace_exists(name):
        emit_error(
            "not_found",
            f"Workspace '{name}' not found",
            output_json=json_out,
            hint="Use 'zot workspace list' to see available workspaces",
            context="workspace index",
        )

    ws = load_workspace(name)
    if not ws.items:
        click.echo(f"Workspace '{name}' is empty. Add items first with: zot workspace add {name} KEY")
        return

    cfg = load_config(profile=ctx.obj.get("profile"))
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    library_id = resolve_library_id(db_path, ctx.obj)
    reader = ZoteroReader(db_path, library_id=library_id, prefs_js_path=get_prefs_js_path(cfg))

    idx_path = workspaces_dir() / f"{name}.idx.sqlite"
    idx = RagIndex(idx_path)

    try:
        if force:
            idx.clear()

        already_indexed = idx.get_indexed_keys()
        to_index = [item for item in ws.items if item.key not in already_indexed]

        if not to_index:
            click.echo(f"Index for '{name}' is up to date ({len(already_indexed)} item(s) indexed).")
            return

        # PHASE 1 — Extract all PDF texts
        import pymupdf

        t0 = time.monotonic()

        # Gather items and PDF paths
        item_map: dict[str, Item] = {}
        pdf_paths_map: dict[str, Path] = {}  # key → path
        path_to_key: dict[Path, str] = {}  # path → key
        for ws_item in to_index:
            item = reader.get_item(ws_item.key)
            if item is None:
                click.echo(f"Warning: item '{ws_item.key}' not found in Zotero, skipped")
                continue
            item_map[ws_item.key] = item
            att = reader.get_pdf_attachment(ws_item.key)
            if att is not None and att.path is not None and att.path.exists():
                pdf_paths_map[ws_item.key] = att.path
                path_to_key[att.path] = ws_item.key

        # Compute total pages for header
        total_pages = 0
        for pdf_path in pdf_paths_map.values():
            doc = pymupdf.open(str(pdf_path))
            total_pages += len(doc)
            doc.close()

        # Determine extraction strategy
        pdf_texts: dict[str, str | Exception] = {}  # key → text or error
        pdf_errors: list[tuple[str, str, Exception]] = []

        if pdf_paths_map:
            if extractor == "mineru" and len(pdf_paths_map) > 1:
                # MinerU batch — has its own progress callback
                click.echo(f"  Extracting {len(pdf_paths_map)} PDFs ({total_pages} pages) with MinerU...")

                def batch_progress(phase: str, current: int, total: int, _pages: int) -> None:
                    sys.stderr.write(f"\r{' ' * 60}\r    [{phase}] [{current}/{total}]")
                    sys.stdout.flush()

                batch_results = convert_pdfs_to_text(list(pdf_paths_map.values()), "mineru", batch_progress)
                for path, text_or_err in batch_results.items():
                    key = path_to_key[path]
                    pdf_texts[key] = text_or_err
            else:
                # Sequential extraction (pymupdf or single MinerU)
                click.echo(f"  Extracting PDFs ({total_pages} pages)...")

                for i, (key, pdf_path) in enumerate(pdf_paths_map.items(), 1):
                    total_files = len(pdf_paths_map)

                    def make_seq_progress(file_idx: int, file_total: int) -> Callable[[str, int, int, int], None]:
                        def seq_progress(phase: str, current: int, chunk_total: int, _pages: int) -> None:
                            sys.stderr.write(
                                f"\r{' ' * 60}\r    [{phase}] [{file_idx}/{file_total}] chunks [{current}/{chunk_total}]"
                            )
                            sys.stdout.flush()

                        return seq_progress

                    sys.stderr.write(f"\r{' ' * 60}\r    [extract] [{i}/{total_files}]")
                    sys.stdout.flush()
                    try:
                        text = convert_pdf_to_text(
                            pdf_path, extractor_name=extractor, progress_callback=make_seq_progress(i, total_files)
                        )
                        pdf_texts[key] = text
                    except Exception as e:
                        pdf_texts[key] = e
                        pdf_errors.append((key, pdf_path.name, e))
                sys.stderr.write(f"\r{' ' * 60}\r")
                sys.stdout.flush()

        # PHASE 2 — Chunk all texts
        click.echo(f"  Chunking {len(to_index)} item(s)...")

        all_chunks: list[tuple[str, str, str, int]] = []  # (key, type, content, doc_len)

        for ws_item in to_index:
            item = item_map.get(ws_item.key)
            if item is None:
                continue

            authors = ", ".join(c.full_name for c in item.creators)
            meta_text = build_metadata_chunk(item.title, authors, item.abstract, item.tags)
            meta_tokens = len(tokenize(meta_text))
            all_chunks.append((ws_item.key, "metadata", meta_text, meta_tokens))

            if ws_item.key in pdf_texts:
                pdf_text_or_err = pdf_texts[ws_item.key]
                if isinstance(pdf_text_or_err, Exception):
                    pass
                else:
                    for chunk_content in chunk_text(pdf_text_or_err, item.title):
                        chunk_tokens = len(tokenize(chunk_content))
                        all_chunks.append((ws_item.key, "pdf", chunk_content, chunk_tokens))

        # PHASE 3 — Index all chunks (bulk insert, single commit)
        click.echo(f"  Indexing {len(all_chunks)} chunk(s)...")

        all_chunk_ids: list[int] = []
        all_chunk_texts: list[str] = []

        for i, (key, chunk_type, content, doc_len) in enumerate(all_chunks, 1):
            if i % 500 == 0 or i == len(all_chunks):
                sys.stderr.write(f"\r{' ' * 60}\r    [index] [{i}/{len(all_chunks)}]")
                sys.stdout.flush()

            chunk_id = idx.insert_chunk_no_commit(key, chunk_type, content, doc_len)
            tfs = compute_term_frequencies(tokenize(content))
            idx.insert_bm25_terms_no_commit(chunk_id, tfs)
            all_chunk_ids.append(chunk_id)
            all_chunk_texts.append(content)

        idx.commit()
        sys.stderr.write(f"\r{' ' * 60}\r")
        sys.stdout.flush()

        # Report extraction errors at end
        if pdf_errors:
            click.echo(f"\nWarning: {len(pdf_errors)} PDF extraction(s) failed:")
            for key, pdf_name, exc in pdf_errors:
                click.echo(f"  - {key} ({pdf_name}): {exc}")

        total_chunks = len(all_chunks)
        all_indexed_chunks = idx.get_all_chunks()
        total_docs = len(all_indexed_chunks)
        if total_docs > 0:
            total_len = sum(c.get("doc_len", 0) or len(tokenize(c["content"])) for c in all_indexed_chunks)
            avg_doc_len = total_len / total_docs
        else:
            avg_doc_len = 1.0
        idx.set_meta("total_docs", str(total_docs))
        idx.set_meta("avg_doc_len", str(avg_doc_len))
        idx.set_meta("chunk_count", str(total_docs))
        idx.set_meta("indexed_at", datetime.now(timezone.utc).isoformat())

        # Embeddings if configured
        mode_label = "BM25"
        emb_cfg = load_embedding_config()
        if emb_cfg.is_configured and all_chunk_texts:
            click.echo("  Generating embeddings...")

            def emb_progress(done: int, total: int) -> None:
                sys.stderr.write(f"\r{' ' * 60}\r    [embed] [{done}/{total}]")
                sys.stdout.flush()

            try:
                vectors = embed_texts(all_chunk_texts, emb_cfg, emb_progress)
                if vectors:
                    idx.set_embeddings_bulk(all_chunk_ids, vectors)
                    mode_label = "BM25 + embeddings"
            except Exception as e:
                click.echo(f"  [WARN] Embedding failed: {e}", err=True)
            sys.stderr.write(f"\r{' ' * 60}\r")
            sys.stdout.flush()

        elapsed = time.monotonic() - t0
        click.echo(f"Indexed {len(to_index)} item(s) ({total_chunks} chunks) in {elapsed:.1f}s [{mode_label}]")
    finally:
        idx.close()
        reader.close()


@workspace_group.command("query")
@click.argument("question")
@click.option("--workspace", "ws_name", required=True, help="Workspace to query")
@click.option("--top-k", default=5, help="Number of results (default: 5)")
@click.option(
    "--mode",
    type=click.Choice(["auto", "bm25", "semantic", "hybrid"]),
    default="auto",
    help="Retrieval mode",
)
@click.pass_context
def workspace_query(ctx: click.Context, question: str, ws_name: str, top_k: int, mode: str) -> None:
    """Query workspace papers with natural language."""
    json_out = ctx.obj.get("json", False)
    if not workspace_exists(ws_name):
        emit_error(
            "not_found",
            f"Workspace '{ws_name}' not found",
            output_json=json_out,
            hint="Use 'zot workspace list' to see available workspaces",
            context="workspace query",
        )

    idx_path = workspaces_dir() / f"{ws_name}.idx.sqlite"
    if not idx_path.exists():
        emit_error(
            "not_found",
            f"No index found for workspace '{ws_name}'",
            output_json=json_out,
            hint=f"Run 'zot workspace index {ws_name}' first",
            context="workspace query",
        )

    idx = RagIndex(idx_path)
    if not json_out:
        sys.stderr.write("\r    [loading index]")
        sys.stderr.flush()
    try:
        # Determine effective mode (cheap check instead of loading all embeddings)
        row = idx._conn.execute("SELECT 1 FROM chunks WHERE embedding IS NOT NULL LIMIT 1").fetchone()
        has_embeddings = row is not None
        if mode == "auto":
            effective_mode = "hybrid" if has_embeddings else "bm25"
        else:
            effective_mode = mode

        bm25_results: list[tuple[int, float, dict]] = []
        semantic_results: list[tuple[int, float, dict]] = []

        if effective_mode in ("bm25", "hybrid"):
            if json_out:
                bm25_results = bm25_score_chunks(idx, question, None)
            else:

                def bm25_progress(done: int, total: int) -> None:
                    sys.stderr.write(f"\r{' ' * 60}\r    [bm25] [{done}/{total}]")
                    sys.stdout.flush()

                bm25_results = bm25_score_chunks(idx, question, bm25_progress)

        if effective_mode in ("semantic", "hybrid") and has_embeddings:
            emb_cfg = load_embedding_config()
            if emb_cfg.is_configured:
                try:
                    q_vecs = embed_texts([question], emb_cfg)
                    if q_vecs:
                        if json_out:
                            semantic_results = semantic_score_chunks(idx, q_vecs[0], None)
                        else:

                            def sem_progress(done: int, total: int) -> None:
                                sys.stderr.write(f"\r{' ' * 60}\r    [semantic] [{done}/{total}]")
                                sys.stdout.flush()

                            semantic_results = semantic_score_chunks(idx, q_vecs[0], sem_progress)
                except Exception:
                    pass

        if not json_out:
            sys.stderr.write(f"\r{' ' * 60}\r")
            sys.stdout.flush()

        # Merge results
        if effective_mode == "hybrid" and bm25_results and semantic_results:
            merged = reciprocal_rank_fusion(bm25_results, semantic_results)
        elif semantic_results and effective_mode in ("semantic", "hybrid"):
            merged = semantic_results
        else:
            merged = bm25_results

        top = merged[:top_k]

        if not top:
            if json_out:
                click.echo("[]")
            else:
                click.echo("No results found.")
            return

        click.echo(format_workspace_query(top, mode=effective_mode, output_json=json_out))
    finally:
        idx.close()
