# Workspaces & RAG

Workspaces are local topic-based paper collections for organizing research. Each workspace stores item keys in a TOML file (`~/.config/zot/workspaces/<name>.toml`) — no Zotero API needed.

## Workspace Management

```bash
# Create
zot workspace new llm-safety --description "LLM alignment and safety papers"

# Add/remove items
zot workspace add llm-safety KEY1 KEY2 KEY3
zot workspace remove llm-safety KEY1

# List and inspect
zot workspace list
zot --json workspace list
zot workspace show llm-safety

# Delete
zot workspace delete llm-safety --yes
```

## Bulk Import

```bash
zot workspace import llm-safety --collection "Alignment"
zot workspace import llm-safety --tag "safety"
zot workspace import llm-safety --search "RLHF"
```

## Search Within Workspace

Metadata substring match (no index required):

```bash
zot workspace search "reward" --workspace llm-safety
zot --json workspace search "attention" --workspace llm-safety
```

## Export

```bash
zot workspace export llm-safety                       # Markdown (default)
zot workspace export llm-safety --format json         # JSON
zot workspace export llm-safety --format bibtex       # BibTeX
```

## RAG Index

```bash
zot workspace index llm-safety                          # Incremental index
zot workspace index llm-safety --force                  # Full rebuild (slow — confirm with user first)
zot workspace index llm-safety --skip-tag skip-index    # Skip PDFs carrying this tag (default: skip-index)
```

Attachments tagged `skip-index` are skipped by default. Use `--skip-tag` to
change which tag(s) are excluded — useful for keeping huge or irrelevant PDFs
out of the index. Tag a PDF `skip-index` in Zotero to exclude it.

**Important**: Never `--force` rebuild without user confirmation. Incremental indexing is usually sufficient.

## RAG Query

```bash
zot workspace query "reward hacking" --workspace llm-safety
zot workspace query "RLHF methods" --workspace llm-safety --top-k 10
zot --json workspace query "attention" --workspace llm-safety
```

### Retrieval Modes

```bash
--mode bm25       # Keyword only (always available, zero deps)
--mode semantic   # Embeddings only (requires ZOT_EMBEDDING_URL + ZOT_EMBEDDING_KEY)
--mode hybrid     # BM25 + semantic fusion (auto-selected if embeddings available)
```

## Chunk Format

RAG results return chunks structured as:

```json
{
  "rank": 1,
  "score": 0.0154,
  "item_key": "B6TZ6TQX",
  "source": "pdf",
  "content": "[Title > Section Heading] chunk text..."
}
```

## Reading More Context from Chunks

When a chunk is incomplete, drill into the source:

```bash
zot --json pdf --outline ITEMKEY            # Get numbered section headings
zot --json pdf --section N ITEMKEY          # Extract content under the N-th heading
```

## Configuration

- BM25: always available, zero additional dependencies
- Semantic search: set `ZOT_EMBEDDING_URL` and `ZOT_EMBEDDING_KEY` environment variables
