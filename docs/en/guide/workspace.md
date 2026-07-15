# Workspaces

## Why Workspaces?

Zotero collections are great for permanent library organization, but research often needs temporary, cross-cutting groupings — "all papers for my ICML submission", "papers to discuss at lab meeting", or "references for Chapter 3".

Workspaces fill this gap: lightweight, local-only views that don't modify your Zotero library. Each workspace is a TOML file at `~/.config/zot/workspaces/<name>.toml`. No API key needed, no syncing side effects.

## Create a Workspace

```bash
zot workspace new llm-safety --description "LLM alignment papers"
```

Names must be kebab-case (e.g., `llm-safety`, `protein-folding`).

## Add Items

```bash
zot workspace add llm-safety ABC123 DEF456 GHI789
```

## Bulk Import

```bash
zot workspace import llm-safety --collection "Alignment"
zot workspace import llm-safety --tag "safety"
zot workspace import llm-safety --search "RLHF"
```

## Browse

```bash
zot workspace list                          # All workspaces
zot workspace show llm-safety               # Items with metadata
zot workspace search "reward" --workspace llm-safety
```

## Export

```bash
zot workspace export llm-safety                       # Markdown
zot workspace export llm-safety --format json         # JSON
zot workspace export llm-safety --format bibtex       # BibTeX
```

## RAG Search

Build an index over workspace papers for natural language querying:

### Build Index

```bash
zot workspace index llm-safety
```

This indexes metadata + PDF full text using BM25.

### Query

```bash
zot workspace query "reward hacking methods" --workspace llm-safety
```

Returns ranked text chunks from indexed papers.

### Semantic Search (Optional)

For hybrid BM25 + vector retrieval, configure an embedding endpoint:

```bash
export ZOT_EMBEDDING_URL="https://api.jina.ai/v1/embeddings"
export ZOT_EMBEDDING_KEY="your-jina-key"   # 10M free tokens
zot workspace index llm-safety --force      # Rebuild with embeddings
zot workspace query "reward hacking" --workspace llm-safety --mode hybrid
```

Any OpenAI-compatible `/v1/embeddings` endpoint also works (Aliyun Bailian workspace URLs, LiteLLM, Ollama, vLLM, ...):

```bash
export ZOT_EMBEDDING_PROVIDER="openai"
export ZOT_EMBEDDING_URL="https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
export ZOT_EMBEDDING_KEY="your-key"
export ZOT_EMBEDDING_MODEL="text-embedding-v3"
```

## Manage

```bash
zot workspace remove llm-safety ABC123      # Remove item
zot workspace delete llm-safety --yes       # Delete workspace
```
