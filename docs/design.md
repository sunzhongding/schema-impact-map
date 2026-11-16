# Design notes

## The problem

A relational schema is usually described in at least four places:

1. the database's `information_schema`
2. the migration/DDL history
3. SQL embedded in services, mappers and ETL jobs
4. the heads of the people who know how the business is wired

When an AI agent proposes a schema change, it sees only the first three — and often only a
small part of the second and third. The review gap is not "can we draw an ERD"; it is
"what does this change touch, and what evidence do we have for each edge".

## Three layers

```
ledger (source)         schema.json + entities.yaml + rules.yaml + sql/
      │
      ▼
graph (derived)         nodes + edges + evidence
      │
      ├── map           interactive HTML
      └── impact        delta → changed / affected / collisions → highlighted HTML
```

The ledger is the only thing a human edits. The graph and the HTML can always be rebuilt.

## Node and edge model

Nodes:

- `database:shop`
- `table:shop.orders`
- `column:shop.orders.status`
- `entity:customer`

Edges:

| kind | direction | source |
|---|---|---|
| `fk` | child column → parent key | declared FK |
| `join` | child column → parent key | parsed SQL |
| `value_overlap` | child column → parent key | value probing |
| `same_entity` | column → entity | human decision |
| `represents` | entity → column | human decision |

Every relationship edge has `confidence`, `method` and `evidence` (file/snippet or probe
statistics). The UI never hides the method: a dashed edge means a code join, a solid edge
means a stronger/declared relationship.

## Confidence

| confidence | meaning |
|---|---|
| 1.0 | DDL FK, or two independent evidences, or human decision |
| 0.9–0.95 | strong value overlap / code join |
| 0.5–0.85 | single evidence, needs review |
| < 0.5 | do not publish into the main map |

The demo keeps this distinction even though its data is synthetic: `fk` edges are 1.0,
`sql_join` edges are 0.9, and merging them upgrades the edge to 1.0.

## Impact algorithm (v0.1)

For each changed column:

1. find every `fk` / `join` / `value_overlap` edge incident to it
2. mark the other endpoint as affected
3. find every SQL statement that references the changed column
4. for added columns, tokenize the name and find same-table / same-database collisions
5. mark changed/affected tables and databases
6. render the map with changed/affected/collision classes and red edges

This is deliberately evidence-based, not LLM-based. The LLM's job is to propose the delta;
the graph's job is to show what the delta touches.

## Multi-database future

The v0.1 demo uses `database.table.column` as the qualified name. The model is intended to
grow to:

```
instance / database / schema / table / column
```

Three cases must stay separate:

| case | direct SQL join? | method |
|---|---|---|
| same instance, different database/schema | yes (MySQL, SQL Server) | cross-schema SQL + value overlap |
| different instances, same engine | no | sample values to local DuckDB/Arrow; hash/Bloom compare |
| different engines | no | sample + type normalization + dialect-aware SQL parsing |

Cross-instance edges should require two independent evidences (for example code join +
value overlap) and a human confirmation. A single naming match is never enough.

## Non-goals

- Full data replication
- Automatic joins without evidence
- Frontend component scanning
- A hosted control plane in v0.1

The point is a small, auditable artifact that can sit next to the code and be reviewed in a
PR — not another service to operate.
