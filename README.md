# zotero-cli-cc

[English](#english) | [中文](#中文)

---

<a id="中文"></a>

## 简介

`zotero-cli-cc` 是一个专为 [Claude Code](https://claude.ai/code) 设计的 Zotero 命令行工具。

**核心特性：**
- **读操作**：直接读取本地 SQLite 数据库，零配置、离线可用、毫秒级响应
- **写操作**：通过 Zotero Web API 安全写入，Zotero 完全感知变更
- **PDF 提取**：直接从本地存储提取 PDF 全文

**无需启动 Zotero 桌面端即可检索和阅读文献。**

## 安装

```bash
# 推荐
uv tool install zotero-cli-cc

# 或者
pip install zotero-cli-cc
```

## 配置

```bash
# 配置 Web API 凭证（仅写操作需要）
zot config init
```

读操作开箱即用，只要 Zotero 数据在默认目录（`~/Zotero`）。

写操作需要 API Key，在 https://www.zotero.org/settings/keys 获取。

## 13 个命令一览

### 检索与浏览

```bash
# 全库搜索（标题、作者、标签、全文）
zot search "transformer attention"

# 按 collection 过滤搜索
zot search "BERT" --collection "NLP"

# 列出文献
zot list --collection "Machine Learning" --limit 10

# 查看文献详情（元数据 + 摘要 + 笔记）
zot read ABC123

# 查找相关文献
zot relate ABC123
```

### 笔记与标签

```bash
# 查看笔记
zot note ABC123

# 添加笔记（通过 Web API）
zot note ABC123 --add "这篇论文提出了新的注意力机制"

# 查看标签
zot tag ABC123

# 添加/删除标签
zot tag ABC123 --add "重要"
zot tag ABC123 --remove "待读"
```

### 引用导出

```bash
# 导出 BibTeX
zot export ABC123

# 导出 JSON
zot export ABC123 --format json
```

### 文献管理

```bash
# 通过 DOI 添加文献
zot add --doi "10.1038/s41586-023-06139-9"

# 通过 URL 添加
zot add --url "https://arxiv.org/abs/2301.00001"

# 删除文献（移入回收站）
zot delete ABC123 --yes
```

### Collection 管理

```bash
# 列出所有 collection（树形展示）
zot collection list

# 查看 collection 内的文献
zot collection items COLML01

# 创建新 collection
zot collection create "新项目"
```

### AI 辅助功能

```bash
# 结构化摘要（专为 Claude Code 优化的输出格式）
zot summarize ABC123

# 提取 PDF 全文
zot pdf ABC123

# 提取指定页
zot pdf ABC123 --pages 1-5
```

### 全局选项

```bash
# JSON 输出（方便 Claude Code 解析）
zot --json search "attention"

# 限制结果数量
zot --limit 5 list

# 查看版本
zot --version
```

## 架构

```
┌─────────────────────────────────┐
│        zot CLI (Click)          │
│  search │ list │ read │ ...     │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│        核心服务层                │
│  ZoteroReader  │  ZoteroWriter  │
│  (SQLite 只读) │  (Web API)     │
└───────┬────────┴────────┬───────┘
        │                 │
   ┌────▼────┐    ┌───────▼────────┐
   │ SQLite  │    │ Zotero Web API │
   │ (本地)   │    │ (远程)         │
   └─────────┘    └────────────────┘
        │
   ┌────▼──────────┐
   │ ~/Zotero/     │
   │ storage/*.pdf │
   └───────────────┘
```

**读写分离设计**：
- 读操作直接访问 `~/Zotero/zotero.sqlite`（只读模式，即使 Zotero 运行中也能安全读取）
- 写操作通过 Zotero Web API（变更由 Zotero 服务器验证和同步）
- PDF 直接从 `~/Zotero/storage/` 目录提取文本

## 在 Claude Code 中使用

在任何 Claude Code 会话中，直接用自然语言请求：

```
帮我搜索 Zotero 中关于 single cell 的论文
→ Claude 自动运行: zot --json search "single cell"

查看这篇论文的详情
→ Claude 自动运行: zot --json read ABC123

导出这篇论文的 BibTeX
→ Claude 自动运行: zot export ABC123
```

建议在 `~/.claude/CLAUDE.md` 中添加：

```markdown
### Zotero CLI
- 使用 `zot` 命令操作 Zotero（搜索、阅读、笔记、导出、添加、删除）
- 处理结果时使用 `--json` 标志
```

## 环境变量

| 变量 | 用途 |
|------|------|
| `ZOT_DATA_DIR` | 覆盖 Zotero 数据目录路径 |
| `ZOT_LIBRARY_ID` | 覆盖 Library ID（写操作） |
| `ZOT_API_KEY` | 覆盖 API Key（写操作） |

## 许可证

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — 免费用于非商业用途。

---

<a id="english"></a>

## English

`zotero-cli-cc` is a Zotero CLI tool designed for [Claude Code](https://claude.ai/code).

- **Reads**: Direct SQLite access to `~/Zotero/zotero.sqlite` (read-only, offline, fast)
- **Writes**: Zotero Web API via pyzotero (safe, Zotero-aware)
- **PDF**: Direct extraction from `~/Zotero/storage/` via pymupdf

### Install

```bash
uv tool install zotero-cli-cc
# or
pip install zotero-cli-cc
```

### Setup

```bash
zot config init  # Configure API key (write operations only)
```

### Commands

| Command | Purpose |
|---------|---------|
| `zot search <query>` | Search library (title, author, tag, fulltext) |
| `zot list` | List items with filters |
| `zot read <key>` | View item details + notes |
| `zot note <key>` | View/add notes |
| `zot export <key>` | Export citation (BibTeX/JSON) |
| `zot add` | Add item by DOI or URL |
| `zot delete <key>` | Delete item (move to trash) |
| `zot tag <key>` | View/manage tags |
| `zot collection` | Manage collections |
| `zot summarize <key>` | Structured summary for AI consumption |
| `zot pdf <key>` | Extract PDF text |
| `zot relate <key>` | Find related items |
| `zot config` | Configuration management |

### Global Flags

- `--json` — JSON output
- `--limit N` — Limit results
- `--version` — Show version

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `ZOT_DATA_DIR` | Override Zotero data directory |
| `ZOT_LIBRARY_ID` | Override library ID (writes) |
| `ZOT_API_KEY` | Override API key (writes) |

### License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — Free for non-commercial use.
