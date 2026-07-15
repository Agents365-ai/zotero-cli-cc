# 配置

## 数据目录

!!! info "什么是数据目录？"
    **数据目录**是包含 `zotero.sqlite` 数据库文件的文件夹 — 不是 Zotero 的安装目录或 PDF 同步目录。可以在 **Zotero 设置 → 高级 → 数据存储位置** 中找到。

读取操作开箱即用。`zot` 会自动检测 Zotero 数据目录：

| 平台 | 检测顺序 |
|------|----------|
| **Windows** | 注册表 `HKCU\Software\Zotero\Zotero\dataDir` → `%APPDATA%\Zotero` → `%LOCALAPPDATA%\Zotero` |
| **macOS / Linux** | `~/Zotero` |

如果数据不在默认位置：

=== "配置文件（推荐）"

    ```bash
    zot config init --data-dir "D:\MyZotero"
    ```

=== "环境变量"

    ```bash
    export ZOT_DATA_DIR="/path/to/zotero/data"
    ```

=== "手动编辑配置"

    编辑 `~/.config/zot/config.toml`：

    ```toml
    [zotero]
    data_dir = "D:\\MyZotero"
    ```

## API 凭据

写入操作（添加、删除、更新、标签、笔记、集合管理）需要 Zotero API 密钥。

1. 访问 [https://www.zotero.org/settings/keys](https://www.zotero.org/settings/keys)
2. 创建具有库读写权限的新密钥
3. 运行配置向导：

```bash
zot config init
```

Library ID 和 API Key 会保存到 `~/.config/zot/config.toml`。

## 配置文件

完整示例：

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

## 环境变量

| 变量 | 用途 |
|------|------|
| `ZOT_DATA_DIR` | 覆盖 Zotero 数据目录路径 |
| `ZOT_LIBRARY_ID` | 覆盖 Library ID（写入操作） |
| `ZOT_API_KEY` | 覆盖 API Key（写入操作） |
| `ZOT_PROFILE` | 覆盖默认配置文件 |
| `S2_API_KEY` | Semantic Scholar API 密钥（用于 `update-status`） |
| `ZOT_EMBEDDING_URL` | Embedding API 端点（默认：Jina AI） |
| `ZOT_EMBEDDING_KEY` | Embedding API 密钥（启用语义工作区搜索） |
| `ZOT_EMBEDDING_MODEL` | Embedding 模型名称（默认：`jina-embeddings-v3`） |
| `ZOT_EMBEDDING_PROVIDER` | Embedding 提供商：`jina`（默认）、`aliyun` 或 `openai`（任意 OpenAI 兼容 `/v1/embeddings` 端点，将 `ZOT_EMBEDDING_URL` 设为其 base URL） |

## 多配置文件

```bash
zot config profile list        # 列出所有配置文件
zot config profile set lab     # 设置默认配置文件
zot --profile lab search "X"   # 使用指定配置文件
```
