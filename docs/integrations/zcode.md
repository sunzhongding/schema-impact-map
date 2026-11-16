# Use it from ZCode

ZCode reads Claude Code plugin manifests, so this repository works as its own plugin
marketplace without any repackaging. ZCode ships with Anthropic's marketplace preset; adding
this repository is one dialog.

## 1. Plugin market (skills + `/impact` + MCP)

设置 → 插件 → 右上「创建」→「添加插件市场」→ 填 GitHub 仓库：

```text
sunzhongding/schema-impact-map
```

ZCode validates [`marketplace.json`](../../.claude-plugin/marketplace.json) and lists
`schema-impact-map` under the **个人** section. Install it; the skill, the `/impact`
command and the MCP tools are enabled together.

> The plugin manifest is `.claude-plugin/plugin.json` (the Claude Code compatible location).
> ZCode also accepts `.zcode-plugin/plugin.json`; that file is not needed here.

## 2. MCP server only

设置 → MCP 服务器 → 新建：

| Field | Value |
|---|---|
| Name | `schema-impact-map` |
| Type | `stdio` |
| Command | `uvx` |
| Args | `--from schema-impact-map[mcp] schema-impact-map mcp` |

The server appears as a regular MCP server and stays enabled across workspaces when the
scope is set to 用户.

## 3. Local plugin folder (offline)

```bash
git clone https://github.com/sunzhongding/schema-impact-map
# 设置 → 插件 → 创建 → 添加插件市场 → 选择目录 → 选中刚 clone 的仓库
```

Useful when the GitHub marketplace cannot be reached.

## Try it

```text
/crm.customers.id 这个字段如果改类型，会影响哪些查询？
```

or plain language: "改 `shop.orders.status` 之前先跑一下影响分析".

## Notes

- Prerequisite: `uv`/`uvx` on `PATH`, or install with
  `pipx install "schema-impact-map[mcp]"` and use the `schema-impact-map` binary instead.
- The MCP server is stdio, read-only and needs no credentials or network access.
