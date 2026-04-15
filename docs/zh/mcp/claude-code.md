# 搭配 Claude Code 使用

!!! tip "Agent-native 接口（0.3.0+）"
    当 stdout 不是 TTY 时，`zot` 自动输出 JSON envelope，Claude Code 无需加
    `--json` 就能拿到可解析的结构化输出。退出码已按类别细分（校验、鉴权、
    未找到、网络、冲突），每个 envelope 携带 `meta.request_id`，所有写命令
    支持 `--dry-run` 和 `--idempotency-key`。完整契约见：[Agent Interface](../reference/agent-interface.md)。

## 安装 Skill

复制 zotero-cli-cc skill，让 Claude Code 自动识别文献相关请求：

```bash
cp -r skill/zotero-cli-cc ~/.claude/skills/
```

## 工作原理

安装 skill 后，Claude Code 会在你提到论文时自动使用 `zot` 命令：

```
搜索我的 Zotero 中关于单细胞的论文
→ Claude 运行: zot --json search "single cell"

查看这篇论文的详情
→ Claude 运行: zot --json read ABC123

导出这些论文的 BibTeX
→ Claude 运行: zot export ABC123

为我的 ICML 投稿创建一个工作区
→ Claude 运行: zot workspace new icml-2026 --description "ICML 2026 submission"
```

## 工作区 + RAG 工作流

Claude Code 的典型科研工作流：

1. **创建工作区** — 为你的项目建立文献集
2. **导入论文** — 从集合、标签或搜索结果导入
3. **构建 RAG 索引** — 支持语义搜索
4. **查询** — 用自然语言提问

```
创建一个叫 "llm-safety" 的工作区，导入所有标签为 "alignment" 的论文
→ Claude 创建工作区并导入条目

索引这个工作区
→ Claude 运行: zot workspace index llm-safety

这些论文使用了哪些方法来检测 reward hacking？
→ Claude 查询工作区 RAG 索引并综合回答
```

## Shell 自动补全

启用 tab 自动补全以加速 CLI 使用：

=== "Zsh"

    ```bash
    zot completions zsh >> ~/.zshrc
    ```

=== "Bash"

    ```bash
    zot completions bash >> ~/.bashrc
    ```

=== "Fish"

    ```bash
    zot completions fish > ~/.config/fish/completions/zot.fish
    ```
