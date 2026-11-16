# Security

Schema Impact Map is a local, static-analysis tool.

- Do not commit database credentials, real schema dumps, SQL from private repositories, or
  screenshots containing internal identifiers.
- The demo is synthetic. Real deployments should keep `schema.json` and generated HTML in a
  private repository.
- The generated HTML is self-contained and makes no network requests.
- Nothing is kept between runs: no change history, no snapshot, no audit database.
- If you add a database connector, make it read-only and document the required grants.

To report a vulnerability, open a private security advisory on GitHub rather than a public
issue.
