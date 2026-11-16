from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .build import build_from_dir
from .impact import analyze_file
from .io import DataError, write_json
from .render import write_html


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
    write_html(args.out, payload["graph"], payload, focus=next(iter(payload["changed"]), None))
    print(
        f"impact: {len(payload['changed'])} changed / "
        f"{len(payload['affected'])} affected / "
        f"{sum(len(v) for v in payload['collisions'].values())} collisions / "
        f"{len(payload['statements'])} SQL"
    )
    print(f"-> {args.out}")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dataasset",
        description="Interactive relational schema map with impact highlighting.",
    )
    parser.add_argument("--version", action="version", version=f"dataasset {__version__}")
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
    impact.add_argument("--out", type=Path, default=Path("site/impact.html"))
    impact.set_defaults(func=cmd_impact)

    check = sub.add_parser("check", help="validate the demo data / ledger")
    check.add_argument("--data", type=Path, default=DEFAULT_DATA)
    check.set_defaults(func=cmd_check)

    demo = sub.add_parser("demo", help="build graph + map + impact pages for the demo")
    demo.add_argument("--data", type=Path, default=DEFAULT_DATA)
    demo.add_argument("--out", type=Path, default=DEFAULT_OUT)
    demo.set_defaults(func=cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
