"""Derive a plan YAML from migration SQL instead of writing it by hand.

Two inputs are supported:

* a git revision range (``--diff origin/main...HEAD``) — only added lines are read,
* a SQL file or stdin (``--sql migration.sql``) — the whole file is read.

Both SQL DDL (``ALTER TABLE ... ADD/DROP/RENAME COLUMN``) and the three Alembic
operations that cover most column changes (``op.add_column`` / ``op.drop_column`` /
``op.alter_column``) are recognised. Anything else is reported as a warning instead of
being guessed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import sqlglot
from sqlglot import exp

from .io import DataError

ADD_RE = re.compile(
    r"op\.add_column\(\s*['\"]([\w.]+)['\"]\s*,\s*sa\.Column\(\s*['\"](\w+)['\"]"
    r"\s*(?:,\s*(sa\.[A-Za-z_]+(?:\([^)]*\))?))?"
)
DROP_RE = re.compile(r"op\.drop_column\(\s*['\"]([\w.]+)['\"]\s*,\s*['\"](\w+)['\"]")
ALTER_RE = re.compile(r"op\.alter_column\(\s*['\"]([\w.]+)['\"]\s*,\s*['\"](\w+)['\"]")

IGNORED = {"CREATE", "DROP", "INDEX", "VIEW", "TRIGGER"}


def git_diff(revision: str, cwd: Path | None = None) -> str:
    """Return the unified diff of ``revision`` (``git diff <revision>``)."""
    result = subprocess.run(
        ["git", "diff", "--unified=0", "--no-color", revision],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DataError(f"git diff {revision} failed: {result.stderr.strip()}")
    return result.stdout


def added_lines(diff: str) -> str:
    """Keep only added lines from a unified diff, without the leading ``+``."""
    lines = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return "\n".join(lines)


def _qualify(name: str, resolver: dict[str, str]) -> str:
    if "." in name:
        return name
    return resolver.get(name, name)


def parse_ddl(text: str, dialect: str = "mysql", resolver: dict[str, str] | None = None) -> tuple[dict, list[str]]:
    """Parse ``ALTER TABLE`` statements into plan changes."""
    resolver = resolver or {}
    changes: dict[str, list] = {}
    warnings: list[str] = []

    try:
        statements = sqlglot.parse(text, read=dialect)
    except Exception as exc:  # noqa: BLE001 - surfacing the dialect error is the point
        raise DataError(f"cannot parse the migration SQL: {exc}") from exc

    for statement in statements:
        if statement is None:
            continue
        if not isinstance(statement, exp.Alter):
            if isinstance(statement, (exp.Create, exp.Drop)):
                kind = (statement.args.get("kind") or statement.key).upper()
                if kind in IGNORED:
                    warnings.append(f"{kind} statement ignored (only column changes become a plan)")
            continue

        table = statement.this
        table_name = ".".join(part for part in [table.db, table.name] if part) or table.name
        table_q = _qualify(table_name, resolver)

        for action in statement.args.get("actions") or []:
            if isinstance(action, exp.ColumnDef):
                column = action.this.name
                column_type = action.args.get("kind")
                changes.setdefault("add_columns", []).append(
                    {
                        "table": table_q,
                        "column": column,
                        **({"type": column_type.sql()} if column_type else {}),
                    }
                )
            elif isinstance(action, exp.Drop) and (action.args.get("kind") or "").lower() == "column":
                for column in action.args.get("tables") or []:
                    changes.setdefault("remove_columns", []).append(f"{table_q}.{column.name}")
            elif isinstance(action, exp.RenameColumn):
                target = action.args.get("to")
                if target is not None:
                    changes.setdefault("rename_columns", []).append(
                        {
                            "from": f"{table_q}.{action.this.name}",
                            "to": f"{table_q}.{target.name}",
                        }
                    )
            elif isinstance(action, exp.AlterColumn):
                changes.setdefault("analyze_columns", []).append(f"{table_q}.{action.this.name}")
            else:
                warnings.append(f"unsupported ALTER action ignored: {action.sql()[:60]}")
    return changes, warnings


def parse_alembic(text: str, resolver: dict[str, str] | None = None) -> tuple[dict, list[str]]:
    """Recognise the column-level Alembic operations."""
    resolver = resolver or {}
    changes: dict[str, list] = {}
    warnings: list[str] = []

    for match in ADD_RE.finditer(text):
        table, column, type_text = match.groups()
        entry = {"table": _qualify(table, resolver), "column": column}
        if type_text:
            entry["type"] = " ".join(type_text.removeprefix("sa.").split())[:40]
        changes.setdefault("add_columns", []).append(entry)
    for match in DROP_RE.finditer(text):
        table, column = match.groups()
        changes.setdefault("remove_columns", []).append(f"{_qualify(table, resolver)}.{column}")
    for match in ALTER_RE.finditer(text):
        table, column = match.groups()
        changes.setdefault("analyze_columns", []).append(f"{_qualify(table, resolver)}.{column}")

    if "op.create_table" in text or "op.drop_table" in text:
        warnings.append("op.create_table/op.drop_table ignored (only column changes become a plan)")
    return changes, warnings


def _dedupe(changes: dict[str, list]) -> dict[str, list]:
    result: dict[str, list] = {}
    for key, items in changes.items():
        seen = set()
        unique = []
        for item in items:
            marker = repr(sorted(item.items())) if isinstance(item, dict) else str(item)
            if marker in seen:
                continue
            seen.add(marker)
            unique.append(item)
        if unique:
            result[key] = unique
    return result


def derive_plan(
    text: str,
    *,
    source: str,
    dialect: str = "mysql",
    resolver: dict[str, str] | None = None,
) -> tuple[dict, list[str]]:
    """Turn raw migration text into a plan document plus warnings."""
    looks_python = bool(re.search(r"^\s*(def upgrade|import |from )", text, re.MULTILINE))
    if looks_python:
        sql_changes, sql_warnings = {}, []
    else:
        try:
            sql_changes, sql_warnings = parse_ddl(text, dialect, resolver)
        except DataError as exc:
            sql_changes, sql_warnings = {}, [str(exc)]
    alembic_changes, alembic_warnings = parse_alembic(text, resolver)

    order = ("add_columns", "remove_columns", "rename_columns", "analyze_columns")
    changes = _dedupe(
        {key: sql_changes.get(key, []) + alembic_changes.get(key, []) for key in order}
    )
    warnings = sql_warnings + alembic_warnings
    if not changes:
        detail = f" ({'; '.join(warnings)})" if warnings else ""
        raise DataError(f"no column changes found in {source}{detail}")

    total = sum(len(items) for items in changes.values())
    plan = {
        "name": f"Changes in {source}",
        "description": f"Derived from {total} column change(s) in {source}.",
        "changes": changes,
    }
    return plan, warnings
