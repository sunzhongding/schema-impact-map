import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from schema_impact_map import mcp as tools

DATA = Path(__file__).resolve().parents[1] / "examples" / "shop"
ROOT = DATA.parents[1]
PLAN = "name: Review customer key\nchanges:\n  analyze_columns:\n    - crm.customers.id\n"
ADD_PLAN = (
    "name: Add refund status\nchanges:\n  add_columns:\n"
    "    - table: shop.refunds\n      column: status\n"
)


def test_check_reports_clean_ledger():
    result = tools.check(str(DATA))
    assert result["ok"] is True
    assert result["errors"] == []
    assert result["stats"]["tables"] == 8


def test_impact_accepts_inline_yaml():
    result = tools.impact(str(DATA), PLAN)
    assert result["ok"] is True
    assert result["changed"][0]["column"] == "crm.customers.id"
    assert "shop.orders.customer_id" in result["affected"]
    assert result["statements"]
    assert result["summary"].count("affected") == 1


def test_impact_accepts_plan_path():
    result = tools.impact(str(DATA), str(DATA / "plans" / "customer-key.yaml"))
    assert result["ok"] is True
    assert result["name"] == "Review customer key"


def test_impact_reports_unknown_plan_instead_of_raising():
    result = tools.impact(str(DATA), "no-such-plan.yaml")
    assert result["ok"] is False
    assert "plan not found" in result["error"]


def test_missing_ledger_is_reported_not_raised():
    result = tools.check(str(DATA / "missing"))
    assert result["ok"] is False
    assert "not found" in result["error"]

    result = tools.render(str(DATA / "missing"), out="whatever.html")
    assert result["ok"] is False


def test_render_writes_map_and_impact(tmp_path):
    result = tools.render(str(DATA), out=str(tmp_path / "map.html"))
    assert result["ok"] is True
    assert result["mode"] == "map"
    assert (tmp_path / "map.html").read_text(encoding="utf-8").startswith("<!doctype html>")

    result = tools.render(str(DATA), plan=ADD_PLAN, out=str(tmp_path / "impact.html"))
    assert result["mode"] == "impact"
    assert result["summary"].startswith("1 changed")
    page = (tmp_path / "impact.html").read_text(encoding="utf-8")
    assert "shop.refunds.status" in page
    assert "changed-add" in page


TOOLS = {"build_graph", "check", "impact", "render", "introspect_sqlite", "context"}


def test_create_server_registers_the_tools():
    server = tools.create_server()
    assert {tool.name for tool in asyncio.run(server.list_tools())} == TOOLS


def test_introspect_sqlite_tool(tmp_path):
    import sqlite3

    db = tmp_path / "shop.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, email TEXT UNIQUE);"
        "CREATE TABLE orders (id INTEGER PRIMARY KEY,"
        " customer_id INTEGER REFERENCES customers(id));"
    )
    conn.commit()
    conn.close()

    result = tools.introspect_sqlite(str(db), str(tmp_path / "ledger"), write_config=True)
    assert result["ok"] is True
    assert result["tables"] == 2
    assert result["relations"] == 1

    again = tools.introspect_sqlite(str(db), str(tmp_path / "ledger"))
    assert again["ok"] is False
    assert "exists" in again["error"]


def test_context_tool_returns_a_budgeted_slice():
    result = tools.context(str(DATA), "crm.customers,shop.orders", 1500)
    assert result["ok"] is True
    assert result["tokens"] <= 1500
    assert "## `crm.customers`" in result["markdown"]

    missing = tools.context(str(DATA), "", 1500)
    assert missing["ok"] is False


def test_stdio_roundtrip():
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "schema_impact_map", "mcp"]
    )

    async def scenario() -> None:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                info = await session.initialize()
                assert info.server_info.name == "schema-impact-map"
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert names == TOOLS

                result = await session.call_tool("check", {"data_dir": str(DATA)})
                assert result.is_error is False
                payload = json.loads(result.content[0].text)
                assert payload["ok"] is True

                result = await session.call_tool(
                    "impact", {"data_dir": str(DATA), "plan": PLAN}
                )
                payload = json.loads(result.content[0].text)
                assert payload["changed"][0]["column"] == "crm.customers.id"

    asyncio.run(asyncio.wait_for(scenario(), 90))
