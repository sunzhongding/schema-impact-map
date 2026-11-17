# Review schema changes in a pull request

`impact --format md` produces a comment-sized report, `--format json` produces a stable
payload for scripts, and `--fail-on` turns either into a CI gate. The composite action in
this repository wires all three together.

## Workflow

```yaml
# .github/workflows/schema-impact.yml
name: schema impact

on:
  pull_request:

permissions:
  contents: read
  pull-requests: write   # needed to post the comment

jobs:
  impact:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: sunzhongding/schema-impact-map@v1
        with:
          data: ledger                              # folder with schema-impact-map.yaml
          plan: .schema-impact/plan.yaml            # the proposed change
          fail-on: breaking                         # none | breaking | collision | affected
          comment: "true"
          artifact: "true"
```

The action renders the report, writes it to the job summary, keeps **one** pull request
comment up to date (it edits its own comment instead of posting a new one on every push),
optionally uploads the markdown/JSON/HTML as an artifact, and finally fails the job when the
`fail-on` gate trips.

## Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `data` | yes | — | ledger folder |
| `plan` | yes | — | plan YAML path, or inline YAML |
| `fail-on` | no | `none` | fail at `breaking`, `collision` or `affected` |
| `comment` | no | `true` | post/update the PR comment |
| `artifact` | no | `false` | upload markdown + JSON + HTML |
| `python-version` | no | `3.12` | interpreter for the CLI |

## Outputs

| Output | Example |
|---|---|
| `summary` | `1 changed, 3 affected, 0 collisions, 2 SQL` |
| `failed` | `true` when the gate tripped |
| `markdown-path` | path of the comment body |
| `json-path` | path of the machine payload |
| `html-path` | path of the map (empty unless `artifact: true`) |

## Without the action

```bash
schema-impact-map impact --data ledger --plan plan.yaml --format md
schema-impact-map impact --data ledger --plan plan.yaml --format json --out impact.json
schema-impact-map impact --data ledger --plan plan.yaml --fail-on breaking
```

`--format md` and `--format json` print to stdout unless `--out` is given; `--format html`
keeps the old default of `site/impact.html`. The command exits `1` when the gate trips, so
it can be a plain step:

```yaml
- run: schema-impact-map impact --data ledger --plan plan.yaml --fail-on breaking
```

## Notes

- **Fork pull requests** get a read-only `GITHUB_TOKEN`, so the comment step cannot post;
  the action marks that step `continue-on-error` and the gate still works.
- Keep the ledger in the same repository as the SQL it analyses: the map is only as good as
  the `sql/` folder and the declared relations.
- The action installs the package from its own checkout (`$GITHUB_ACTION_PATH`), so pinning
  `@v1` pins the behaviour, including the Python dependencies.
