# Use it from WorkBuddy

WorkBuddy does not read Claude Code plugin manifests; it consumes **MCP servers** and
**skills** separately. Two small steps, both local.

## 1. MCP server

Install once:

```bash
uv tool install "schema-impact-map[mcp]"     # or: pipx install "schema-impact-map[mcp]"
```

User level — `~/.workbuddy/mcp.json` (available in every project):

```json
{
  "mcpServers": {
    "schema-impact-map": {
      "command": "uvx",
      "args": ["--from", "schema-impact-map[mcp]", "schema-impact-map", "mcp"]
    }
  }
}
```

Project level — `<project>/.workbuddy/mcp.json`, same content.

Or use the UI: 侧边栏 **插件** → **MCP 服务器** → **配置 MCP**，粘贴上面的 JSON。状态变绿即可用。

## 2. Skill

打包技能目录（`plugins/schema-impact-map/skills/schema-impact-map`）为 zip，然后在
**专家·技能·连接器 → 技能 → 添加技能 → 上传技能** 导入。

Or copy it straight into the user skills directory:

```bash
mkdir -p ~/.workbuddy/skills
cp -R plugins/schema-impact-map/skills/schema-impact-map ~/.workbuddy/skills/
```

The skill teaches WorkBuddy when to call the tools, how to write a plan YAML and how to
report evidence instead of guessing.

## Try it

> 帮我看看 `shop.orders.status` 改成枚举值会影响哪些报表和 join

WorkBuddy calls `check` then `impact`, and can write `site/impact.html` for review.

## Notes

- WorkBuddy 的 MCP 市场入口是腾讯云 MCP 市场；本仓库是本地 stdio 服务，不需要上架即可使用。
- 服务只读本地文件，不访问数据库、不联网、不需要任何密钥。
- 若企业环境禁用外网，可先 `pip install "schema-impact-map[mcp]"`，把 `command` 改成
  `schema-impact-map`、`args` 改成 `["mcp"]`。
