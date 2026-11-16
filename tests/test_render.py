from pathlib import Path

from dataasset.build import build_from_dir
from dataasset.impact import analyze_file
from dataasset.render import render_html

DATA = Path(__file__).resolve().parents[1] / "examples" / "shop"


def test_map_html_is_self_contained():
    graph = build_from_dir(DATA)
    page = render_html(graph)
    assert "<svg" in page
    assert 'id="map"' in page
    assert 'data-q="shop.orders.customer_id"' in page
    assert "https://" not in page
    assert 'data-act="dim"' not in page


def test_impact_html_has_classes_and_panel():
    graph = build_from_dir(DATA)
    payload = analyze_file(graph, DATA / "plans" / "customer-key.yaml")
    page = render_html(payload["graph"], payload)
    assert "Impact only" in page
    assert "edge-impact" in page
    assert "crm.customers.id" in page
    assert "shop.orders.customer_id" in page


def test_add_column_renders_proposed_row():
    graph = build_from_dir(DATA)
    payload = analyze_file(graph, DATA / "plans" / "add-refund-status.yaml")
    page = render_html(payload["graph"], payload)
    assert 'data-q="shop.refunds.status"' in page
    assert "changed-add" in page
    assert "shop.orders.status" in page
