"""MCP server: expose schema-impact-map to AI coding clients.

The server speaks the Model Context Protocol over stdio, so clients such as
Claude Code, Codex, ZCode and WorkBuddy can call the tool provider. The MCP SDK
is optional, install it with::

    pip install "schema-impact-map[mcp]"

Every tool is read-only with respect to the ledger and never touches a database:
it reads a data directory, parses SQL text, and writes at most one static HTML
file that the caller asked for.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from . import __version__
from .build import CONFIG_FILE, build_from_dir
from .impact import analyze
from .introspect import write_sqlite_ledger
from .io import DataError, load_yaml, load_yaml_text
from .render import write_html

SERVER_NAME = "schema-impact-map"

INSTRUCTIONS = """\
Schema Impact Map answers one question: if this column changes, what breaks?

Workflow:
1. `check` the ledger (dangling relations, unknown entity members, unexplained *_id columns).
2. `impact` a plan to get the changed columns, affected columns, naming collisions and
   affected SQL statements.
3. `render` only when the user wants a page they can open or share.

`data_dir` points at a ledger folder: schema-impact-map.yaml + schema.json +
entities.yaml + rules.yaml + sql/ (see examples/shop in the repository). When the user
points at a SQLite file and there is no ledger yet, `introspect_sqlite` writes one from the
file's schema metadata (read-only, no credentials).
All tools read local files only; no database connection, no credentials, no uploads."""

PLAN_HINT = (
    "Pass either a path to a plan YAML file or the YAML itself, for example:\n"
    "name: Review customer key\n"
    "changes:\n"
    "  analyze_columns:\n"
    "    - crm.customers.id"
)


def _stats(graph: dict) -> dict:
    return dict(graph.get("stats") or {})


def _data_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists():
        raise DataError(f"data directory not found: {value}")
    if not path.is_dir():
        raise DataError(f"not a directory: {value}")
    if not (path / CONFIG_FILE).exists():
        raise DataError(
            f"{value} has no {CONFIG_FILE}; point data_dir at a ledger folder "
            "(the repository ships one in examples/shop)"
        )
    return path


def _plan(plan: str) -> dict:
    text = (plan or "").strip()
    if not text:
        raise DataError(f"no plan given; {PLAN_HINT}")
    path = Path(text).expanduser()
    if "\n" not in text and len(text) < 260 and path.is_file():
        return load_yaml(path)
    if "\n" in text or ":" in text:
        return load_yaml_text(text)
    raise DataError(f"plan not found: {text}; {PLAN_HINT}")


def _summary(changed: int, affected: int, collisions: int, statements: int) -> str:
    return (
        f"{changed} changed / {affected} affected / "
        f"{collisions} collisions / {statements} SQL"
    )


def build_graph(data_dir: str = ".") -> dict:
    """Build the schema graph for a ledger folder and report its size.

    Use this first to confirm that ``data_dir`` is a real ledger. Returns the
    database/table/column/edge counts plus any ``check`` errors.
    """
    try:
        graph = build_from_dir(_data_dir(data_dir))
    except DataError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": bool(graph["check"]["ok"]),
        "stats": _stats(graph),
        "errors": list(graph["check"]["errors"]),
    }


def check(data_dir: str = ".") -> dict:
    """Validate the ledger before trusting an impact result.

    Reports every declared relation that points at a missing column, every entity
    member that does not exist, and every ``*_id`` column that no relation or
    entity explains.
    """
    try:
        graph = build_from_dir(_data_dir(data_dir))
    except DataError as exc:
        return {"ok": False, "error": str(exc)}
    errors = list(graph["check"]["errors"])
    return {
        "ok": not errors,
        "errors": errors,
        "stats": _stats(graph),
    }


def impact(data_dir: str = ".", plan: str = "") -> dict:
    """Analyse what a proposed schema change touches. Nothing is written to disk.

    ``plan`` is a plan YAML file path or the YAML text itself (see the module
    instructions). Returns changed columns, affected columns, naming collisions,
    affected SQL statements and tables.
    """
    try:
        graph = build_from_dir(_data_dir(data_dir))
        payload = analyze(copy.deepcopy(graph), _plan(plan))
    except DataError as exc:
        return {"ok": False, "error": str(exc)}

    collisions = {
        qualified: [
            {
                "column": item["qualified"],
                "shared_tokens": item["shared"],
                "same_table": item["same_table"],
                "same_database": item["same_database"],
            }
            for item in items
        ]
        for qualified, items in payload["collisions"].items()
    }
    statements = [
        {
            "file": Path(statement["file"]).name,
            "name": statement["name"],
            "columns": statement["columns"],
        }
        for statement in payload["statements"]
    ]
    changed = [
        {"column": qualified, **meta} for qualified, meta in payload["changed"].items()
    ]
    affected = list(payload["affected"])
    collision_count = sum(len(items) for items in collisions.values())
    return {
        "ok": True,
        "name": payload["name"],
        "summary": _summary(len(changed), len(affected), collision_count, len(statements)),
        "changed": changed,
        "affected": affected,
        "collisions": collisions,
        "statements": statements,
        "tables": payload["tables"],
    }


def render(
    data_dir: str = ".",
    plan: str | None = None,
    out: str = "site/schema-impact-map.html",
    focus: str | None = None,
) -> dict:
    """Write one self-contained HTML page: the map, or the impact map when a plan is given.

    ``out`` is written relative to the current working directory. Returns the path
    and whether impact highlighting was applied, so the caller can open or link it.
    """
    try:
        graph = build_from_dir(_data_dir(data_dir))
        target = Path(out).expanduser()
        if plan:
            payload = analyze(copy.deepcopy(graph), _plan(plan))
            write_html(target, payload["graph"], payload, focus=focus or next(iter(payload["changed"]), None))
            return {
                "ok": True,
                "out": str(target),
                "mode": "impact",
                "name": payload["name"],
                "summary": _summary(
                    len(payload["changed"]),
                    len(payload["affected"]),
                    sum(len(items) for items in payload["collisions"].values()),
                    len(payload["statements"]),
                ),
            }
        write_html(target, graph, focus=focus)
        return {
            "ok": True,
            "out": str(target),
            "mode": "map",
            "stats": _stats(graph),
        }
    except DataError as exc:
        return {"ok": False, "error": str(exc)}


def introspect_sqlite(
    db_path: str,
    out_dir: str = ".",
    name: str | None = None,
    force: bool = False,
    write_config: bool = False,
) -> dict:
    """Generate ``schema.json`` from a SQLite file, opened read-only.

    Use this when the user points at a ``.db`` / ``.sqlite`` file and the repository
    has no ledger yet. Only schema metadata is read: no rows, no credentials.
    ``write_config`` also creates a starter ledger next to it (never overwrites).
    """
    try:
        result = write_sqlite_ledger(
            Path(db_path),
            Path(out_dir),
            database=name,
            force=force,
            write_config=write_config,
        )
    except DataError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, **result}


def create_server():
    """Build the MCP server; imported lazily so the CLI works without the extra."""
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        name=SERVER_NAME,
        version=__version__,
        instructions=INSTRUCTIONS,
    )
    for tool in (build_graph, check, impact, render, introspect_sqlite):
        server.add_tool(tool)
    return server


def main() -> int:
    try:
        server = create_server()
    except ModuleNotFoundError:
        print(
            'The MCP server needs the optional dependency: '
            'pip install "schema-impact-map[mcp]"',
            file=sys.stderr,
        )
        return 1
    try:
        server.run("stdio")
    except KeyboardInterrupt:  # client closed the pipe
        return 0
    return 0
