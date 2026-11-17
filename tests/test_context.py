from pathlib import Path

import pytest

from schema_impact_map.build import build_from_dir
from schema_impact_map.context import build_context
from schema_impact_map.io import DataError

DATA = Path(__file__).resolve().parents[1] / "examples" / "shop"


@pytest.fixture(scope="module")
def graph():
    return build_from_dir(DATA)


def test_context_includes_seed_table_and_relationships(graph):
    text, stats = build_context(graph, ["crm.customers"], budget=1500)
    assert text.startswith("# Schema context")
    assert "## `crm.customers`" in text
    assert "`id` bigint PK" in text
    assert "shop.orders.customer_id" in text
    assert stats["tokens"] <= 1500


def test_context_resolves_bare_names_and_columns(graph):
    text, _ = build_context(graph, ["customers", "orders.status"], budget=1500)
    assert "## `crm.customers`" in text
    assert "## `shop.orders`" in text


def test_context_stops_at_a_small_budget(graph):
    text, stats = build_context(graph, ["crm.customers", "shop.orders", "billing.invoices"], 300)
    assert stats["tokens"] <= 300
    assert stats["dropped_blocks"] >= 1


def test_context_reports_unmatched_seeds(graph):
    _, stats = build_context(graph, ["crm.customers", "not_a_table"], budget=800)
    assert stats["unmatched"] == ["not_a_table"]


def test_context_rejects_empty_seeds(graph):
    with pytest.raises(DataError):
        build_context(graph, [], budget=800)
    with pytest.raises(DataError):
        build_context(graph, ["  "], budget=800)


def test_context_skips_entity_edges(graph):
    text, _ = build_context(graph, ["crm.customers"], budget=1500)
    assert "(same_entity" not in text
