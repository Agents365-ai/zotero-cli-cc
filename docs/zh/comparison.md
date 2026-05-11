# 同类工具对比

| 特性 | **zotero-cli-cc** | [pyzotero-cli](https://github.com/chriscarrollsmith/pyzotero-cli) | [zotero-cli](https://github.com/jbaiter/zotero-cli) | [zotero-cli-tool](https://github.com/dhondta/zotero-cli) | [zotero-mcp](https://github.com/54yyyu/zotero-mcp) | [cookjohn/zotero-mcp](https://github.com/cookjohn/zotero-mcp) | [ZoteroBridge](https://github.com/Combjellyshen/ZoteroBridge) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **直读 SQLite** | **✅** | ❌ | ❌（仅缓存） | ❌ | ❌ | ❌（插件） | ✅ |
| **离线读** | **✅** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **无需 Zotero 运行** | **✅** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **零配置读** | **✅** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **安全写（Web API）** | **✅** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌（直写 SQLite） |
| **PDF 全文** | **✅** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **AI 编程助手** | **✅ Claude Code** | 部分 | ❌ | ❌ | Claude/ChatGPT | Claude/Cursor | Claude/Cursor |
| **终端 CLI** | **✅** | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **MCP 协议** | **✅** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **JSON 输出** | ✅ | ✅ | ❌ | ❌ | N/A | N/A | N/A |
| **笔记管理** | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ |
| **分类管理** | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **引用导出** | ✅ BibTeX/CSL-JSON/RIS | ✅ | ❌ | ✅ Excel | ❌ | ❌ | ❌ |
| **语义搜索** | **✅ 内置（workspace RAG）** | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **详细级别** | **✅** | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **多 Profile** | **✅** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **PDF 缓存** | **✅** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **库维护** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **语言** | Python | Python | Python | Python | Python | TypeScript | TypeScript |
| **活跃度** | ✅ 2026 | ✅ 2025 | ❌ 2024 | ✅ 2026 | ✅ 2026 | ✅ 2026 | ✅ 2026 |

## 为什么选 zotero-cli-cc？

> **当前唯一仍在维护、直接读取 Zotero 本地 SQLite 的 Python CLI。**

- **快** —— 毫秒级响应，无网络延迟
- **离线** —— 无需联网、无需 Zotero 桌面端
- **零配置** —— 装完即用，读操作不需要 API Key
- **AI 原生** —— 为 Claude Code 而生，自动输出 JSON envelope 供 AI 消费
- **安全** —— 读写分离：写操作走 Web API 以保护数据库完整性
- **终端原生** —— 唯一一个把本地 SQLite 读 + 安全 Web API 写组合在一起的终端 CLI；纯 MCP 工具必须配 AI 客户端才能用
