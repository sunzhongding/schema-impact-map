from pathlib import Path

from dataasset.build import build_from_dir
from dataasset.impact import analyze_file

DATA = Path(__file__).resolve().parents[1] / "examples" / "shop"


def test_customer_key_impact():
    graph = build_from_dir(DATA)
    payload = analyze_file(graph, DATA / "plans" / "customer-key.yaml")
    assert payload["changed"] == {"crm.customers.id": {"action": "analyze", "severity": "breaking"}}
    assert "shop.orders.customer_id" in payload["affected"]
    assert "billing.invoices.customer_id" in payload["affected"]
    assert "crm.customer_profiles.customer_id" in payload["affected"]
    assert {statement["name"] for statement in payload["statements"]} == {
        "order_detail",
        "invoice_report",
    }


def test_add_refund_status_collisions():
    graph = build_from_dir(DATA)
    payload = analyze_file(graph, DATA / "plans" / "add-refund-status.yaml")
    assert payload["changed"]["shop.refunds.status"]["action"] == "add"
    collisions = payload["collisions"]["shop.refunds.status"]
    names = {item["qualified"] for item in collisions}
    assert "shop.orders.status" in names
    assert "billing.invoices.status" in names


def test_impact_does_not_mutate_source_graph():
    graph = build_from_dir(DATA)
    before = len(graph["columns"])
    analyze_file(graph, DATA / "plans" / "add-refund-status.yaml")
    assert len(graph["columns"]) == before
