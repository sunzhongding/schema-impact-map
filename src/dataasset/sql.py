from __future__ import annotations

import re
from pathlib import Path

import sqlglot
from sqlglot import exp

from .io import DataError


def _table_key(table: exp.Table) -> str:
    parts = [part for part in (table.catalog, table.db, table.name) if part]
    return ".".join(str(part) for part in parts)


class Resolver:
    def __init__(self, tables: dict[str, dict], default_database: str):
        self.tables = tables
        self.default_database = default_database
        self.by_name: dict[str, list[str]] = {}
        for qualified in tables:
            self.by_name.setdefault(qualified.rsplit(".", 1)[-1], []).append(qualified)

    def resolve_table(self, table: exp.Table) -> str | None:
        explicit = _table_key(table)
        if explicit in self.tables:
            return explicit
        if table.db:
            candidate = f"{table.db}.{table.name}"
            if candidate in self.tables:
                return candidate
        hits = self.by_name.get(str(table.name), [])
        if len(hits) == 1:
            return hits[0]
        candidate = f"{self.default_database}.{table.name}"
        return candidate if candidate in self.tables else None

    def resolve_column(self, column: exp.Column, aliases: dict[str, str],
                       sole_table: str | None) -> tuple[str, str] | None:
        if not isinstance(column.this, exp.Identifier):
            return None
        name = column.name
        qualifier = (column.table or "").lower()
        table = aliases.get(qualifier) if qualifier else sole_table
        if not table:
            return None
        if name == "*":
            return None
        if not any(c["name"] == name for c in self.tables[table]["columns"]):
            return None
        return table, name


def parse_sql_files(sql_dir: Path, dialect: str, tables: dict[str, dict],
                    default_database: str) -> list[dict]:
    if not sql_dir.exists():
        return []
    resolver = Resolver(tables, default_database)
    statements: list[dict] = []

    for path in sorted(sql_dir.rglob("*.sql")):
        raw = path.read_text(encoding="utf-8")
        name = None
        match = re.search(r"^\s*--\s*name:\s*(\S+)", raw, re.MULTILINE)
        if match:
            name = match.group(1)
        name = name or path.stem

        try:
            trees = sqlglot.parse(raw, read=dialect)
        except Exception as exc:  # noqa: BLE001 - report parse failures to the user
            raise DataError(f"cannot parse {path}: {exc}") from exc

        for index, tree in enumerate(trees):
            if tree is None:
                continue
            aliases: dict[str, str] = {}
            used_tables: set[str] = set()
            for table in tree.find_all(exp.Table):
                resolved = resolver.resolve_table(table)
                if not resolved:
                    continue
                used_tables.add(resolved)
                alias = (table.alias or table.name).lower()
                aliases[alias] = resolved
                aliases.setdefault(str(table.name).lower(), resolved)
            sole = next(iter(used_tables)) if len(used_tables) == 1 else None

            columns: set[str] = set()
            for column in tree.find_all(exp.Column):
                resolved = resolver.resolve_column(column, aliases, sole)
                if resolved:
                    columns.add(f"{resolved[0]}.{resolved[1]}")

            join_pairs: list[dict] = []
            conditions = []
            for join in tree.find_all(exp.Join):
                if join.args.get("on") is not None:
                    conditions.append(join.args["on"])
            where = tree.args.get("where")
            if where is not None:
                conditions.append(where.this)
            for condition in conditions:
                for eq in condition.find_all(exp.EQ):
                    left, right = eq.left, eq.right
                    if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                        continue
                    lres = resolver.resolve_column(left, aliases, sole)
                    rres = resolver.resolve_column(right, aliases, sole)
                    if not lres or not rres or lres == rres:
                        continue
                    join_pairs.append(
                        {
                            "left": f"{lres[0]}.{lres[1]}",
                            "right": f"{rres[0]}.{rres[1]}",
                            "snippet": f"{left.sql()} = {right.sql()}",
                        }
                    )

            statements.append(
                {
                    "id": f"sql:{name}:{index}",
                    "name": name,
                    "file": f"{sql_dir.name}/{path.relative_to(sql_dir)}",
                    "database": default_database,
                    "columns": sorted(columns),
                    "joins": join_pairs,
                }
            )
    return statements
