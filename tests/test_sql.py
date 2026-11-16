from pathlib import Path

from dataasset.build import build_from_dir

DATA = Path(__file__).resolve().parents[1] / "examples" / "shop"


def test_sql_statements_and_cross_db_tables():
    graph = build_from_dir(DATA)
    names = {statement["name"] for statement in graph["statements"]}
    assert names == {"order_detail", "invoice_report", "refund_review"}
    order_detail = next(s for s in graph["statements"] if s["name"] == "order_detail")
    assert "crm.customers.id" in order_detail["columns"]
    assert "shop.orders.customer_id" in order_detail["columns"]
    assert order_detail["joins"]


def test_declared_relation_survives_sql_merge():
    graph = build_from_dir(DATA)
    edge = next(
        edge for edge in graph["edges"]
        if edge["src"] == "column:shop.orders.customer_id"
        and edge["dst"] == "column:crm.customers.id"
    )
    assert edge["kind"] == "fk"
    assert edge["confidence"] == 1.0
    assert "sql_join" in edge["method"]
