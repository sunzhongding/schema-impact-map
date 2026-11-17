from __future__ import annotations

import copy
import re
from pathlib import Path

from .io import DataError, load_yaml


GENERIC_TOKENS = {"id", "code", "no", "type", "time", "name", "info", "created", "updated"}


def _column_id(qualified: str) -> str:
    return f"column:{qualified}"


def _tokens(name: str) -> set[str]:
    return {
        token for token in re.split(r"[_\W]+", name.lower())
        if token and token not in GENERIC_TOKENS
    }


def _find_column(graph: dict, qualified: str) -> dict | None:
    for column in graph["columns"]:
        if column["qualified"] == qualified:
            return column
    return None


def _find_table(graph: dict, qualified: str) -> dict | None:
    for table in graph["tables"]:
        if table["qualified"] == qualified:
            return table
    return None


def _add_column(graph: dict, table_name: str, name: str, column_type: str = "",
                comment: str = "") -> dict:
    table = _find_table(graph, table_name)
    if not table:
        raise DataError(f"table not found for new column: {table_name}")
    if _find_column(graph, f"{table_name}.{name}"):
        raise DataError(f"column already exists: {table_name}.{name}")
    column = {
        "id": _column_id(f"{table_name}.{name}"),
        "kind": "column",
        "name": name,
        "qualified": f"{table_name}.{name}",
        "table": table_name,
        "database": table["database"],
        "type": column_type,
        "pk": False,
        "unique": False,
        "comment": comment,
        "proposed": True,
    }
    graph["columns"].append(column)
    table["columns"].append(column)
    return column


def _collisions(graph: dict, column: dict, limit: int = 6) -> list[dict]:
    new_tokens = _tokens(column["name"])
    if not new_tokens:
        return []
    found = []
    for other in graph["columns"]:
        if other["qualified"] == column["qualified"]:
            continue
        tokens = _tokens(other["name"])
        shared = new_tokens & tokens
        if not shared:
            continue
        same_table = other["table"] == column["table"]
        same_database = other["database"] == column["database"]
        jaccard = len(shared) / len(new_tokens | tokens)
        if not same_table and not same_database and jaccard < 0.5:
            continue
        found.append(
            {
                "qualified": other["qualified"],
                "name": other["name"],
                "shared": sorted(shared),
                "jaccard": round(jaccard, 2),
                "same_table": same_table,
                "same_database": same_database,
                "comment": other.get("comment", ""),
            }
        )
    found.sort(key=lambda item: (not item["same_table"], not item["same_database"], -item["jaccard"]))
    return found[:limit]


def _table_of(column_id: str) -> str:
    return column_id.split(":", 1)[-1].rsplit(".", 1)[0]


def analyze(graph: dict, delta: dict) -> dict:
    changes = delta.get("changes") or {}
    changed: dict[str, dict] = {}
    proposed_edges: list[dict] = []

    for item in changes.get("add_columns") or []:
        column = _add_column(
            graph,
            item["table"],
            item["column"],
            item.get("type", ""),
            item.get("comment", ""),
        )
        changed[column["qualified"]] = {"action": "add", "severity": "info"}

    for item in changes.get("rename_columns") or []:
        old = item["from"] if isinstance(item, dict) else item
        new = item.get("to") if isinstance(item, dict) else None
        if not new:
            raise DataError(f"rename needs a 'to' column: {old}")
        column = _find_column(graph, old)
        if not column:
            raise DataError(f"column not found: {old}")
        if _find_column(graph, new):
            raise DataError(f"column already exists: {new}")
        if old.rsplit(".", 1)[0] != new.rsplit(".", 1)[0]:
            raise DataError(f"rename must stay in one table: {old} -> {new}")
        added = _add_column(
            graph,
            old.rsplit(".", 1)[0],
            new.rsplit(".", 1)[-1],
            column.get("type", ""),
            column.get("comment", ""),
        )
        added["proposed"] = True
        changed[old] = {"action": "rename", "severity": "breaking", "to": new}

    for item in changes.get("remove_columns") or []:
        qualified = item if isinstance(item, str) else item["column"]
        if not _find_column(graph, qualified):
            raise DataError(f"column not found: {qualified}")
        changed[qualified] = {"action": "remove", "severity": "breaking"}

    for item in changes.get("analyze_columns") or []:
        qualified = item if isinstance(item, str) else item["column"]
        if not _find_column(graph, qualified):
            raise DataError(f"column not found: {qualified}")
        changed[qualified] = {"action": "analyze", "severity": "breaking"}

    for edge in changes.get("add_edges") or []:
        src = edge["src"] if edge["src"].startswith("column:") else f"column:{edge['src']}"
        dst = edge["dst"] if edge["dst"].startswith("column:") else f"column:{edge['dst']}"
        if not _find_column(graph, src.split(":", 1)[-1]) or not _find_column(graph, dst.split(":", 1)[-1]):
            raise DataError(f"edge endpoint not found: {src} -> {dst}")
        entry = {
            "src": src,
            "dst": dst,
            "kind": edge.get("kind", "reads"),
            "confidence": float(edge.get("confidence", 0.8)),
            "method": "proposed",
            "evidence": {"file": "delta", "snippet": edge.get("reason", "")},
        }
        graph["edges"].append(entry)
        proposed_edges.append(entry)

    affected: set[str] = set()
    statements: dict[str, dict] = {}
    tables: set[str] = set()
    for qualified, meta in changed.items():
        tables.add(qualified.rsplit(".", 1)[0])
        node_id = _column_id(qualified)
        for edge in graph["edges"]:
            if edge["kind"] not in {"fk", "join", "value_overlap"}:
                continue
            if edge["src"] != node_id and edge["dst"] != node_id:
                continue
            other = edge["dst"] if edge["src"] == node_id else edge["src"]
            other_q = other.split(":", 1)[-1]
            affected.add(other_q)
            tables.add(other_q.rsplit(".", 1)[0])
        for statement in graph["statements"]:
            if qualified in statement["columns"]:
                statements[statement["id"]] = statement
                for column in statement["columns"]:
                    tables.add(column.rsplit(".", 1)[0])

    collisions: dict[str, list[dict]] = {}
    for qualified, meta in changed.items():
        if meta["action"] != "add":
            continue
        column = _find_column(graph, qualified)
        if column:
            collisions[qualified] = _collisions(graph, column)

    for column in affected:
        tables.add(column.rsplit(".", 1)[0])
    for items in collisions.values():
        for item in items:
            tables.add(item["qualified"].rsplit(".", 1)[0])

    return {
        "name": delta.get("name") or "proposed change",
        "description": delta.get("description", ""),
        "delta": delta,
        "changed": changed,
        "affected": sorted(affected),
        "collisions": collisions,
        "statements": list(statements.values()),
        "tables": sorted(tables),
        "proposed_edges": proposed_edges,
        "graph": graph,
    }


def analyze_file(graph: dict, plan_path: Path) -> dict:
    if not plan_path.exists():
        raise DataError(f"plan not found: {plan_path}")
    return analyze(copy.deepcopy(graph), load_yaml(plan_path))
