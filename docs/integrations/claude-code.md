# Use it from Claude Code

Three ways in, from most integrated to smallest footprint. All of them need the CLI on
`PATH` once:

```bash
uv tool install "schema-impact-map[mcp]"     # or: pipx install "schema-impact-map[mcp]"
```

## 1. Plugin (skills + `/impact` + MCP)

```text
/plugin marketplace add sunzhongding/schema-impact-map
/plugin install schema-impact-map@schema-impact-map
```

The marketplace manifest lives in [`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json)
and the plugin in [`plugins/schema-impact-map`](../../plugins/schema-impact-map). Installing it
registers the skill, the `/impact` command and the MCP tools in one step.

## 2. Project skill only

```bash
mkdir -p .claude/skills
cp -R /path/to/schema-impact-map/plugins/schema-impact-map/skills/schema-impact-map .claude/skills/
```

Claude picks it up for the current repository. The skill tells it when to call the CLI and
how to read a plan file.

## 3. MCP server only

```bash
claude mcp add schema-impact-map -- uvx --from "schema-impact-map[mcp]" schema-impact-map mcp
claude mcp list
```

This exposes `check`, `impact`, `render` and `build_graph` as tools without loading the
skill text.

## Try it

In a repository that has a ledger folder (`schema-impact-map.yaml`, `schema.json`,
`entities.yaml`, `rules.yaml`, `sql/`):

```text
What breaks if we change crm.customers.id?
```

Claude runs `impact`, reports the changed/affected columns and the SQL statements, and can
write `site/impact.html` for review.

## Notes

- The MCP server is stdio only, reads local files, and never connects to a database.
- `uvx --from "schema-impact-map[mcp]"` installs the optional MCP extra in a throwaway
  environment; add `--python 3.12` if your default Python is older than 3.10.
- If `/plugin` cannot reach GitHub, clone this repository and use route 2 or 3.
