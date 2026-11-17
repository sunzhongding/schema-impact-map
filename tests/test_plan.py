import subprocess
from pathlib import Path

import pytest
import yaml

from schema_impact_map import cli
from schema_impact_map.io import DataError
from schema_impact_map.plan import added_lines, derive_plan, parse_alembic, parse_ddl

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "examples" / "shop"

DIFF = """diff --git a/mig.sql b/mig.sql
--- a/mig.sql
+++ b/mig.sql
@@ -1,0 +2,2 @@
+ALTER TABLE orders ADD COLUMN refund_status VARCHAR(24);
+ALTER TABLE orders RENAME COLUMN status TO order_status;
"""

SQL = """
ALTER TABLE shop.orders ADD COLUMN refund_status VARCHAR(24);
ALTER TABLE shop.orders DROP COLUMN legacy_code;
ALTER TABLE shop.orders RENAME COLUMN status TO order_status;
ALTER TABLE shop.orders ALTER COLUMN total SET DATA TYPE numeric(12,3);
CREATE INDEX idx_orders_status ON shop.orders(status);
"""

ALEMBIC = """
def upgrade():
    op.add_column('shop.orders', sa.Column('refund_status', sa.String(24)))
    op.drop_column('shop.orders', 'legacy_code')
    op.alter_column('shop.orders', 'total', type_=sa.Numeric(12, 3))
    op.create_table('x')
"""


def test_added_lines_keeps_only_additions():
    assert added_lines(DIFF).splitlines() == [
        "ALTER TABLE orders ADD COLUMN refund_status VARCHAR(24);",
        "ALTER TABLE orders RENAME COLUMN status TO order_status;",
    ]


def test_parse_ddl_handles_add_drop_rename_alter():
    changes, warnings = parse_ddl(SQL)
    assert changes["add_columns"] == [
        {"table": "shop.orders", "column": "refund_status", "type": "VARCHAR(24)"}
    ]
    assert changes["remove_columns"] == ["shop.orders.legacy_code"]
    assert changes["rename_columns"] == [
        {"from": "shop.orders.status", "to": "shop.orders.order_status"}
    ]
    assert changes["analyze_columns"] == ["shop.orders.total"]
    assert any("INDEX" in warning for warning in warnings)


def test_parse_alembic_operations():
    changes, warnings = parse_alembic(ALEMBIC)
    assert changes["add_columns"] == [
        {"table": "shop.orders", "column": "refund_status", "type": "String(24)"}
    ]
    assert changes["remove_columns"] == ["shop.orders.legacy_code"]
    assert changes["analyze_columns"] == ["shop.orders.total"]
    assert any("create_table" in warning for warning in warnings)


def test_derive_plan_qualifies_bare_table_names():
    plan, _ = derive_plan(
        "ALTER TABLE orders ADD COLUMN x INT;",
        source="m.sql",
        resolver={"orders": "shop.orders"},
    )
    assert plan["changes"]["add_columns"][0]["table"] == "shop.orders"
    assert plan["name"] == "Changes in m.sql"


def test_derive_plan_rejects_input_without_column_changes():
    with pytest.raises(DataError):
        derive_plan("SELECT 1;", source="query.sql")


def test_cli_plan_writes_yaml(tmp_path, capsys):
    sql = tmp_path / "m.sql"
    sql.write_text(SQL, encoding="utf-8")
    out = tmp_path / "plan.yaml"

    assert (
        cli.main(["plan", "--sql", str(sql), "--data", str(DATA), "--out", str(out)]) == 0
    )
    plan = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert plan["changes"]["add_columns"][0] == {
        "table": "shop.orders",
        "column": "refund_status",
        "type": "VARCHAR(24)",
    }
    assert "1 add / 1 remove / 1 rename / 1 analyze" in capsys.readouterr().out


def test_cli_plan_from_git_diff(tmp_path, monkeypatch, capsys):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True, text=True)

    git("init", "-q")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "--allow-empty", "-m", "init")
    (tmp_path / "mig.sql").write_text("SELECT 1;\n", encoding="utf-8")
    git("add", ".")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-m", "base")
    with (tmp_path / "mig.sql").open("a", encoding="utf-8") as handle:
        handle.write("ALTER TABLE customers ADD COLUMN loyalty_tier VARCHAR(16);\n")
    git("add", ".")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-m", "change")

    monkeypatch.chdir(tmp_path)
    assert cli.main(["plan", "--diff", "HEAD~1", "--data", str(DATA)]) == 0
    assert "crm.customers" in capsys.readouterr().out
