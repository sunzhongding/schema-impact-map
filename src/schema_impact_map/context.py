"""Compress a ledger into the slice an agent can afford to read.

An agent cannot load 4,000 columns. Given a few tables or columns it is about to
change, this module emits the parts that matter — the seed tables, their key columns,
the relationships that reach them and the SQL that touches them — and stops at a token
budget instead of truncating in the middle of a line.
"""

from __future__ import annotations

from .io import DataError

CHARS_PER_TOKEN = 4


def _resolve(seeds: list[str], graph: dict) -> tuple[list[str], list[str], list[str]]:
    tables = {table["qualified"]: table for table in graph["tables"]}
    columns = {column["qualified"]: column for column in graph["columns"]}
    by_name: dict[str, list[str]] = {}
    for qualified in tables:
        by_name.setdefault(qualified.rsplit(".", 1)[-1], []).append(qualified)

    seed_tables: list[str] = []
    focus: list[str] = []
    unmatched: list[str] = []

    for raw in seeds:
        seed = raw.strip().strip("`")
        if not seed:
            continue
        if seed in tables:
            seed_tables.append(seed)
        elif seed in columns:
            focus.append(seed)
            seed_tables.append(columns[seed]["table"])
        elif len(by_name.get(seed, [])) == 1:
            seed_tables.append(by_name[seed][0])
        else:
            hits = [qualified for qualified in columns if qualified.endswith("." + seed)]
            if len(hits) == 1:
                focus.append(hits[0])
                seed_tables.append(columns[hits[0]]["table"])
            else:
                unmatched.append(seed)

    ordered = list(dict.fromkeys(seed_tables))
    return ordered, list(dict.fromkeys(focus)), unmatched


def _edges(graph: dict) -> list[dict]:
    edges = []
    for edge in graph["edges"]:
        if edge["kind"] not in {"fk", "join", "value_overlap", "same_entity"}:
            continue
        src = edge["src"].split(":", 1)[-1]
        dst = edge["dst"].split(":", 1)[-1]
        if "." not in src or "." not in dst:  # entity nodes are not columns
            continue
        edges.append(
            {
                "src": src,
                "dst": dst,
                "kind": edge["kind"],
                "confidence": edge["confidence"],
                "method": edge["method"],
                "src_table": src.rsplit(".", 1)[0],
                "dst_table": dst.rsplit(".", 1)[0],
            }
        )
    return edges


def _column_line(column: dict, parents: dict[str, str]) -> str:
    parts = [f"- `{column['name']}`"]
    if column.get("type"):
        parts.append(column["type"])
    if column.get("pk"):
        parts.append("PK")
    elif column.get("unique"):
        parts.append("UNIQUE")
    parent = parents.get(column["qualified"])
    if parent:
        parts.append(f"→ `{parent}`")
    comment = (column.get("comment") or "").strip()
    if comment:
        parts.append(f"· {comment[:60]}")
    return " ".join(parts)


def build_context(graph: dict, seeds: list[str], budget: int = 1500) -> tuple[str, dict]:
    """Return ``(markdown, stats)`` for the requested tables/columns."""
    if not seeds:
        raise DataError("give at least one table or column")
    if budget < 200:
        raise DataError("budget must be at least 200 tokens")

    seed_tables, focus, unmatched = _resolve(seeds, graph)
    if not seed_tables:
        raise DataError(f"nothing matched: {', '.join(unmatched) or ', '.join(seeds)}")

    edges = _edges(graph)
    parents: dict[str, str] = {}
    for edge in edges:
        if edge["kind"] == "fk":
            parents.setdefault(edge["src"], edge["dst"])

    neighbours: list[str] = []
    for edge in edges:
        for near, far in ((edge["src_table"], edge["dst_table"]), (edge["dst_table"], edge["src_table"])):
            if near in seed_tables and far not in seed_tables and far not in neighbours:
                neighbours.append(far)

    tables = {table["qualified"]: table for table in graph["tables"]}
    limit = budget * CHARS_PER_TOKEN
    blocks: list[tuple[str, int]] = []  # (text, priority)

    header = f"# Schema context · {len(seed_tables)} table(s) · budget {budget} tokens"
    if focus:
        header += f" · focus {', '.join(f'`{item}`' for item in focus)}"
    blocks.append((header + "\n", 0))

    for qualified in seed_tables:
        table = tables.get(qualified)
        if not table:
            continue
        lines = [f"## `{qualified}`"]
        lines += [_column_line(column, parents) for column in table["columns"]]
        blocks.append(("\n".join(lines) + "\n", 1))

    relations = [
        edge
        for edge in edges
        if edge["src_table"] in seed_tables or edge["dst_table"] in seed_tables
    ]
    if relations:
        lines = ["## Relationships"]
        lines += [
            f"- `{edge['src']}` → `{edge['dst']}` ({edge['kind']} {edge['confidence']:.2f}"
            f" · {edge['method']})"
            for edge in relations[:30]
        ]
        blocks.append(("\n".join(lines) + "\n", 2))

    for qualified in neighbours[:8]:
        table = tables.get(qualified)
        if not table:
            continue
        key_columns = [
            column
            for column in table["columns"]
            if column.get("pk")
            or column.get("unique")
            or column["name"].endswith("_id")
            or column["qualified"] in focus
        ][:6]
        if not key_columns:
            key_columns = table["columns"][:3]
        lines = [f"## `{qualified}` (related)"]
        lines += [_column_line(column, parents) for column in key_columns]
        blocks.append(("\n".join(lines) + "\n", 3))

    statements = [
        statement
        for statement in graph["statements"]
        if any(column.rsplit(".", 1)[0] in seed_tables for column in statement["columns"])
    ]
    if statements:
        lines = ["## SQL touching these tables"]
        lines += [
            f"- `{statement['file'].rsplit('/', 1)[-1]}` · {statement['name']}"
            for statement in statements[:20]
        ]
        blocks.append(("\n".join(lines) + "\n", 4))

    blocks.sort(key=lambda item: item[1])
    text = ""
    included, dropped = 0, 0
    for block, priority in blocks:
        if len(text) + len(block) > limit:
            if priority == 0:
                text += block
            else:
                dropped += 1
            continue
        text += block + ("\n" if not block.endswith("\n\n") else "")
        included += 1

    text = text.rstrip() + "\n"
    stats = {
        "tokens": len(text) // CHARS_PER_TOKEN,
        "budget": budget,
        "tables": len(seed_tables) + len(neighbours),
        "dropped_blocks": dropped,
        "unmatched": unmatched,
    }
    return text, stats
