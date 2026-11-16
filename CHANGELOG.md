# Changelog

## 0.2.0

- `schema-impact-map mcp`: stdio MCP server with `check`, `impact`, `render` and `build_graph`
- plugin package in `plugins/schema-impact-map` (skill, `/impact` command, MCP server)
- `.claude-plugin/marketplace.json`, so Claude Code and ZCode can install it from this repo
- integration guides for Claude Code, Codex, ZCode and WorkBuddy
- PyPI publishing workflow using trusted publishing (OIDC, no stored token)

## 0.1.0

- distribution, CLI and Python package named `schema-impact-map` (`schema_impact_map`)
- schema JSON loader with databases, tables, columns and declared relations
- SQL file parser (sqlglot) with column-level join extraction
- entity map (canonical / alias / business key)
- graph builder with evidence + confidence
- `schema-impact-map check` gate for unresolved `*_id` columns
- interactive static map (pan, zoom, search, fit)
- plan delta impact: changed / affected / collisions / affected SQL
- synthetic four-database commerce demo
