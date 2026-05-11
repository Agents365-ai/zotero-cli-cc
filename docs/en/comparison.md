# Comparison with Similar Tools

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

## Why zotero-cli-cc?

> **The only actively maintained Python CLI that reads Zotero's local SQLite database directly.**

- **Fast** — millisecond response, no network latency
- **Offline** — no internet, no Zotero desktop needed
- **Zero-config** — install and go, no API key for reads
- **AI-native** — built for Claude Code, automatic JSON envelope for AI consumption
- **Safe** — read/write separation: writes go through the Web API to protect DB integrity
- **Terminal-native** — the only CLI combining local SQLite reads with safe Web API writes; MCP-only tools require an AI client and aren't usable from a terminal
