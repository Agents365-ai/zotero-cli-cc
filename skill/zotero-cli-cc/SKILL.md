---
name: zotero-cli
description: "Use when user mentions papers, references, citations, Zotero, literature, bibliography, or needs to search/read/export academic papers. Provides guidance for using the zot CLI tool to interact with Zotero libraries."
version: 0.1.0
---

# Zotero CLI Skill for Claude Code

Use the `zot` command to interact with the user's local Zotero library. Reads are instant (local SQLite), writes go through Zotero Web API.

## When to Activate

- User mentions: papers, references, citations, Zotero, literature, bibliography, DOI, BibTeX
- User asks to search, read, export, or manage academic references
- User needs to add papers by DOI or URL
- User is writing a paper and needs citations

## Core Principle

**Always use `--json` when processing results programmatically.** Human-readable output is for display only.

## Command Reference

### Search & Browse

```bash
# Search across title, author, tags, fulltext
zot --json search "transformer attention"

# Filter by collection
zot --json search "BERT" --collection "NLP"

# List items (optionally filtered)
zot --json list --collection "Machine Learning" --limit 10

# View item details (metadata + abstract + notes)
zot --json read ITEMKEY

# Find related items
zot --json relate ITEMKEY
```

### Notes & Tags

```bash
# View notes
zot --json note ITEMKEY

# Add a note (write operation, needs API credentials)
zot note ITEMKEY --add "Key finding: ..."

# View tags
zot --json tag ITEMKEY

# Add/remove tags
zot tag ITEMKEY --add "important"
zot tag ITEMKEY --remove "to-read"
```

### Citation Export

```bash
# BibTeX (default)
zot export ITEMKEY

# JSON format
zot export ITEMKEY --format json
```

### Item Management (Write Operations)

```bash
# Add by DOI
zot add --doi "10.1038/s41586-023-06139-9"

# Add by URL
zot add --url "https://arxiv.org/abs/2301.00001"

# Delete (moves to trash)
zot --no-interaction delete ITEMKEY
```

### Collections

```bash
# List all collections (tree view)
zot --json collection list

# Items in a collection
zot --json collection items COLLECTIONKEY

# Create collection
zot collection create "New Project"

# Move item to collection
zot collection move ITEMKEY COLLECTIONKEY

# Rename / delete collection
zot collection rename COLLECTIONKEY "New Name"
zot collection delete COLLECTIONKEY

# AI-powered batch reorganize (from JSON plan)
zot collection reorganize plan.json
```

### PDF & Summarization

```bash
# Extract full PDF text (cached automatically)
zot --json pdf ITEMKEY

# Extract specific pages
zot pdf ITEMKEY --pages 1-5

# Structured summary optimized for AI consumption
zot --json summarize ITEMKEY

# Batch export all items for AI classification
zot summarize-all
```

### Configuration

```bash
# Initialize API credentials (write operations only)
zot config init

# Non-interactive setup (for scripts/automation)
zot --no-interaction config init --library-id "123" --api-key "abc"

# Switch profile
zot --profile lab search "CRISPR"

# Manage profiles
zot config profile list
zot config profile set lab

# PDF cache management
zot config cache stats
zot config cache clear
```

## Global Flags

| Flag | Purpose |
|------|---------|
| `--json` | JSON output (ALWAYS use for programmatic processing) |
| `--limit N` | Limit results (default: 50) |
| `--detail minimal` | Only key/title/authors/year — saves tokens |
| `--detail full` | Include extra fields |
| `--no-interaction` | Suppress prompts (for automation) |
| `--profile NAME` | Use a specific config profile |

## Workflow Patterns

### Pattern 1: Find and Read a Paper

```bash
# Step 1: Search
zot --json search "single cell RNA sequencing"

# Step 2: Read details of interesting result
zot --json read K853PGUG

# Step 3: Get full PDF text if needed
zot --json pdf K853PGUG
```

### Pattern 2: Export Citations for a Paper

```bash
# Get BibTeX for LaTeX
zot export K853PGUG

# Get structured JSON for programmatic use
zot --json export K853PGUG --format json
```

### Pattern 3: Literature Survey of a Collection

```bash
# List all items in a collection
zot --json --detail minimal collection items COLLKEY

# Read each one with minimal detail to save tokens
zot --json --detail minimal read KEY1
zot --json --detail minimal read KEY2

# Deep dive into promising papers
zot --json --detail full read KEY3
zot --json pdf KEY3
```

### Pattern 4: Add and Organize New Papers

```bash
# Add paper by DOI
zot add --doi "10.1038/s41592-024-02201-0"

# Tag it
zot tag NEWKEY --add "single-cell"
zot tag NEWKEY --add "methods"
```

### Pattern 5: AI-Powered Library Reorganization

```bash
# Step 1: Export all abstracts
zot summarize-all > abstracts.json

# Step 2: AI analyzes and generates a classification plan
# (Claude reads abstracts.json, creates plan.json)

# Step 3: Execute the plan
zot collection reorganize plan.json
```

Plan file format:
```json
{
  "collections": [
    {"name": "Machine Learning", "items": ["KEY1", "KEY2"]},
    {"name": "Reinforcement Learning", "parent": "Machine Learning", "items": ["KEY3"]}
  ]
}
```

### Pattern 6: Batch Search with Token Efficiency

```bash
# First pass: minimal detail to scan many results
zot --json --detail minimal --limit 20 search "spatial transcriptomics"

# Second pass: full detail on selected items
zot --json --detail full read SELECTED_KEY
```

## JSON Output Parsing

All `--json` output follows consistent structures:

**Search/List result** — array of items:
```json
[{"key": "ABC123", "title": "...", "creators": [...], "date": "2024", ...}]
```

**Read result** — single item with notes:
```json
{"key": "ABC123", "title": "...", "notes": [{"key": "N1", "content": "..."}], ...}
```

**Error result** — with recovery hints:
```json
{"error": "Item 'XYZ' not found", "context": "read", "hint": "Run 'zot search' to find valid keys"}
```

## Important Notes

- **Read operations** work offline with zero config — just install `zot`
- **Write operations** (add, delete, note --add, tag --add/--remove) need API credentials via `zot config init`
- **PDF cache** — full PDF extractions are cached automatically. Use `zot config cache clear` if stale
- **Profiles** — use `--profile` to switch between personal/lab/group Zotero libraries
- **After writes** — Zotero desktop needs to sync to reflect changes in the local database
- **Item keys** are 8-character alphanumeric strings like `K853PGUG`
