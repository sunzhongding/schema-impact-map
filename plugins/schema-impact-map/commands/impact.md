---
description: Analyse the impact of a schema change and write an impact map
argument-hint: "[plan.yaml | changing column, e.g. crm.customers.id]"
---

Analyse the schema impact of: $ARGUMENTS

1. Find the ledger folder (`schema-impact-map.yaml`). If there is none, say so and stop.
2. If `$ARGUMENTS` names a plan file, use it. Otherwise write a temporary plan:

   ```yaml
   name: <one line summary>
   changes:
     analyze_columns:        # or remove_columns / add_columns / add_edges
       - <qualified column>
   ```

3. Run:

   ```bash
   schema-impact-map impact --data <ledger> --plan <plan> --out site/impact.html
   ```

4. Reply with the summary (changed / affected / collisions / SQL), the affected columns
   with their confidence, and the path to `site/impact.html`. Do not edit the schema,
   the SQL or the ledger as part of this command.
