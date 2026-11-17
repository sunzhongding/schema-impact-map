"""Render an impact result for machines and for pull request comments.

The HTML map is for humans who open it; this module produces the two other
views a review workflow needs:

* ``to_markdown`` — a compact comment (a table plus a short summary) that fits
  in a pull request without hiding the evidence,
* ``to_json`` — a stable payload for scripts, CI gates and agents.

Nothing here reads files; it only reshapes what :func:`schema_impact_map.impact.analyze`
already returned.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_LIMIT = 25


def _evidence(payload: dict, qualified: str) -> str:
    """Best edge that explains why ``qualified`` is affected."""
    best = None
    for edge in payload["graph"]["edges"]:
        if edge["kind"] not in {"fk", "join", "value_overlap", "same_entity"}:
            continue
        endpoints = {edge["src"].split(":", 1)[-1], edge["dst"].split(":", 1)[-1]}
        if qualified not in endpoints:
            continue
        other = (endpoints - {qualified}).pop()
        if other not in payload["changed"]:
            continue
        if best is None or edge["confidence"] > best["confidence"]:
            best = edge
    if not best:
        return "declared"
    return f"{best['kind']} {best['confidence']:.2f} · {best['method']}"


def counts(payload: dict) -> dict:
    return {
        "changed": len(payload["changed"]),
        "affected": len(payload["affected"]),
        "collisions": sum(len(items) for items in payload["collisions"].values()),
        "statements": len(payload["statements"]),
        "breaking": sum(
            1 for meta in payload["changed"].values() if meta.get("severity") == "breaking"
        ),
    }


def failure(payload: dict, fail_on: str) -> tuple[bool, str]:
    """Decide whether a gate should fail, and why."""
    totals = counts(payload)
    if fail_on == "none":
        return False, ""
    reasons = []
    if totals["breaking"]:
        reasons.append(f"{totals['breaking']} breaking change(s)")
    if fail_on in {"collision", "affected"} and totals["collisions"]:
        reasons.append(f"{totals['collisions']} naming collision(s)")
    if fail_on == "affected" and totals["affected"]:
        reasons.append(f"{totals['affected']} affected column(s)")
    return bool(reasons), ", ".join(reasons)


def summary_line(payload: dict) -> str:
    totals = counts(payload)
    return (
        f"{totals['changed']} changed / {totals['affected']} affected / "
        f"{totals['collisions']} collisions / {totals['statements']} SQL"
    )


def to_markdown(payload: dict, limit: int = DEFAULT_LIMIT, version: str = "") -> str:
    """Compact GitHub-flavoured markdown: summary, table, optional details."""
    totals = counts(payload)
    lines = [
        f"### Schema Impact Map · {payload['name']}",
        "",
        f"**{totals['changed']} changed · {totals['affected']} affected · "
        f"{totals['collisions']} collisions · {totals['statements']} SQL**",
        "",
        "| Column | Role | Evidence |",
        "| --- | --- | --- |",
    ]

    rows = 0
    for qualified, meta in payload["changed"].items():
        if rows >= limit:
            break
        action = meta.get("action", "change")
        severity = meta.get("severity", "")
        role = f"changed · {action}" + (f" · {severity}" if severity else "")
        lines.append(f"| `{qualified}` | {role} | plan |")
        rows += 1

    for qualified in payload["affected"]:
        if rows >= limit:
            break
        lines.append(f"| `{qualified}` | affected | {_evidence(payload, qualified)} |")
        rows += 1

    remaining = totals["changed"] + totals["affected"] - rows
    if remaining > 0:
        lines.append(f"| … | {remaining} more | see the full map |")

    if payload["collisions"]:
        lines += ["", "<details><summary>Naming collisions</summary>", ""]
        for qualified, items in payload["collisions"].items():
            names = ", ".join(f"`{item['qualified']}`" for item in items[:5])
            lines.append(f"- `{qualified}` collides with {names}")
        lines += ["", "</details>"]

    if payload["statements"]:
        lines += ["", "<details><summary>Affected SQL</summary>", ""]
        for statement in payload["statements"]:
            name = Path(statement["file"]).name
            lines.append(f"- `{name}` · {statement['name']}")
        lines += ["", "</details>"]

    footer = "schema-impact-map"
    if version:
        footer = f"{footer} {version}"
    lines += ["", f"<sub>{footer}</sub>"]
    return "\n".join(lines)


def to_json(payload: dict, *, version: str = "", fail_on: str = "none") -> dict:
    """Stable, graph-free payload for scripts and agents."""
    failed, reason = failure(payload, fail_on)
    return {
        "tool": {"name": "schema-impact-map", "version": version},
        "plan": {"name": payload["name"], "description": payload.get("description", "")},
        "summary": counts(payload),
        "changed": [
            {"column": qualified, "action": meta.get("action"), "severity": meta.get("severity")}
            for qualified, meta in payload["changed"].items()
        ],
        "affected": [
            {"column": qualified, "evidence": _evidence(payload, qualified)}
            for qualified in payload["affected"]
        ],
        "collisions": {
            qualified: [item["qualified"] for item in items]
            for qualified, items in payload["collisions"].items()
        },
        "statements": [
            {
                "file": Path(statement["file"]).name,
                "name": statement["name"],
                "columns": statement["columns"],
            }
            for statement in payload["statements"]
        ],
        "tables": payload["tables"],
        "gate": {"fail_on": fail_on, "failed": failed, "reason": reason},
    }
