# 工作区

## 为什么需要工作区？

Zotero 集合适合永久的文献组织，但科研工作经常需要临时的、跨类别的分组 -- "ICML 投稿的所有论文"、"组会要讨论的论文"或"第三章的参考文献"。

工作区填补了这一空白：轻量级的本地视图，不会修改你的 Zotero 文献库。每个工作区是一个 TOML 文件，位于 `~/.config/zot/workspaces/<name>.toml`。无需 API 密钥，没有同步副作用。

## 创建工作区

```bash
zot workspace new llm-safety --description "LLM alignment papers"
```

名称必须使用 kebab-case（如 `llm-safety`、`protein-folding`）。

## 添加条目

```bash
zot workspace add llm-safety ABC123 DEF456 GHI789
```

## 批量导入

```bash
zot workspace import llm-safety --collection "Alignment"
zot workspace import llm-safety --tag "safety"
zot workspace import llm-safety --search "RLHF"
```

## 浏览

```bash
zot workspace list                          # 所有工作区
zot workspace show llm-safety               # 查看条目及元数据
zot workspace search "reward" --workspace llm-safety
```

## 导出

```bash
zot workspace export llm-safety                       # Markdown
zot workspace export llm-safety --format json         # JSON
zot workspace export llm-safety --format bibtex       # BibTeX
```

## RAG 检索

为工作区论文构建索引，支持自然语言查询：

### 构建索引

```bash
zot workspace index llm-safety
```

索引元数据 + PDF 全文，使用 BM25 算法。

### 查询

```bash
zot workspace query "reward hacking methods" --workspace llm-safety
```

返回索引论文中的排序文本片段。

### 语义搜索（可选）

配置 Embedding 端点以启用混合 BM25 + 向量检索：

```bash
export ZOT_EMBEDDING_URL="https://api.jina.ai/v1/embeddings"
export ZOT_EMBEDDING_KEY="your-jina-key"   # 1000 万免费 token
zot workspace index llm-safety --force      # 重建索引（含 embeddings）
zot workspace query "reward hacking" --workspace llm-safety --mode hybrid
```

也支持任意 OpenAI 兼容的 `/v1/embeddings` 端点（阿里云百炼工作空间专属地址、LiteLLM、Ollama、vLLM 等）：

```bash
export ZOT_EMBEDDING_PROVIDER="openai"
export ZOT_EMBEDDING_URL="https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
export ZOT_EMBEDDING_KEY="your-key"
export ZOT_EMBEDDING_MODEL="text-embedding-v3"
```

## 管理

```bash
zot workspace remove llm-safety ABC123      # 移除条目
zot workspace delete llm-safety --yes       # 删除工作区
```
