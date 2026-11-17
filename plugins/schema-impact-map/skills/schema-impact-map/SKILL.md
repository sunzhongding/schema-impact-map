---
name: schema-impact-map
description: Find what a relational schema change touches before editing migrations, models or SQL. Use when adding, renaming, retyping or dropping a column or table, when asked "what breaks if I change X", or when reviewing a schema/migration diff and you need the affected columns, foreign keys, joins and SQL statements as evidence.
license: Apache-2.0
metadata:
  author: sunzhongding
  version: 0.4.0
---

# Schema Impact Map

A relational schema is described in four places: `information_schema`, the DDL history,
the SQL embedded in services (mappers, reports, ETL), and people's heads. Before changing
a column, collect the evidence: which columns reference it, which joins fail, which SQL
statements mention it, and which new names collide with existing ones.

## When to use

- A migration, model or mapper change adds / removes / renames / retypes a column.
- Someone asks "what breaks if we change this column?" or "is it safe to drop this table?".
- A PR touches `*.sql`, migrations, ORM models or MyBatis XML and needs an impact review.
- Two teams disagree about whether a column is still in use.

## Setup

A **ledger folder** describes the schema as text:

```text
ledger/
├── schema-impact-map.yaml   # entry point: name, dialect, references below
├── schema.json              # databases -> tables -> columns, keys, declared relations
├── entities.yaml            # human decisions: canonical column, aliases, business keys
├── rules.yaml               # patterns that are NOT relationships
├── sql/                     # real SQL; joins are parsed into column-level edges
└── plans/                   # optional what-if YAML files
```

If the repository has no ledger, say so instead of inventing one. A SQLite file can become
one without a server: `schema-impact-map introspect --sqlite app.db --out ledger --write-config`
opens it read-only and writes `schema.json` plus a starter config. For other engines, offer to
generate `schema.json` from `information_schema` (read-only) or from DDL files.

## Commands

```bash
schema-impact-map check  --data <ledger>                       # validate the ledger
schema-impact-map impact --data <ledger> --plan <plan.yaml> --out site/impact.html
schema-impact-map map    --data <ledger> --out site/map.html   # full map
```

With the MCP server (`schema-impact-map mcp`) the same work is available as the tools
`check`, `impact`, `render` and `build_graph`.

## Plan format

```yaml
name: Review customer key          # label shown on the page
description: optional context
changes:
  analyze_columns:                 # what-if: does this change break anything?
    - crm.customers.id
  remove_columns:                  # treated as breaking
    - billing.invoices.legacy_code
  add_columns:                     # checked for naming collisions
    - table: shop.refunds
      column: status
      type: varchar(24)
  add_edges:                       # relationships the change introduces
    - src: shop.refunds.status
      dst: shop.orders.status
      kind: same_entity
      reason: same lifecycle
```

## Reading the result

- **red** — changed column, breaking impact, impacted relationship, affected table/database
- **orange** — new column, affected column
- **yellow** — naming/semantic collision with an existing column

Every edge carries `confidence` and `method`: `fk` 1.0, `sql_join` 0.9, `value_overlap`
0.9–0.95, human decision 1.0. Quote the evidence, not just the count.

## Rules

- **Read-only.** Never edit the ledger, the SQL or the plan to make an impact disappear;
  report the impact and let the human decide.
- **No database access.** The tool never connects to a database and never needs credentials.
- **Link, don't dump.** Give the user the summary (changed / affected / collisions / SQL)
  and the generated HTML path; paste only the few rows that matter.
- **Missing ledger is a finding.** If there is no ledger for the schema under change, say
  what would be needed to build one instead of guessing.
