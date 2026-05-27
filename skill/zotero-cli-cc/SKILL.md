---
name: zotero-cli-cc
description: Use when user mentions papers, references, citations, Zotero, literature, bibliography, workspaces, or needs to search, read, export, or organize documents. Handles all zot CLI operations including workspace-based RAG search.
---

# Zotero CLI Skill

`zot` is an all-in-one Zotero CLI: search, CRUD, PDF extraction, citation export, and workspace-based RAG. Local SQLite for reads, Zotero Web API for writes.

## Quick Start

```bash
zot search "transformer attention"       # Search papers
zot --json read ABC123                   # View paper details (JSON)
zot export ABC123                        # BibTeX export
zot workspace query "RLHF" --workspace my-ws  # RAG search
```

## Critical Rules

1. **Always use `--json`** for programmatic processing (auto-enabled when stdout is not a TTY).
2. **Windows CJK encoding**: On Windows with CJK locale, `zot` auto-reconfigures stdout to UTF-8 (v0.6+). For older versions or subprocess calls, set `PYTHONIOENCODING=utf-8`. See `references/windows-encoding.md`.
3. **Write safety**: Use `--dry-run` to preview mutations. Pass `--idempotency-key` on retries.
4. **Large PDFs**: Use `--outline` first, then `--section SECID` to extract selectively. Avoid pulling full text when >20k chars.
5. **Workspace RAG index**: Do not `--force` rebuild without user confirmation — it is slow.
6. **Canonical schema**: Run `zot schema <cmd>` for exhaustive flags, types, and safety tiers.

## Routing Table

| User Intent | Command |
|-------------|---------|
| Search metadata | `zot --json search "query"` |
| Read item detail | `zot --json read KEY` |
| Export BibTeX/RIS/JSON | `zot export KEY --format bibtex` |
| Formatted citation | `zot cite KEY --style apa` |
| Batch import DOIs | `zot add --from-file dois.txt` |
| Add single item | `zot add --doi "10.1038/..."` |
| Update metadata | `zot update KEY --title "New"` |
| Delete item | `zot --no-interaction delete KEY` |
| PDF full text | `zot --json pdf KEY` |
| PDF outline | `zot --json pdf --outline KEY` |
| PDF section | `zot --json pdf --section SECID KEY` |
| Collection list | `zot --json collection list` |
| Collection items | `zot --json collection items COLLKEY` |
| Find duplicates | `zot --json duplicates` |
| Recent items | `zot --json recent --days 7` |
| Library stats | `zot --json stats` |
| Workspace create | `zot workspace new NAME` |
| Workspace RAG query | `zot workspace query "q" --workspace NAME` |
| Group library | `zot --library group:ID search "q"` |

**Rule of thumb**: `zot search` for quick metadata lookups. `zot workspace query` for deep content search over curated papers.

## Global Flags

| Flag | Purpose |
|------|---------|
| `--json` | JSON output (always use for programmatic processing) |
| `--limit N` | Limit results (default: 50) |
| `--detail minimal` | Only key/title/authors/year — saves tokens |
| `--detail full` | All fields |
| `--no-interaction` | Suppress prompts (automation) |
| `--verbose` | Debug output |

## Key Facts

- Read ops work offline with zero config
- Write ops need API credentials (`zot config init`)
- Item keys are 8-char alphanumeric strings (e.g. `K853PGUG`)
- Non-TTY stdout auto-emits JSON envelope — agents never need explicit `--json`

## References

- `references/commands.md` — Full command reference with examples
- `references/workspaces.md` — Workspace management and RAG deep dive
- `references/workflows.md` — Common multi-step workflow patterns
- `references/windows-encoding.md` — Windows CJK encoding fix
