import re
from pathlib import Path

from schema_impact_map.build import build_from_dir
from schema_impact_map.impact import analyze_file
from schema_impact_map.render import render_html

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


def test_rendered_pages_have_english_labels_only():
    """The UI is English; keep CJK or full-width glyphs out of the generated HTML."""
    graph = build_from_dir(DATA)
    payload = analyze_file(graph, DATA / "plans" / "customer-key.yaml")
    pages = {"map": render_html(graph), "impact": render_html(payload["graph"], payload)}
    for name, page in pages.items():
        leftovers = re.findall(r"[\u3000\u4e00-\u9fff\uff00-\uffef]+", page)
        assert not leftovers, f"{name} page has non-English labels: {leftovers[:5]}"
