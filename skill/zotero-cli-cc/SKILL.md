---
name: zotero-cli
description: "Use when user mentions papers, references, citations, Zotero, literature, bibliography, or needs to search/read/export academic papers. Routes between zot (fast local SQLite) and rak (semantic/hybrid search) automatically."
version: 0.2.0
---

# Zotero CLI Skill for Claude Code

Two complementary tools for Zotero:

| Tool | Purpose | Speed |
|------|---------|-------|
| **`zot`** | CRUD, reading, export, PDF, stats — local SQLite | Instant |
| **`rak`** | Semantic/hybrid search, Q&A — vector + BM25 | ~2s |

**Always use `--json` when processing results programmatically.**

## Routing Rules

| User Intent | Command | Why |
|-------------|---------|-----|
| Search by title/author/tag | `zot --json search "transformer"` | Fast metadata match |
| **Search paper content / fulltext** | **`rak --json search "query" --hybrid`** | **zot fulltext is word-level LIKE only; rak has BM25 + vector** |
| Semantic search ("papers about cell fate") | `rak --json search "cell fate" --hybrid` | Needs semantic understanding |
| Similarity search ("papers like this one") | `rak --json search "..." --hybrid` | Needs embeddings |
| Read/view a paper | `zot --json read KEY` | Direct lookup |
| Export citation | `zot export KEY` | Local data |
| Add/delete/tag/note | `zot ...` | All write ops |
| PDF full text extraction | `zot --json pdf KEY` | Local file access |
| Library stats | `zot --json stats` | Local aggregation |
| Open PDF/URL | `zot open KEY` or `zot open --url KEY` | System open |
| Ask question about papers | `rak ask "question" --hybrid` | Needs RAG pipeline |

**Rule of thumb**: Use `zot` for metadata lookup and all CRUD. Use `rak` for any search that involves paper content, semantic meaning, or Q&A. When in doubt about search, prefer `rak --hybrid` — it covers both keyword and semantic matching.

**If `rak` is not installed**, fall back to `zot` for everything. Check with `which rak`.

---

## zot — Zotero CLI (Core Tool)

### Search & Browse

```bash
zot --json search "transformer attention"
zot --json search "BERT" --collection "NLP"
zot --json list --collection "Machine Learning" --limit 10
zot --json read ITEMKEY
zot --json relate ITEMKEY
```

### Notes & Tags

```bash
zot --json note ITEMKEY
zot note ITEMKEY --add "Key finding: ..."
zot --json tag ITEMKEY
zot tag ITEMKEY --add "important"
zot tag ITEMKEY --remove "to-read"
```

### Citation Export

```bash
zot export ITEMKEY                    # BibTeX
zot export ITEMKEY --format csl-json  # CSL-JSON
zot export ITEMKEY --format json      # Raw JSON
```

### Item Management (Write Ops)

```bash
zot add --doi "10.1038/s41586-023-06139-9"
zot add --url "https://arxiv.org/abs/2301.00001"
zot --no-interaction delete ITEMKEY
```

### Collections

```bash
zot --json collection list
zot --json collection items COLLECTIONKEY
zot collection create "New Project"
zot collection move ITEMKEY COLLECTIONKEY
zot collection rename COLLECTIONKEY "New Name"
zot collection delete COLLECTIONKEY
```

### PDF & Summarization

```bash
zot --json pdf ITEMKEY
zot pdf ITEMKEY --pages 1-5
zot --json summarize ITEMKEY
zot summarize-all
```

### Utilities

```bash
zot --json stats                     # Library statistics
zot open ITEMKEY                     # Open PDF in system viewer
zot open --url ITEMKEY               # Open URL/DOI in browser
```

### Configuration

```bash
zot config init
zot config profile list
zot config profile set lab
zot config cache stats
zot config cache clear
```

### Global Flags

| Flag | Purpose |
|------|---------|
| `--json` | JSON output (ALWAYS use for programmatic processing) |
| `--limit N` | Limit results (default: 50) |
| `--detail minimal` | Only key/title/authors/year — saves tokens |
| `--detail full` | Include extra fields |
| `--no-interaction` | Suppress prompts (for automation) |
| `--profile NAME` | Use a specific config profile |

---

## rak — Zotero RAG Search (Semantic Search)

### Prerequisites

```bash
# Check if rak is available
which rak

# Index must be built before first search
rak index
```

### Search

```bash
# Hybrid search (recommended — vector + BM25)
rak --json search "cell fate determination" --hybrid

# With filters
rak --json search "CRISPR" --hybrid --limit 5 --collection "Methods" --tag "review"
```

### Q&A (RAG)

```bash
# Single question
rak ask "What are the main clustering methods for single-cell?" --hybrid

# Interactive chat
rak chat --hybrid
```

### Export Search Results

```bash
rak export "single cell" --format csv
rak export "CRISPR" --format bibtex --output refs.bib
```

### Index Management

```bash
rak index              # Incremental index (new items only)
rak index --full       # Full rebuild
rak status             # Show index status
rak clear --yes        # Delete all indexes
```

---

## Workflow Patterns

### Pattern 1: Find and Read a Paper

```bash
# Step 1: Search (use zot for keyword, rak for semantic)
zot --json search "single cell RNA sequencing"

# Step 2: Read details
zot --json read K853PGUG

# Step 3: Full PDF text if needed
zot --json pdf K853PGUG
```

### Pattern 2: Semantic Literature Discovery

```bash
# Step 1: Semantic search with rak
rak --json search "mechanisms of drug resistance in cancer" --hybrid --limit 10

# Step 2: Read promising results with zot
zot --json --detail full read KEY1
zot --json pdf KEY1 --pages 1-5
```

### Pattern 3: AI-Powered Library Reorganization

```bash
# Step 1: Export all abstracts
zot summarize-all > abstracts.json

# Step 2: AI generates classification plan
# Step 3: Execute
zot collection reorganize plan.json
```

### Pattern 4: Q&A Over Library

```bash
# Ask a question — rak retrieves relevant papers + generates answer
rak ask "Compare attention mechanisms in transformer variants" --hybrid --context 10
```

## Important Notes

- **`zot` read operations** work offline with zero config
- **`zot` write operations** need API credentials via `zot config init`
- **`rak`** requires `rak index` before first search
- **PDF cache** — `zot` caches PDF extractions automatically
- **Item keys** are 8-character alphanumeric strings like `K853PGUG`
- **After writes** — Zotero desktop needs to sync, then `rak index` to update search index
