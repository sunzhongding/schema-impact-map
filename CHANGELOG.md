# Changelog

## 0.5.0

- `plan --diff <range>` / `plan --sql <file>`: derive the plan YAML from a migration diff,
  understanding `ALTER TABLE ... ADD/DROP/RENAME COLUMN` and the Alembic `op.add_column` /
  `op.drop_column` / `op.alter_column` calls; unmodelled statements become warnings
- `context --for <tables> --budget <tokens>`: the schema slice an agent needs, in priority
  order, trimmed to the budget; exposed as the `context` MCP tool
- `rename_columns` in a plan, with the new name rendered on the map and in the report
- README, SKILL.md and the action docs cover the new commands

## 0.4.0

- `impact --format md|json`: a comment-sized report and a stable machine payload
- `impact --fail-on none|breaking|collision|affected`: exit 1 when the change reaches that
  severity, so the command can be a CI gate
- `impact --out` is optional: html still defaults to `site/impact.html`, md/json print to
  stdout
- `action.yml`: composite GitHub Action that renders the report, keeps one PR comment up to
  date, optionally uploads the HTML map, and fails the job when the gate trips

## 0.3.0

- SQLite introspection: `schema-impact-map introspect --sqlite app.db --out ledger`
  writes `schema.json` (and `--write-config` a starter ledger) from a file opened
  read-only — tables, columns, primary keys, unique columns and foreign keys
- `introspect_sqlite` MCP tool so an agent can turn a `.db` file into a ledger
- `dialect: sqlite` SQL parsing, and views/virtual tables/composite foreign keys are
  reported as warnings instead of being guessed
- integration docs unchanged; the plugin and marketplace versions move to 0.3.0

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
