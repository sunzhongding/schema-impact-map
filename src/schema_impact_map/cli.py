from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .build import build_from_dir
from .impact import analyze_file
from .introspect import write_sqlite_ledger
from .io import DataError, write_json
from .render import write_html
from .report import failure, summary_line, to_json, to_markdown


DEFAULT_DATA = Path("examples/shop")
DEFAULT_OUT = Path("site")


def _build(data: Path) -> dict:
    graph = build_from_dir(data)
    if not graph["check"]["ok"]:
        for error in graph["check"]["errors"]:
            print(f"  ! {error}", file=sys.stderr)
        raise DataError(f"{len(graph['check']['errors'])} data check error(s)")
    return graph


def _print_stats(graph: dict) -> None:
    stats = graph["stats"]
    print(
        f"graph: {stats['databases']} databases / {stats['tables']} tables / "
        f"{stats['columns']} columns / {stats['edges']} edges / "
        f"{stats['statements']} SQL statements"
    )


def cmd_build(args) -> int:
    graph = _build(args.data)
    _print_stats(graph)
    out = args.out / "graph.json"
    write_json(out, graph)
    print(f"-> {out}")
    return 0


def cmd_map(args) -> int:
    graph = _build(args.data)
    _print_stats(graph)
    write_html(args.out, graph, focus=args.focus)
    print(f"-> {args.out}")
    return 0


def cmd_impact(args) -> int:
    graph = _build(args.data)
    payload = analyze_file(graph, args.plan)
    failed, reason = failure(payload, args.fail_on)

    if args.format == "html":
        out = args.out or Path("site/impact.html")
        write_html(out, payload["graph"], payload, focus=next(iter(payload["changed"]), None))
        print(f"impact: {summary_line(payload)}")
        print(f"-> {out}")
    else:
        if args.format == "md":
            text = to_markdown(payload, version=__version__)
        else:
            text = json.dumps(
                to_json(payload, version=__version__, fail_on=args.fail_on), indent=2
            )
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n", encoding="utf-8")
            print(f"impact: {summary_line(payload)}", file=sys.stderr)
            print(f"-> {args.out}", file=sys.stderr)
        else:
            print(text)

    if failed:
        print(f"fail-on {args.fail_on}: {reason}", file=sys.stderr)
        return 1
    return 0


def cmd_check(args) -> int:
    graph = _build(args.data)
    check = graph["check"]
    if check["ok"]:
        print(f"PASS: {len(graph['tables'])} tables, {len(graph['columns'])} columns, "
              f"{len(graph['edges'])} edges")
        return 0
    print(f"FAIL: {len(check['errors'])} error(s)")
    for error in check["errors"]:
        print(f"  - {error}")
    return 1


def cmd_demo(args) -> int:
    graph = _build(args.data)
    _print_stats(graph)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "graph.json", graph)
    write_html(args.out / "index.html", graph)
    print(f"-> {args.out / 'index.html'}")

    impact_plan = args.data / "plans" / "customer-key.yaml"
    if impact_plan.exists():
        payload = analyze_file(graph, impact_plan)
        write_html(args.out / "impact.html", payload["graph"], payload,
                   focus=next(iter(payload["changed"]), None))
        write_json(args.out / "impact.json", payload)
        print(f"-> {args.out / 'impact.html'}")

    refund_plan = args.data / "plans" / "add-refund-status.yaml"
    if refund_plan.exists():
        payload = analyze_file(graph, refund_plan)
        write_html(args.out / "impact-refund.html", payload["graph"], payload,
                   focus=next(iter(payload["changed"]), None))
        print(f"-> {args.out / 'impact-refund.html'}")
    return 0


def cmd_introspect(args) -> int:
    result = write_sqlite_ledger(
        args.sqlite,
        args.out,
        database=args.name,
        force=args.force,
        write_config=args.write_config,
    )
    print(
        f"sqlite: {result['tables']} tables / {result['columns']} columns / "
        f"{result['relations']} relations -> {result['schema']}"
    )
    for warning in result["warnings"]:
        print(f"  ! {warning}", file=sys.stderr)
    for path in result["created"][1:]:
        print(f"-> {path}")
    return 0


def cmd_mcp(args) -> int:
    from .mcp import main as serve_mcp

    return serve_mcp()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schema-impact-map",
        description="Interactive relational schema map with impact highlighting.",
    )
    parser.add_argument("--version", action="version", version=f"schema-impact-map {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build graph JSON from a data directory")
    build.add_argument("--data", type=Path, default=DEFAULT_DATA)
    build.add_argument("--out", type=Path, default=Path("dist"))
    build.set_defaults(func=cmd_build)

    map_cmd = sub.add_parser("map", help="render the interactive schema map")
    map_cmd.add_argument("--data", type=Path, default=DEFAULT_DATA)
    map_cmd.add_argument("--out", type=Path, default=Path("site/map.html"))
    map_cmd.add_argument("--focus", help="column to focus initially")
    map_cmd.set_defaults(func=cmd_map)

    impact = sub.add_parser("impact", help="render a plan-impact map")
    impact.add_argument("--data", type=Path, default=DEFAULT_DATA)
    impact.add_argument("--plan", type=Path, required=True)
    impact.add_argument("--format", choices=["html", "md", "json"], default="html",
                        help="output format (default: html)")
    impact.add_argument("--out", type=Path, default=None,
                        help="output file (html: site/impact.html; md/json: stdout)")
    impact.add_argument("--fail-on", choices=["none", "breaking", "collision", "affected"],
                        default="none", help="exit 1 when the plan reaches this severity")
    impact.set_defaults(func=cmd_impact)

    check = sub.add_parser("check", help="validate the demo data / ledger")
    check.add_argument("--data", type=Path, default=DEFAULT_DATA)
    check.set_defaults(func=cmd_check)

    demo = sub.add_parser("demo", help="build graph + map + impact pages for the demo")
    demo.add_argument("--data", type=Path, default=DEFAULT_DATA)
    demo.add_argument("--out", type=Path, default=DEFAULT_OUT)
    demo.set_defaults(func=cmd_demo)

    introspect = sub.add_parser(
        "introspect",
        help="generate schema.json from a SQLite file (read-only, no credentials)",
    )
    introspect.add_argument(
        "--sqlite", type=Path, required=True, help="SQLite file to read (opened read-only)"
    )
    introspect.add_argument(
        "--name", help="database name used in qualified names (default: file stem)"
    )
    introspect.add_argument(
        "--out", type=Path, default=Path("."), help="directory that receives schema.json"
    )
    introspect.add_argument(
        "--force", action="store_true", help="overwrite an existing schema.json"
    )
    introspect.add_argument(
        "--write-config",
        action="store_true",
        help="also write schema-impact-map.yaml / entities.yaml / rules.yaml if missing",
    )
    introspect.set_defaults(func=cmd_introspect)

    sub.add_parser(
        "mcp",
        help="serve the MCP tools over stdio for Claude Code, Codex, ZCode or WorkBuddy",
    ).set_defaults(func=cmd_mcp)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
