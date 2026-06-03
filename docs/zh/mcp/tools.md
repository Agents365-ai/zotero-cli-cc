# MCP 工具参考

共 45 个工具，按类别组织。所有工具均接受可选的 `library` 参数（默认：`"user"`）。群组文献库使用 `"group:<id>"`。

## 读取工具

| 工具 | 描述 | 关键参数 |
|------|------|----------|
| `search` | 按标题、作者、标签、全文搜索 | `query`, `collection?`, `item_type?`, `sort?`, `limit` |
| `list_items` | 列出所有条目 | `item_type?`, `sort?`, `limit` |
| `read` | 读取条目详情 + 笔记 | `key`, `detail?` |
| `pdf` | 提取 PDF 文本 | `key`, `pages?` |
| `annotations` | 提取 PDF 标注 | `key` |
| `summarize` | AI 结构化摘要 | `key` |
| `summarize_all` | 导出所有条目摘要 | `limit` |
| `export` | 导出引用 (bibtex/csl-json/ris) | `key`, `fmt?` |
| `cite` | 格式化引用 (apa/nature/vancouver) | `key`, `style?` |
| `relate` | 查找相关条目 | `key`, `limit?` |
| `recent` | 最近添加/修改的条目 | `days?`, `modified?`, `limit?` |
| `note_view` | 查看条目笔记 | `key` |
| `tag_view` | 查看条目标签 | `key` |
| `find_orphans` | 查找本地缺失文件的附件 | `dead_only?` |
| `collection_list` | 列出所有集合 | — |
| `collection_items` | 集合中的条目 | `collection_key` |
| `duplicates` | 查找重复 | `strategy?`, `threshold?`, `limit?` |
| `stats` | 文献库统计 | — |
| `update_status` | 检查预印本发表状态 | `key?`, `collection?`, `limit?`, `apply?` |

## 写入工具

| 工具 | 描述 | 关键参数 |
|------|------|----------|
| `add` | 通过 DOI 或 URL 添加条目 | `doi?`, `url?` |
| `add_from_pdf` | 从本地 PDF 添加 | `file_path`, `doi_override?` |
| `delete` | 删除条目（移入回收站） | `keys` |
| `update` | 更新元数据 | `key`, `title?`, `date?`, `fields?` |
| `attach` | 上传附件 | `parent_key`, `file_path`, `via_bridge?` |
| `note_add` | 添加笔记 | `key`, `content` |
| `note_update` | 更新笔记 | `note_key`, `content` |
| `tag_add` | 添加标签 | `keys`, `tags` |
| `tag_remove` | 删除标签 | `keys`, `tags` |
| `collection_create` | 创建集合 | `name`, `parent_key?` |
| `collection_move` | 移动条目到集合 | `item_key`, `collection_key` |
| `collection_delete` | 删除集合 | `collection_key` |
| `collection_rename` | 重命名集合 | `collection_key`, `new_name` |
| `collection_reorganize` | 批量重组 | `plan` |
| `trash_list` | 列出回收站条目 | `limit?` |
| `trash_restore` | 从回收站恢复 | `key` |

## 工作区工具

| 工具 | 描述 | 关键参数 |
|------|------|----------|
| `workspace_new` | 创建工作区 | `name`, `description?` |
| `workspace_delete` | 删除工作区 | `name` |
| `workspace_add` | 添加条目到工作区 | `name`, `keys` |
| `workspace_remove` | 移除条目 | `name`, `keys` |
| `workspace_list` | 列出所有工作区 | — |
| `workspace_show` | 显示工作区条目 | `name`, `limit?` |
| `workspace_export` | 导出工作区 | `name`, `fmt?` |
| `workspace_import` | 批量导入条目 | `name`, `collection?`, `tag?`, `search_query?` |
| `workspace_search` | 工作区内搜索 | `name`, `query`, `limit?` |
| `workspace_index` | 构建 RAG 索引 | `name`, `force?` |
| `workspace_query` | 自然语言查询 | `name`, `question`, `top_k?`, `mode?` |
