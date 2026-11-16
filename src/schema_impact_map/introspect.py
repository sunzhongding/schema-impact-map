"""Read a schema out of a live database.

SQLite is the first engine here on purpose: it is a single file, needs no server,
no credentials and no network, and can be opened read-only. That is exactly how
this tool is meant to run, so a SQLite file can become a ledger without breaking
the "no database connection" promise.

Only schema metadata is read (``PRAGMA table_list`` / ``table_info`` /
``foreign_key_list``); no row data and no statistics.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from .io import DataError, write_json


def _qi(name: str) -> str:
    """Quote an identifier for a PRAGMA argument."""
    return '"' + name.replace('"', '""') + '"'


def _table_names(conn: sqlite3.Connection) -> list[str]:
    try:
        rows = conn.execute("PRAGMA table_list").fetchall()
    except sqlite3.Error:
        rows = []
    if rows:
        # (schema, name, type, ncol, wr, strict); skip views, virtual and shadow tables
        return sorted(
            row[1]
            for row in rows
            if row[0] == "main" and row[2] == "table" and not row[1].startswith("sqlite_")
        )
    rows = conn.execute(
        "select name from sqlite_master where type = 'table' "
        "and name not like 'sqlite_%' order by name"
    ).fetchall()
    return [row[0] for row in rows]


def _columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA table_info({_qi(table)})").fetchall()
    # (cid, name, type, notnull, dflt_value, pk)
    return [
        {
            "name": row[1],
            "type": (row[2] or "").strip(),
            "pk": bool(row[5]),
        }
        for row in rows
    ]


def _unique_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    unique: set[str] = set()
    for index in conn.execute(f"PRAGMA index_list({_qi(table)})").fetchall():
        # (seq, name, unique, origin, partial)
        if not index[2]:
            continue
        columns = conn.execute(f"PRAGMA index_info({_qi(index[1])})").fetchall()
        if len(columns) == 1 and columns[0][2]:
            unique.add(columns[0][2])
    return unique


def _primary_key(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({_qi(table)})").fetchall()
    return [row[1] for row in sorted((r for r in rows if r[5]), key=lambda r: r[5])]


def _foreign_keys(
    conn: sqlite3.Connection,
    table: str,
    database: str,
    tables: dict[str, list[dict]],
    warnings: list[str],
) -> list[dict]:
    rows = conn.execute(f"PRAGMA foreign_key_list({_qi(table)})").fetchall()
    # (id, seq, table, from, to, on_update, on_delete, match)
    grouped: dict[int, list[tuple]] = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row)

    relations = []
    for fk_id, group in sorted(grouped.items()):
        parent = group[0][2]
        if parent not in tables:
            warnings.append(f"{table}: foreign key -> unknown table {parent}")
            continue
        if len(group) > 1:
            columns = ", ".join(row[3] for row in group)
            warnings.append(f"{table}: composite foreign key ({columns}) skipped")
            continue
        row = group[0]
        child_column, parent_column = row[3], row[4]
        if not parent_column:
            parent_key = _primary_key(conn, parent)
            if len(parent_key) != 1:
                warnings.append(
                    f"{table}.{child_column}: foreign key -> {parent} has no single-column key"
                )
                continue
            parent_column = parent_key[0]
        note_parts = []
        if row[5] and row[5] != "NO ACTION":
            note_parts.append(f"on update {row[5]}")
        if row[6] and row[6] != "NO ACTION":
            note_parts.append(f"on delete {row[6]}")
        relation = {
            "child": f"{database}.{table}.{child_column}",
            "parent": f"{database}.{parent}.{parent_column}",
            "method": "ddl_fk",
            "confidence": 1.0,
        }
        if note_parts:
            relation["note"] = ", ".join(note_parts)
        relations.append(relation)
    return relations


def introspect_sqlite(path: Path, database: str | None = None) -> tuple[dict, list[str]]:
    """Return ``(schema, warnings)`` for a SQLite file.

    ``schema`` matches what ``examples/shop/schema.json`` expects, so it can be
    dropped next to a ledger config and used unchanged.
    """
    path = path.expanduser()
    if not path.exists():
        raise DataError(f"sqlite database not found: {path}")
    if not path.is_file():
        raise DataError(f"not a file: {path}")

    name = database or path.stem or "main"
    uri = f"file:{quote(str(path.resolve()))}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise DataError(f"cannot open {path} read-only: {exc}") from exc

    warnings: list[str] = []
    try:
        table_names = _table_names(conn)
        if not table_names:
            raise DataError(f"{path} has no tables")

        tables: dict[str, list[dict]] = {}
        for table in table_names:
            columns = _columns(conn, table)
            if not columns:
                warnings.append(f"{table}: no columns, skipped")
                continue
            unique = _unique_columns(conn, table)
            for column in columns:
                column["unique"] = column["name"] in unique
            tables[table] = columns

        relations: list[dict] = []
        for table in tables:
            relations.extend(_foreign_keys(conn, table, name, tables, warnings))
    except sqlite3.Error as exc:
        raise DataError(f"cannot read schema from {path}: {exc}") from exc
    finally:
        conn.close()

    schema = {
        "instance": "sqlite",
        "databases": [
            {
                "name": name,
                "comment": f"SQLite file {path.name}",
                "tables": [
                    {"name": table, "columns": tables[table]} for table in sorted(tables)
                ],
            }
        ],
        "relations": relations,
    }
    return schema, warnings


def write_sqlite_ledger(
    db_path: Path,
    out_dir: Path,
    database: str | None = None,
    force: bool = False,
    write_config: bool = False,
) -> dict:
    """Write ``schema.json`` (and optionally a starter ledger) for a SQLite file.

    Returns a summary so CLI and MCP callers can print or return the same shape.
    """
    schema, warnings = introspect_sqlite(db_path, database)
    out = out_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    target = out / "schema.json"
    if target.exists() and not force:
        raise DataError(f"{target} already exists; pass force to overwrite")
    write_json(target, schema)

    tables = sum(len(db["tables"]) for db in schema["databases"])
    columns = sum(len(table["columns"]) for db in schema["databases"] for table in db["tables"])
    created = [target]
    if write_config:
        created += _write_starter_ledger(out, schema["databases"][0]["name"])

    return {
        "schema": str(target),
        "tables": tables,
        "columns": columns,
        "relations": len(schema["relations"]),
        "warnings": warnings,
        "created": [str(path) for path in created],
    }


def _write_starter_ledger(out: Path, database: str) -> list[Path]:
    """Create the ledger files around schema.json, never overwriting anything."""
    created: list[Path] = []
    config = out / "schema-impact-map.yaml"
    if not config.exists():
        config.write_text(
            f"name: {database}\ndialect: sqlite\ndefault_database: {database}\n"
            "schema: schema.json\nentities: entities.yaml\nrules: rules.yaml\nsql: sql\n",
            encoding="utf-8",
        )
        created.append(config)
    entities = out / "entities.yaml"
    if not entities.exists():
        entities.write_text("entities: {}\n", encoding="utf-8")
        created.append(entities)
    rules = out / "rules.yaml"
    if not rules.exists():
        rules.write_text('ignore_columns: {}\nrelation_patterns:\n  - "*_id"\n', encoding="utf-8")
        created.append(rules)
    sql_dir = out / "sql"
    if not sql_dir.exists():
        sql_dir.mkdir()
        created.append(sql_dir)
    return created
