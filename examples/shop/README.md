# Shop demo

Synthetic four-database commerce schema used by `schema-impact-map demo`.

```
crm      customers, customer_profiles
shop     orders, order_items, refunds, order_agents
billing  invoices
ops      agents
```

- No real company data.
- `schema.json` declares cross-database relations.
- `sql/*.sql` contains joins that are parsed by sqlglot.
- `entities.yaml` records the human decision that one customer has several physical columns.
- `plans/*.yaml` are what-if changes used by `schema-impact-map impact`.

Try:

```bash
schema-impact-map check --data examples/shop
schema-impact-map demo --out site
schema-impact-map impact --data examples/shop \
    --plan examples/shop/plans/customer-key.yaml --out site/impact.html
```
