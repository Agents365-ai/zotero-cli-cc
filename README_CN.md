# zot — 让 Zotero 在终端飞起来

<p align="center">
  <img src="asserts/banner_official.png" alt="zotero-cli-cc banner" width="720">
</p>

<p align="center">
  <a href="https://pypi.org/project/zotero-cli-cc/"><img src="https://img.shields.io/pypi/v/zotero-cli-cc?color=blue" alt="PyPI version"></a>
  <a href="https://github.com/Agents365-ai/zotero-cli-cc/actions/workflows/ci.yml"><img src="https://github.com/Agents365-ai/zotero-cli-cc/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/zotero-cli-cc/"><img src="https://img.shields.io/pypi/pyversions/zotero-cli-cc" alt="Python versions"></a>
  <a href="https://creativecommons.org/licenses/by-nc/4.0/"><img src="https://img.shields.io/badge/license-CC%20BY--NC%204.0-lightgrey" alt="License"></a>
  <a href="https://agents365-ai.github.io/zotero-cli-cc/zh/"><img src="https://img.shields.io/badge/文档-GitHub%20Pages-blue" alt="文档"></a>
</p>

[English](README.md) | [文档](https://agents365-ai.github.io/zotero-cli-cc/zh/)

`zotero-cli-cc` 是一个专为 [Claude Code](https://claude.ai/code) 和 AI Agent 设计的 Zotero 命令行工具。

- **读操作** — 直接读取本地 SQLite，零配置、离线可用、毫秒级响应
- **写操作** — 通过 Zotero Web API 安全写入，Zotero 完全感知变更
- **PDF + RAG** — 提取 PDF 全文并自动缓存；内置 BM25（可选向量）按主题工作空间检索
- **Agent-native** — 稳定 JSON envelope、类型化退出码、`zot schema`、`--dry-run`、`--idempotency-key`、NDJSON 流
- **MCP 服务器** — 通过 `zot mcp serve` 向 Claude Desktop / LM Studio / Cursor 暴露 45 个工具

## 安装

```bash
uv tool install zotero-cli-cc      # 推荐
pipx install zotero-cli-cc         # 或者
pip install zotero-cli-cc          # 或者
```

## 60 秒上手

```bash
# 读操作开箱即用 —— 无需 API Key，自动检测 Zotero 数据目录
zot search "transformer attention"
zot read ABC123
zot export ABC123                  # BibTeX

# 写操作需要 Web API Key（https://www.zotero.org/settings/keys）
zot config init
zot add --doi "10.1038/s41586-023-06139-9"
```

在 Claude Code 中直接用自然语言提问——配套 skill 会自动把请求映射到 `zot` 命令：

```bash
cp -r skill/zotero-cli-cc ~/.claude/skills/
```

当 stdout 不是终端时，`zot` 自动输出稳定的 JSON envelope，Agent 调用无需加 `--json`：

```json
{ "ok": true, "data": { ... }, "meta": { "request_id": "...", "cli_version": "0.4.3" } }
```

## 文档

完整文档：**https://agents365-ai.github.io/zotero-cli-cc/zh/**

| 主题 | 链接 |
|---|---|
| 安装与配置 | [快速开始](https://agents365-ai.github.io/zotero-cli-cc/zh/getting-started/installation/) |
| 搜索、列表、阅读 | [搜索指南](https://agents365-ai.github.io/zotero-cli-cc/zh/guide/search/) |
| 笔记、标签、引用 | [笔记与标签](https://agents365-ai.github.io/zotero-cli-cc/zh/guide/notes-tags/)、[引用导出](https://agents365-ai.github.io/zotero-cli-cc/zh/guide/citations/) |
| 增 / 改 / 删条目 | [条目管理](https://agents365-ai.github.io/zotero-cli-cc/zh/guide/item-management/) |
| 分类（Collection） | [Collections](https://agents365-ai.github.io/zotero-cli-cc/zh/guide/collections/) |
| 工作空间 + RAG | [Workspace](https://agents365-ai.github.io/zotero-cli-cc/zh/guide/workspace/) |
| PDF 提取 | [PDF](https://agents365-ai.github.io/zotero-cli-cc/zh/guide/pdf/) |
| 预印本 → 已发表 | [update-status](https://agents365-ai.github.io/zotero-cli-cc/zh/guide/update-status/) |
| MCP 配置与工具 | [MCP](https://agents365-ai.github.io/zotero-cli-cc/zh/mcp/setup/) |
| 完整 CLI 参考 | [CLI Reference](https://agents365-ai.github.io/zotero-cli-cc/zh/reference/cli/) |
| Agent 契约（envelope、退出码、schema） | [`docs/agent-interface.md`](docs/agent-interface.md) |

## 同类工具对比

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
| **语义搜索** | **✅ 内置（workspace RAG）** | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **活跃度** | ✅ 2026 | ✅ 2025 | ❌ 2024 | ✅ 2026 | ✅ 2026 | ✅ 2026 | ✅ 2026 |

**为什么选 zotero-cli-cc？** 当前唯一仍在维护、直接读取 Zotero 本地 SQLite 的 Python CLI；读写分离架构 —— SQLite 提供快速离线读，Web API 提供让 Zotero 感知的安全写。

## 架构

<p align="center">
  <img src="asserts/architecture.png" alt="Architecture diagram" width="720">
</p>

## 作者

**Agents365-ai** — [GitHub](https://github.com/Agents365-ai) · [Bilibili](https://space.bilibili.com/441831884)

## 赞助

<table>
  <tr>
    <td align="center">
      <img src="https://raw.githubusercontent.com/Agents365-ai/images_payment/main/qrcode/wechat-pay.png" width="180" alt="微信支付">
      <br>
      <b>微信支付</b>
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/Agents365-ai/images_payment/main/qrcode/alipay.png" width="180" alt="支付宝">
      <br>
      <b>支付宝</b>
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/Agents365-ai/images_payment/main/qrcode/buymeacoffee.png" width="180" alt="Buy Me a Coffee">
      <br>
      <b>Buy Me a Coffee</b>
    </td>
  </tr>
</table>

## 许可证

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — 非商业使用免费。
