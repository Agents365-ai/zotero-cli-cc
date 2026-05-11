# Roadmap

Historical TODO list extracted from the README. Completed items are kept for
context; open items are tracked here until they're promoted to GitHub Issues.

## Done

- [x] Improve HTML-to-Markdown: support lists, links, tables, and other common Zotero note formats (v0.1.2: uses markdownify)
- [x] `summarize-all` pagination: add offset/cursor pagination for large libraries (v0.1.2: `--offset` flag)
- [x] `--dry-run` for destructive ops: add preview mode to `delete`, `collection delete`, and `tag` (v0.1.2)
- [x] `zot cite`: copy formatted citation to clipboard (APA, Nature, Vancouver)
- [x] Bulk operations from file input (`zot add --from-file dois.txt`)
- [x] `zot export`: add RIS format support (BibTeX, CSL-JSON, RIS, JSON)
- [x] `zot update KEY --title/--date/--field`: update item metadata (pyzotero `update_item()`)
- [x] `zot search --type journalArticle`: filter search results by item type
- [x] `zot search --sort dateAdded --direction desc`: sort control for search/list
- [x] `zot recent --days 7`: recently added/modified items
- [x] `zot pdf KEY --annotations`: extract PDF annotations (highlights, comments, page numbers) — pymupdf
- [x] `zot duplicates --by doi|title|both`: duplicate detection (fuzzy title + DOI matching)
- [x] `zot trash list/restore`: trash management (view + restore)
- [x] `zot attach KEY --file paper.pdf`: attachment upload
- [x] `--library group:<id>`: group library support (all commands + MCP tools)
- [x] `zot add --pdf paper.pdf`: add from local PDF (auto-extract DOI + upload attachment)
- [x] Semantic search via workspace RAG (BM25 + optional embeddings, v0.2.0)
- [x] Improve `--help` text with usage examples
- [x] Shell completion install instructions in README (zsh/bash/fish)
- [x] `pipx` install instructions
- [x] GitHub Releases with changelogs
- [x] README badges: PyPI version, CI status, Python versions, License
- [x] Expand MCP tools: workspace, cite, stats, update-status (45 tools total)

## Open

### Features

- [ ] Saved searches CRUD
- [ ] More export formats: BibLaTeX, MODS, TEI, CSV
- [ ] Formatted bibliography via citeproc-py with CSL styles
- [ ] `zot collection remove`: remove item from collection (counterpart to `collection move`)
- [ ] BetterBibTeX citation key lookup support
- [ ] DOI-to-key index
- [ ] Version tracking / incremental sync
- [ ] Web interface (`zot serve`)
- [ ] View tags by collection

### Polish & Distribution

- [ ] GitHub Issues / Discussions setup for user feedback
- [ ] MCP server documentation / integration guide
