import copy
import sqlite3
from pathlib import Path

import pytest

from schema_impact_map import cli
from schema_impact_map.build import build_from_dir
from schema_impact_map.impact import analyze
from schema_impact_map.introspect import introspect_sqlite, write_sqlite_ledger
from schema_impact_map.io import DataError

DDL = """
CREATE TABLE customers (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT,
  created_at TEXT
);
CREATE TABLE orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  status TEXT,
  total NUMERIC
);
CREATE TABLE notes (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER REFERENCES customers,
  body TEXT
);
CREATE TABLE pairs (
  a INTEGER, b INTEGER,
  FOREIGN KEY (a, b) REFERENCES customers(id, email)
);
CREATE VIEW v_orders AS SELECT * FROM orders;
CREATE INDEX idx_orders_status ON orders(status);
"""


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / "shop.db"
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    conn.commit()
    conn.close()
    return path


def test_reads_tables_columns_and_keys(db: Path):
    schema, warnings = introspect_sqlite(db)
    database = schema["databases"][0]
    assert database["name"] == "shop"
    assert [table["name"] for table in database["tables"]] == [
        "customers",
        "notes",
        "orders",
        "pairs",
    ]
    customers = next(t for t in database["tables"] if t["name"] == "customers")
    columns = {column["name"]: column for column in customers["columns"]}
    assert columns["id"]["pk"] is True
    assert columns["email"]["unique"] is True
    assert columns["name"]["type"] == "TEXT"
    assert warnings and "composite" in warnings[0]


def test_reads_foreign_keys_including_implicit_primary_key(db: Path):
    schema, _ = introspect_sqlite(db)
    relations = {(r["child"], r["parent"]) for r in schema["relations"]}
    assert ("shop.orders.customer_id", "shop.customers.id") in relations
    # `references customers` has no column list; the single-column PK is used
    assert ("shop.notes.customer_id", "shop.customers.id") in relations


def test_writes_ledger_and_refuses_to_overwrite(tmp_path: Path, db: Path):
    out = tmp_path / "ledger"
    result = write_sqlite_ledger(db, out, write_config=True)
    assert (out / "schema.json").exists()
    assert (out / "schema-impact-map.yaml").read_text(encoding="utf-8").startswith("name: shop")
    assert (out / "entities.yaml").exists()
    assert (out / "rules.yaml").exists()
    assert (out / "sql").is_dir()
    assert result["tables"] == 4
    assert result["relations"] == 2

    with pytest.raises(DataError):
        write_sqlite_ledger(db, out)
    assert write_sqlite_ledger(db, out, force=True)["tables"] == 4


def test_cli_introspect_then_check(tmp_path: Path, db: Path):
    out = tmp_path / "ledger"
    assert (
        cli.main(
            ["introspect", "--sqlite", str(db), "--out", str(out), "--write-config"]
        )
        == 0
    )
    assert cli.main(["check", "--data", str(out)]) == 0


def test_sqlite_ledger_parses_sqlite_sql(tmp_path: Path, db: Path):
    out = tmp_path / "ledger"
    write_sqlite_ledger(db, out, write_config=True)
    (out / "sql" / "report.sql").write_text(
        "-- name: customer_report\n"
        "select o.id, c.email from orders o join customers c on o.customer_id = c.id\n",
        encoding="utf-8",
    )
    graph = build_from_dir(out)
    assert graph["stats"]["statements"] == 1

    payload = analyze(
        copy.deepcopy(graph),
        {"name": "Review customer id", "changes": {"analyze_columns": ["shop.customers.id"]}},
    )
    assert "shop.orders.customer_id" in payload["affected"]
    assert payload["statements"]


def test_missing_file_is_a_data_error(tmp_path: Path):
    with pytest.raises(DataError):
        introspect_sqlite(tmp_path / "nope.db")
