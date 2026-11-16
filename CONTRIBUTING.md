# Contributing

Thanks for helping. Schema Impact Map is intentionally small and evidence-first.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
schema-impact-map demo --out site
schema-impact-map check --data examples/shop
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
- `schema-impact-map check` must pass before opening a PR.

## Pull requests

1. Fork and create a branch.
2. Add tests and run `pytest`.
3. Update README or docs if behaviour changes.
4. Keep commits focused; describe the evidence model change.

## Releasing

The version lives in `src/schema_impact_map/__init__.py`; `pyproject.toml` reads it from
there and `tests/test_plugin.py` fails if the plugin manifests drift.

```bash
scripts/release.sh --check     # clean main, in sync, version + CHANGELOG notes present
scripts/release.sh --tag       # run tests, create and push v<version>
scripts/release.sh --release   # also open the GitHub release (gh CLI or GITHUB_TOKEN)
```

Publishing to PyPI happens only when the GitHub release is published: `publish.yml` uses
trusted publishing (OIDC), so no token is stored in the repository.
