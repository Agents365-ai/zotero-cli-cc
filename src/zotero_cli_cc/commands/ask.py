from __future__ import annotations

import click

from zotero_cli_cc.config import load_embedding_config
from zotero_cli_cc.core.rag import (
    bm25_score_chunks,
    build_evidence_pack,
    embed_texts,
    semantic_score_chunks,
)
from zotero_cli_cc.core.rag_index import RagIndex
from zotero_cli_cc.core.workspace import workspace_exists, workspaces_dir
from zotero_cli_cc.exit_codes import emit_error
from zotero_cli_cc.formatter import emit_progress, format_ask


@click.command("ask")
@click.argument("question")
@click.option("--workspace", "ws_name", required=True, help="Workspace to ask against")
@click.option("--evidence-k", default=12, help="Number of evidence chunks to retrieve (default: 12)")
@click.option(
    "--mode",
    type=click.Choice(["auto", "bm25", "semantic", "hybrid"]),
    default="auto",
    help="Retrieval mode",
)
@click.pass_context
def ask_cmd(ctx: click.Context, question: str, ws_name: str, evidence_k: int, mode: str) -> None:
    """Retrieve a citation-keyed evidence pack to answer a question from a workspace.

    Unlike `workspace query` (which dumps ranked chunks), `ask` returns evidence
    tagged with Zotero item keys plus answer instructions, so the calling agent
    can synthesize a grounded, cited answer. zot does not call an LLM itself.

    \b
    Examples:
      zot ask "how does attention scale?" --workspace transformers
      zot --json ask "what dataset was used?" --workspace papers --evidence-k 8
    """
    json_out = ctx.obj.get("json", False)
    if not workspace_exists(ws_name):
        emit_error(
            "not_found",
            f"Workspace '{ws_name}' not found",
            output_json=json_out,
            hint="Use 'zot workspace list' to see available workspaces",
            context="ask",
        )

    idx_path = workspaces_dir() / f"{ws_name}.idx.sqlite"
    if not idx_path.exists():
        emit_error(
            "not_found",
            f"No index found for workspace '{ws_name}'",
            output_json=json_out,
            hint=f"Run 'zot workspace index {ws_name}' first",
            context="ask",
        )

    idx = RagIndex(idx_path)
    try:
        has_emb = idx._conn.execute("SELECT 1 FROM chunks WHERE embedding IS NOT NULL LIMIT 1").fetchone() is not None
        if mode == "auto":
            effective_mode = "hybrid" if has_emb else "bm25"
        else:
            effective_mode = mode

        bm25_results: list[tuple[int, float, dict]] = []
        semantic_results: list[tuple[int, float, dict]] = []

        if effective_mode in ("bm25", "hybrid"):
            emit_progress("progress", phase="ask", step="bm25")
            bm25_results = bm25_score_chunks(idx, question)

        if effective_mode in ("semantic", "hybrid") and has_emb:
            emb_cfg = load_embedding_config()
            if emb_cfg.is_configured:
                emit_progress("progress", phase="ask", step="semantic")
                q_vecs = embed_texts([question], emb_cfg)
                if q_vecs:
                    semantic_results = semantic_score_chunks(idx, q_vecs[0])

        evidence = build_evidence_pack(bm25_results, semantic_results, effective_mode, evidence_k)
        click.echo(format_ask(question, evidence, effective_mode, output_json=json_out))
    finally:
        idx.close()
