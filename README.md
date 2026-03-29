# zot — Let Zotero Fly in Your Terminal

<p align="center">
  <img src="asserts/banner_official.png" alt="zotero-cli-cc banner" width="720">
</p>

<p align="center">
  <a href="https://pypi.org/project/zotero-cli-cc/"><img src="https://img.shields.io/pypi/v/zotero-cli-cc?color=blue" alt="PyPI version"></a>
  <a href="https://github.com/Agents365-ai/zotero-cli-cc/actions/workflows/ci.yml"><img src="https://github.com/Agents365-ai/zotero-cli-cc/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/zotero-cli-cc/"><img src="https://img.shields.io/pypi/pyversions/zotero-cli-cc" alt="Python versions"></a>
  <a href="https://creativecommons.org/licenses/by-nc/4.0/"><img src="https://img.shields.io/badge/license-CC%20BY--NC%204.0-lightgrey" alt="License"></a>
</p>

[中文](README_CN.md)

## Introduction

`zotero-cli-cc` is a Zotero CLI designed for [Claude Code](https://claude.ai/code).

**Core Features:**
- **Reads**: Direct local SQLite database access — zero config, offline, millisecond response
- **Writes**: Safe writes through Zotero Web API — Zotero fully aware of changes
- **PDF**: Extract full text from local PDF storage with automatic caching
- **Workspace**: Organize papers by topic with local workspaces + built-in RAG search

**Search and read papers without launching Zotero desktop.**

## Using with Claude Code

In any Claude Code session, use natural language:

```
Search my Zotero for single cell papers
→ Claude runs: zot --json search "single cell"

Show me details of this paper
→ Claude runs: zot --json read ABC123

Export BibTeX for this paper
→ Claude runs: zot export ABC123
```

Install the zotero-cli skill so Claude Code automatically recognizes literature-related requests:

```bash
# Install skill (copy skill/zotero-cli-cc/ to ~/.claude/skills/)
cp -r skill/zotero-cli-cc ~/.claude/skills/
```

## Install

```bash
# Recommended
uv tool install zotero-cli-cc

# Or
pipx install zotero-cli-cc

# Or
pip install zotero-cli-cc
```

Upgrade to the latest version:

```bash
uv tool upgrade zotero-cli-cc    # uv
pipx upgrade zotero-cli-cc       # pipx
pip install -U zotero-cli-cc     # pip
```

## Setup

```bash
# Configure Web API credentials (write operations only)
zot config init
```

### Data Directory

> **Data directory** refers to the folder containing the `zotero.sqlite` database file (not the Zotero installation directory or the PDF sync directory). You can find it in Zotero Settings → Advanced → "Data Directory Location".

Read operations work out of the box. `zot` automatically detects the Zotero data directory:

| Platform | Detection Order |
|----------|----------------|
| **Windows** | Registry `HKCU\Software\Zotero\Zotero\dataDir` → `%APPDATA%\Zotero` → `%LOCALAPPDATA%\Zotero` |
| **macOS / Linux** | `~/Zotero` |

If your Zotero data is not in the default location, specify it:

```bash
# Option 1: Config file (recommended)
zot config init --data-dir "D:\MyZotero"

# Option 2: Environment variable
export ZOT_DATA_DIR="/path/to/zotero/data"

# Option 3: Edit config file manually
# Edit ~/.config/zot/config.toml
```

Example config file:

```toml
[zotero]
data_dir = "D:\\MyZotero"
library_id = "12345"
api_key = "xxx"

[output]
default_format = "table"
limit = 50

[export]
default_style = "bibtex"
```

### API Credentials

Write operations require an API Key from https://www.zotero.org/settings/keys.

### MCP Server Mode

zotero-cli-cc supports [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) and can be used in MCP-compatible clients like LM Studio, Claude Desktop, and Cursor.

**Install MCP Support:**

```bash
pip install zotero-cli-cc[mcp]
```

**Start MCP Server:**

```bash
zot mcp serve
```

**Client Configuration (LM Studio / Claude Desktop / Cursor):**

```json
{
  "mcpServers": {
    "zotero": {
      "command": "zot",
      "args": ["mcp", "serve"]
    }
  }
}
```

MCP mode provides 17 tools covering search, reading, PDF extraction, note management, tag management, citation export, and more.

## Commands

### Search & Browse

> **How search works:** `zot search` matches keywords across four layers: ① titles & abstracts ② author names ③ tags ④ PDF fulltext index. For deeper content search with BM25 ranking and optional semantic matching, use `zot workspace query` — it indexes metadata + full PDF text and supports hybrid BM25 + embedding retrieval.

```bash
# Search across title, author, tags, fulltext
zot search "transformer attention"

# Filter by collection
zot search "BERT" --collection "NLP"

# List items
zot list --collection "Machine Learning" --limit 10

# View item details (metadata + abstract + notes)
zot read ABC123

# Find related items
zot relate ABC123
```

### Notes & Tags

```bash
# View/add notes
zot note ABC123
zot note ABC123 --add "This paper proposes a new attention mechanism"

# View/add/remove tags
zot tag ABC123
zot tag ABC123 --add "important"
zot tag ABC123 --remove "to-read"
```

### Citation Export

```bash
zot export ABC123                    # BibTeX
zot export ABC123 --format csl-json  # CSL-JSON
zot export ABC123 --format ris       # RIS
zot export ABC123 --format json      # JSON

# Format citation and copy to clipboard
zot cite ABC123                      # APA (default)
zot cite ABC123 --style nature       # Nature
zot cite ABC123 --style vancouver    # Vancouver
```

### Item Management

```bash
zot add --doi "10.1038/s41586-023-06139-9"       # Add by DOI
zot add --url "https://arxiv.org/abs/2301.00001"  # Add by URL
zot add --from-file dois.txt                      # Batch import from file
zot delete ABC123 --yes                           # Delete (move to trash)
```

### Collections

```bash
zot collection list                # List all collections (tree view)
zot collection items COLML01       # View items in a collection
zot collection create "New Project"  # Create a new collection
```

### Workspaces

> **Why workspaces?** Zotero collections are great for permanent library organization, but research often requires temporary, cross-cutting groupings — "all papers for my ICML submission", "papers to discuss at lab meeting", or "references for Chapter 3". Workspaces fill this gap: they're lightweight, local-only views that don't modify your Zotero library. Each workspace is a simple TOML file at `~/.config/zot/workspaces/<name>.toml` containing item key references — no API key needed, no syncing side effects. Combined with built-in RAG indexing, workspaces become a powerful bridge between your Zotero library and AI coding assistants like Claude Code.

```bash
# Create and populate a workspace
zot workspace new llm-safety --description "LLM alignment papers"
zot workspace add llm-safety ABC123 DEF456 GHI789
zot workspace import llm-safety --collection "Alignment"   # Bulk import from collection
zot workspace import llm-safety --tag "safety"              # or by tag
zot workspace import llm-safety --search "RLHF"            # or by search

# Browse workspace
zot workspace list                          # List all workspaces
zot workspace show llm-safety               # View items with metadata
zot workspace search "reward" --workspace llm-safety  # Search within workspace

# Export for AI consumption
zot workspace export llm-safety                       # Markdown (for Claude Code)
zot workspace export llm-safety --format json         # JSON
zot workspace export llm-safety --format bibtex       # BibTeX

# Built-in RAG: index and query
zot workspace index llm-safety              # Build BM25 index (metadata + PDF text)
zot workspace query "reward hacking methods" --workspace llm-safety

# Manage
zot workspace remove llm-safety ABC123      # Remove item
zot workspace delete llm-safety --yes       # Delete workspace
```

**Optional semantic search** — configure an embedding endpoint for hybrid BM25 + vector retrieval:

```bash
export ZOT_EMBEDDING_URL="https://api.jina.ai/v1/embeddings"
export ZOT_EMBEDDING_KEY="your-jina-key"   # 10M free tokens
zot workspace index llm-safety --force      # Rebuild with embeddings
zot workspace query "reward hacking" --workspace llm-safety --mode hybrid
```

### Profiles & Cache

```bash
zot config profile list            # List all config profiles
zot config profile set lab         # Set default profile
zot config cache stats             # Show PDF cache statistics
zot config cache clear             # Clear PDF cache
```

### Preprint Status Check

```bash
# Check if arXiv/bioRxiv/medRxiv preprints have been published (dry-run)
zot update-status

# Actually update Zotero metadata for published papers
zot update-status --apply

# Check a single item
zot update-status ABC123

# Check items in a collection
zot update-status --collection "scRNA-seq" --limit 20
```

Uses the [Semantic Scholar API](https://www.semanticscholar.org/product/api). Optional API key for faster rate limits:

```bash
export S2_API_KEY=your_key_here   # in ~/.zshrc or ~/.bashrc
```

### AI Features

```bash
zot summarize ABC123               # Structured summary (optimized for Claude Code)
zot pdf ABC123                     # Extract PDF full text
zot pdf ABC123 --pages 1-5         # Extract specific pages
```

### Global Flags

```bash
zot --json search "attention"              # JSON output
zot --limit 5 list                         # Limit results
zot --detail minimal search "attention"    # Minimal output (key/title/authors/year only)
zot --detail full read ABC123              # Full output (including extra fields)
zot --no-interaction delete ABC123         # Skip confirmation prompts (AI/script mode)
zot --profile lab search "CRISPR"          # Use a specific config profile
zot --version                              # Show version
```

### Shell Completions

```bash
# Zsh (recommended)
zot completions zsh >> ~/.zshrc

# Bash
zot completions bash >> ~/.bashrc

# Fish
zot completions fish > ~/.config/fish/completions/zot.fish
```

Restart your terminal or `source` the config file to enable tab completions.

## Comparison with Similar Tools

| Feature | **zotero-cli-cc** | [pyzotero-cli](https://github.com/chriscarrollsmith/pyzotero-cli) | [zotero-cli](https://github.com/jbaiter/zotero-cli) | [zotero-cli-tool](https://github.com/dhondta/zotero-cli) | [zotero-mcp](https://github.com/54yyyu/zotero-mcp) | [cookjohn/zotero-mcp](https://github.com/cookjohn/zotero-mcp) | [ZoteroBridge](https://github.com/Combjellyshen/ZoteroBridge) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Direct SQLite Read** | **✅** | ❌ | ❌ (cache only) | ❌ | ❌ | ❌ (plugin) | ✅ |
| **Offline Read** | **✅** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **No Zotero Running** | **✅** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Zero-Config Read** | **✅** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Safe Write (Web API)** | **✅** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ (direct SQLite) |
| **PDF Full-Text** | **✅** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **AI Coding Assistant** | **✅ Claude Code** | Partial | ❌ | ❌ | Claude/ChatGPT | Claude/Cursor | Claude/Cursor |
| **Terminal CLI** | **✅** | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **MCP Protocol** | **✅** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **JSON Output** | ✅ | ✅ | ❌ | ❌ | N/A | N/A | N/A |
| **Note Management** | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ |
| **Collections** | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Citation Export** | ✅ BibTeX/CSL-JSON/RIS | ✅ | ❌ | ✅ Excel | ❌ | ❌ | ❌ |
| **Semantic Search** | **✅ Built-in (workspace RAG)** | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **Detail Levels** | **✅** | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **Multi-Profile** | **✅** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **PDF Cache** | **✅** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Library Maintenance** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Language** | Python | Python | Python | Python | Python | TypeScript | TypeScript |
| **Active** | ✅ 2026 | ✅ 2025 | ❌ 2024 | ✅ 2026 | ✅ 2026 | ✅ 2026 | ✅ 2026 |

### Why zotero-cli-cc?

> **The only actively maintained Python CLI that reads Zotero's local SQLite database directly.**

- **Fast**: Millisecond response, no network latency
- **Offline**: No internet, no Zotero desktop needed
- **Zero-Config**: Install and go, no API key for reads
- **AI-Native**: Built for Claude Code, `--json` output for AI consumption
- **Safe**: Read/write separation — writes go through Web API to protect DB integrity
- **Terminal-Native**: The only CLI combining local SQLite reads with safe Web API writes; MCP tools require AI client, not usable in terminal

## Architecture

```mermaid
graph TD
    A["zot CLI (Click)<br>search | list | read | workspace | ..."] --> B["Core Services"]
    C["MCP Server (FastMCP)<br>stdio transport"] --> B

    subgraph B["Core Services"]
        R["ZoteroReader<br>(SQLite read-only)"]
        W["ZoteroWriter<br>(Web API)"]
        RAG["RAG Engine<br>(BM25 + Embeddings)"]
    end

    R --> D["SQLite<br>~/Zotero/zotero.sqlite"]
    W --> E["Zotero Web API<br>(remote)"]
    D --> F["~/Zotero/storage/*.pdf"]
    RAG --> G["Workspace Index<br>~/.config/zot/workspaces/*.idx.sqlite"]
    RAG -.->|optional| H["Embedding API<br>(Jina / OpenAI)"]
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ZOT_DATA_DIR` | Override Zotero data directory path |
| `ZOT_LIBRARY_ID` | Override Library ID (write operations) |
| `ZOT_API_KEY` | Override API Key (write operations) |
| `ZOT_PROFILE` | Override default config profile |
| `S2_API_KEY` | Semantic Scholar API key (for `update-status`) |
| `ZOT_EMBEDDING_URL` | Embedding API endpoint (default: Jina AI) |
| `ZOT_EMBEDDING_KEY` | Embedding API key (enables semantic workspace search) |
| `ZOT_EMBEDDING_MODEL` | Embedding model name (default: `jina-embeddings-v3`) |

## TODO

- [x] Improve HTML-to-Markdown: support lists, links, tables, and other common Zotero note formats (v0.1.2: uses markdownify)
- [x] `summarize-all` pagination: add offset/cursor pagination for large libraries (v0.1.2: `--offset` flag)
- [x] `--dry-run` for destructive ops: add preview mode to `delete`, `collection delete`, and `tag` (v0.1.2)

### Features

- [x] `zot cite`: copy formatted citation to clipboard (APA, Nature, Vancouver)
- [x] Bulk operations from file input (`zot add --from-file dois.txt`)
- [x] `zot export`: add RIS format support (BibTeX, CSL-JSON, RIS, JSON)

### Tier 1 — High Value, Moderate Effort

- [x] `zot update KEY --title/--date/--field`: update item metadata (pyzotero `update_item()`)
- [x] `zot search --type journalArticle`: filter search results by item type
- [x] `zot search --sort dateAdded --direction desc`: sort control for search/list
- [x] `zot recent --days 7`: recently added/modified items
- [x] `zot pdf KEY --annotations`: extract PDF annotations (highlights, comments, page numbers) — pymupdf

### Tier 2 — High Value, Higher Effort

- [x] `zot duplicates --by doi|title|both`: duplicate detection (fuzzy title + DOI matching)
- [x] `zot trash list/restore`: trash management (view + restore)
- [x] `zot attach KEY --file paper.pdf`: attachment upload
- [x] `--library group:<id>`: group library support (all commands + MCP tools)
- [x] `zot add --pdf paper.pdf`: add from local PDF (auto-extract DOI + upload attachment)

### Tier 3 — Medium Value

- [ ] Saved searches CRUD
- [ ] More export formats: BibLaTeX, MODS, TEI, CSV
- [ ] Formatted bibliography via citeproc-py with CSL styles
- [ ] `zot collection remove`: remove item from collection (counterpart to `collection move`)
- [ ] BetterBibTeX citation key lookup support

### Tier 4 — Nice to Have

- [x] Semantic search via workspace RAG (BM25 + optional embeddings, v0.2.0)
- [ ] DOI-to-key index
- [ ] Version tracking / incremental sync
- [ ] Web interface (`zot serve`)
- [ ] View tags by collection

### Polish

- [ ] GitHub Issues / Discussions setup for user feedback
- [x] Improve `--help` text with usage examples
- [x] Shell completion install instructions in README (zsh/bash/fish)

### Distribution

- [x] `pipx` install instructions
- [x] GitHub Releases with changelogs (v0.1.1, v0.1.2)
- [x] README badges: PyPI version, CI status, Python versions, License

### MCP Server

- [ ] Expand MCP tools: collection management, export, advanced search
- [ ] MCP server documentation / integration guide

---

## Support

<table>
  <tr>
    <td align="center">
      <img src="https://raw.githubusercontent.com/Agents365-ai/images_payment/main/qrcode/wechat-pay.png" width="180" alt="WeChat Pay">
      <br>
      <b>WeChat Pay</b>
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/Agents365-ai/images_payment/main/qrcode/alipay.png" width="180" alt="Alipay">
      <br>
      <b>Alipay</b>
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/Agents365-ai/images_payment/main/qrcode/buymeacoffee.png" width="180" alt="Buy Me a Coffee">
      <br>
      <b>Buy Me a Coffee</b>
    </td>
  </tr>
</table>

## License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — Free for non-commercial use.
