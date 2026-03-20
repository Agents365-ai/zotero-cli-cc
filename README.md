# zotero-cli-cc

Zotero CLI for Claude Code — fast local reads via SQLite, safe writes via Web API.

## Install

```bash
uv tool install zotero-cli-cc
# or
pip install zotero-cli-cc
```

## Setup

```bash
# Configure Web API credentials (needed for write operations only)
zot config init
```

Read operations work immediately with zero configuration if Zotero data is at the default location (`~/Zotero`).

## Usage

```bash
# Search
zot search "transformer attention"
zot search "BERT" --collection "NLP"

# List
zot list --collection "Machine Learning" --limit 10

# Read details
zot read ATTN001

# Notes
zot note ATTN001                    # View notes
zot note ATTN001 --add "Important"  # Add note (Web API)

# Export citation
zot export ATTN001                  # BibTeX
zot export ATTN001 --format json    # JSON

# Add / Delete
zot add --doi "10.1234/example"
zot delete ATTN001 --yes

# Tags
zot tag ATTN001                     # View tags
zot tag ATTN001 --add "important"   # Add tag (Web API)

# Collections
zot collection list
zot collection items COLML01
zot collection create "New Project"

# Summarize (structured output for Claude Code)
zot summarize ATTN001

# PDF text extraction
zot pdf ATTN001 --pages 1-5

# Related items
zot relate ATTN001

# JSON output
zot --json search "attention"
```

## Architecture

- **Reads**: Direct SQLite access to `~/Zotero/zotero.sqlite` (read-only, offline, fast)
- **Writes**: Zotero Web API via pyzotero (safe, Zotero-aware)
- **PDF**: Direct extraction from `~/Zotero/storage/` via pymupdf

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ZOT_DATA_DIR` | Override Zotero data directory path |
| `ZOT_LIBRARY_ID` | Override library ID (for write operations) |
| `ZOT_API_KEY` | Override API key (for write operations) |

## License

MIT
