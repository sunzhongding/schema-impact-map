from pathlib import Path

from dataasset.build import build_from_dir

DATA = Path(__file__).resolve().parents[1] / "examples" / "shop"


def test_build_demo_graph():
    graph = build_from_dir(DATA)
    assert graph["stats"]["databases"] == 4
    assert graph["stats"]["tables"] == 8
    assert graph["stats"]["columns"] == 35
    assert graph["stats"]["statements"] == 3
    assert graph["check"]["ok"], graph["check"]["errors"]


def test_cross_database_relation():
    graph = build_from_dir(DATA)
    edges = {(edge["src"], edge["dst"]) for edge in graph["edges"]}
    assert ("column:shop.orders.customer_id", "column:crm.customers.id") in edges
    assert ("column:billing.invoices.order_id", "column:shop.orders.id") in edges


def test_sql_join_merges_into_declared_fk():
    graph = build_from_dir(DATA)
    # declared FK + SQL join should be merged into one strong edge
    edge = next(
        edge for edge in graph["edges"]
        if edge["src"] == "column:shop.orders.customer_id"
        and edge["dst"] == "column:crm.customers.id"
    )
    assert edge["kind"] == "fk"
    assert edge["confidence"] == 1.0
    assert "sql_join" in edge["method"]
