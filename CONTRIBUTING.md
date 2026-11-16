# Contributing

Thanks for helping. DataAsset is intentionally small and evidence-first.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
dataasset demo --out site
dataasset check --data examples/shop
```

## Good first issues

- add a MySQL connector (read-only `information_schema`)
- add a PostgreSQL fixture and test
- add a MyBatis XML extractor
- improve the map layout for wide tables
- add a GitHub Action that comments an impact map on a PR

## Rules

- Keep the demo data synthetic. Never commit real customer or company data.
- Every new relation must carry `confidence`, `method` and evidence.
- Add a test when changing graph orientation or impact semantics.
- `dataasset check` must pass before opening a PR.

## Pull requests

1. Fork and create a branch.
2. Add tests and run `pytest`.
3. Update README or docs if behaviour changes.
4. Keep commits focused; describe the evidence model change.
