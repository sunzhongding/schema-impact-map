# Use it from Codex

Codex reads `AGENTS.md`, `SKILL.md` skills and MCP servers from `~/.codex/`.

## 1. MCP server

Install the CLI once, then register the server in `~/.codex/config.toml`:

```bash
uv tool install "schema-impact-map[mcp]"     # or: pipx install "schema-impact-map[mcp]"
```

```toml
[mcp_servers.schema-impact-map]
command = "uvx"
args = ["--from", "schema-impact-map[mcp]", "schema-impact-map", "mcp"]
```

Start a Codex session and ask it to `check` or `impact` a ledger folder; the four tools are
`callable` as `schema-impact-map.check`, `schema-impact-map.impact`,
`schema-impact-map.render` and `schema-impact-map.build_graph` (namespacing depends on the
Codex version).

## 2. Skill

```bash
mkdir -p ~/.codex/skills
cp -R /path/to/schema-impact-map/plugins/schema-impact-map/skills/schema-impact-map \
      ~/.codex/skills/
```

For a single repository, copy it to `.codex/skills/` instead. The skill carries the plan
format and the "read-only, evidence first" rules.

## 3. AGENTS.md snippet

Add this to the repository that owns the schema (not to this project):

```markdown
## Schema changes

Before editing migrations, ORM models, mappers or SQL that mention a column:

1. run `schema-impact-map check --data <ledger>` and fix any error first;
2. write the change as a plan YAML and run
   `schema-impact-map impact --data <ledger> --plan <plan> --out site/impact.html`;
3. summarise changed / affected / collisions / SQL in the PR description and link the HTML.

Never edit the ledger or the SQL to make an impact disappear.
```

## Notes

- The MCP server is stdio-only, local and read-only; it needs no credentials.
- If `uvx` is unavailable, point `command` at the installed binary instead:
  `command = "schema-impact-map"`, `args = ["mcp"]`.
