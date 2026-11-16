from __future__ import annotations

import html
import json
from collections import defaultdict
from pathlib import Path

ROW_H = 20
HEADER_H = 30
CARD_W = 420
CARD_GAP = 24
DB_PAD = 20
DB_HEAD = 34
DB_GAP = 42
FIELD_W = 205


def _e(value) -> str:
    return html.escape(str(value or ""))


def _count(n: int, word: str) -> str:
    """Pluralised count, e.g. ``1 table`` / ``6 columns``."""
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _impact_classes(qualified: str, impact: dict | None) -> str:
    if not impact:
        return ""
    classes = []
    changed = impact["changed"].get(qualified)
    if changed:
        classes.append("changed")
        classes.append(f"changed-{changed['action']}")
    if qualified in impact.get("proposed", set()):
        classes.append("proposed")
    if qualified in impact.get("collision_set", set()):
        classes.append("collision")
    if qualified in impact["affected_set"]:
        classes.append("affected")
    return " ".join(classes)


def _edge_path(src: tuple, dst: tuple) -> str:
    x1, y1, w1, h1 = src
    x2, y2, w2, h2 = dst
    sx, sy = x1 + w1 / 2, y1 + h1 / 2
    dx, dy = x2 + w2 / 2, y2 + h2 / 2
    mx = (sx + dx) / 2
    return f"M{sx:.1f},{sy:.1f} C{mx:.1f},{sy:.1f} {mx:.1f},{dy:.1f} {dx:.1f},{dy:.1f}"


def _layout(graph: dict) -> dict:
    databases = defaultdict(list)
    for table in graph["tables"]:
        databases[table["database"]].append(table)
    for name in databases:
        databases[name].sort(key=lambda table: table["qualified"])

    positions: dict[str, tuple[int, int, int, int]] = {}
    table_boxes = []
    database_boxes = []
    y = 92
    width = 0

    for database in sorted(databases):
        tables = databases[database]
        ncols = min(3, len(tables))
        heights = [0] * ncols
        boxes = []
        for table in tables:
            index = min(range(ncols), key=lambda i: heights[i])
            x = DB_PAD + index * (CARD_W + CARD_GAP)
            card_y = DB_HEAD + heights[index]
            rows = max(1, (len(table["columns"]) + 1) // 2)
            height = HEADER_H + rows * ROW_H + 8
            boxes.append((table, x, card_y, height))
            heights[index] += height + CARD_GAP

        box_w = DB_PAD * 2 + ncols * CARD_W + (ncols - 1) * CARD_GAP
        box_h = DB_HEAD + max(heights) + DB_PAD
        database_boxes.append(
            {
                "name": database,
                "x": 32,
                "y": y,
                "w": box_w,
                "h": box_h,
                "tables": len(tables),
                "columns": sum(len(t["columns"]) for t in tables),
            }
        )
        for table, x, card_y, height in boxes:
            abs_x = 32 + x
            abs_y = y + card_y
            table_boxes.append(
                {"table": table, "x": abs_x, "y": abs_y, "w": CARD_W, "h": height}
            )
            for index, column in enumerate(table["columns"]):
                row = index // 2
                half = index % 2
                positions[column["qualified"]] = (
                    abs_x + 10 + half * FIELD_W,
                    abs_y + HEADER_H + row * ROW_H,
                    FIELD_W - 14,
                    ROW_H,
                )
        y += box_h + DB_GAP
        width = max(width, box_w)

    return {
        "positions": positions,
        "table_boxes": table_boxes,
        "database_boxes": database_boxes,
        "width": max(width + 64, 700),
        "height": max(y, 320),
    }


def _svg(graph: dict, layout: dict, impact: dict | None) -> str:
    positions = layout["positions"]
    width, height = layout["width"], layout["height"]
    impact_active = bool(impact and (impact["changed"] or impact["affected"] or impact["collisions"]))

    changed_tables = set()
    affected_tables = set()
    soft_tables = set()
    if impact:
        for column in impact["changed"]:
            changed_tables.add(column.rsplit(".", 1)[0])
        for column in impact["affected"]:
            affected_tables.add(column.rsplit(".", 1)[0])
        for column in impact.get("proposed", set()):
            changed_tables.add(column.rsplit(".", 1)[0])
        for items in impact["collisions"].values():
            for item in items:
                soft_tables.add(item["qualified"].rsplit(".", 1)[0])
        for statement in impact["statements"]:
            for column in statement["columns"]:
                soft_tables.add(column.rsplit(".", 1)[0])
    hard_tables = changed_tables | affected_tables
    hard_databases = {table.split(".", 1)[0] for table in hard_tables}
    soft_databases = {table.split(".", 1)[0] for table in soft_tables} - hard_databases

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" '
        f'class="map-svg" id="map">',
        "<defs>",
        '<pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">'
        '<circle cx="1" cy="1" r="1" fill="#dfe6ef"/></pattern>',
        "</defs>",
        f'<rect width="{width}" height="{height}" fill="#fbfbfd"/>',
        f'<rect width="{width}" height="{height}" fill="url(#grid)" opacity=".55"/>',
        '<g id="viewport">',
    ]

    for box in layout["database_boxes"]:
        cls = "db-box"
        if box["name"] in hard_databases:
            cls += " impact-db hard"
        elif box["name"] in soft_databases:
            cls += " impact-db soft"
        parts.append(
            f'<rect class="{cls}" x="{box["x"]}" y="{box["y"]}" width="{box["w"]}" '
            f'height="{box["h"]}" rx="10"/>'
        )
        parts.append(
            f'<text class="db-title" x="{box["x"] + 14}" y="{box["y"] + 22}" font-size="13" '
            f'font-weight="600">{_e(box["name"])} '
            f'<tspan font-weight="400" font-size="11" fill="#6b7280">'
            f'{_count(box["tables"], "table")} / {_count(box["columns"], "column")}</tspan></text>'
        )

    normal_edges = []
    impact_edges = []
    seen = set()
    for edge in graph["edges"]:
        if edge["kind"] not in {"fk", "join", "value_overlap"}:
            continue
        src = edge["src"].split(":", 1)[-1]
        dst = edge["dst"].split(":", 1)[-1]
        if src not in positions or dst not in positions:
            continue
        if src.rsplit(".", 1)[0] == dst.rsplit(".", 1)[0]:
            continue
        key = (frozenset((src, dst)), edge["kind"])
        if key in seen:
            continue
        seen.add(key)
        highlighted = bool(
            impact
            and (
                src in impact["changed"]
                or dst in impact["changed"]
                or src in impact["affected_set"]
                or dst in impact["affected_set"]
            )
        )
        cls = "edge"
        if highlighted:
            cls += " edge-impact"
        if edge.get("method") == "proposed":
            cls += " edge-proposed"
        dash = ' stroke-dasharray="5 4"' if edge.get("method") == "proposed" else (
            ' stroke-dasharray="3 3"' if edge["kind"] == "join" else ""
        )
        title = f"{src} → {dst} · {edge['kind']} · {edge['confidence']:.2f} · {edge['method']}"
        path = (
            f'<path class="{cls}" d="{_edge_path(positions[src], positions[dst])}" '
            f'fill="none"{dash}><title>{_e(title)}</title></path>'
        )
        if highlighted:
            impact_edges.append(path)
        else:
            normal_edges.append(path)

    for item in layout["table_boxes"]:
        table = item["table"]
        x, y, w, h = item["x"], item["y"], item["w"], item["h"]
        qname = table["qualified"]
        table_cls = "table-card"
        if qname in hard_tables:
            table_cls += " impact-table hard"
        elif qname in soft_tables:
            table_cls += " impact-table soft"
        parts.append(
            f'<g class="{table_cls}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7"/>'
            f'<rect class="table-head" x="{x}" y="{y}" width="{w}" height="{HEADER_H}" rx="7"/>'
            f'<text class="table-name" x="{x + 12}" y="{y + 19}" font-size="12" font-weight="600">'
            f'{_e(table["name"])}</text>'
            f'<text class="table-meta" x="{x + w - 12}" y="{y + 19}" font-size="10" '
            f'text-anchor="end">{_count(len(table["columns"]), "column")}</text></g>'
        )
        for index, column in enumerate(table["columns"]):
            row = index // 2
            half = index % 2
            fx = x + 10 + half * FIELD_W
            fy = y + HEADER_H + row * ROW_H
            classes = _impact_classes(column["qualified"], impact)
            cls = "field" + (f" {classes}" if classes else "")
            label = column["name"]
            if len(label) > 28:
                label = label[:27] + "…"
            role = _entity_role(graph, column["qualified"])
            badge = ""
            if role:
                badge = f'<text class="field-badge" x="{fx + FIELD_W - 26}" y="{fy + 14}">{role}</text>'
            elif column.get("proposed"):
                badge = f'<text class="field-badge proposed-badge" x="{fx + FIELD_W - 26}" y="{fy + 14}">+</text>'
            parts.append(
                f'<g class="{cls}" data-q="{_e(column["qualified"])}">'
                f'<rect x="{fx}" y="{fy}" width="{FIELD_W - 10}" height="{ROW_H - 1}"/>'
                f'<text class="field-name" x="{fx + 6}" y="{fy + 14}">{_e(label)}</text>'
                f"{badge}<title>{_e(column['qualified'])} · {_e(column.get('type', ''))}"
                f" {_e(column.get('comment', ''))}</title></g>"
            )

    parts.extend(normal_edges)
    parts.extend(impact_edges)
    parts.append("</g></svg>")
    return "\n".join(parts), impact_active


def _entity_role(graph: dict, qualified: str) -> str:
    for entity in graph["entities"]:
        for member in entity.get("members", []):
            if member["column"] == qualified:
                return {"canonical": "C", "alias": "A", "key": "K"}.get(member["role"], "")
    return ""


def _panel(graph: dict, impact: dict | None) -> str:
    if impact:
        changed = impact["changed"]
        affected = impact["affected"]
        collisions = [
            item
            for items in impact["collisions"].values()
            for item in items
        ]
        statements = impact["statements"]
        rows = [
            '<section><div class="kicker">IMPACT</div>',
            f'<h2>{_e(impact["name"])}</h2>',
            '<div class="counts">'
            f'<span class="red">{len(changed)} changed</span>'
            f'<span class="amber">{len(affected)} affected</span>'
            f'<span class="yellow">{len(collisions)} collisions</span>'
            f'<span>{len(statements)} SQL</span></div></section>',
            "<section><h3>Changed columns</h3>",
        ]
        for qualified, meta in changed.items():
            label = {"add": "add", "remove": "remove", "analyze": "change"}.get(meta["action"], meta["action"])
            rows.append(
                f'<button class="hit changed" data-focus="{_e(qualified)}">'
                f'<span class="dot red"></span>{_e(label)} · {_e(qualified)}</button>'
            )
        rows.append("</section>")
        if affected:
            rows.append("<section><h3>Affected columns</h3>")
            for qualified in affected[:30]:
                rows.append(
                    f'<button class="hit" data-focus="{_e(qualified)}">'
                    f'<span class="dot amber"></span>{_e(qualified)}</button>'
                )
            rows.append("</section>")
        if collisions:
            rows.append("<section><h3>Collisions</h3>")
            for item in collisions[:20]:
                rows.append(
                    f'<button class="hit" data-focus="{_e(item["qualified"])}">'
                    f'<span class="dot yellow"></span>{_e(item["qualified"])}</button>'
                )
            rows.append("</section>")
        if statements:
            rows.append("<section><h3>Affected SQL</h3>")
            for statement in statements[:10]:
                rows.append(
                    f'<div class="stmt"><span class="svc">SQL</span>'
                    f' {_e(Path(statement["file"]).name)}'
                    f'<br><small>{_e(statement["name"])}</small></div>'
                )
            rows.append("</section>")
        rows.append(
            '<section class="howto"><h3>Colors</h3>'
            '<p><span class="dot red"></span>changed / breaking&nbsp;&nbsp;'
            '<span class="dot amber"></span>affected&nbsp;&nbsp;'
            '<span class="dot yellow"></span>collision</p>'
            "<p>Click an item to focus. Red edges are impacted relationships.</p></section>"
        )
        return "\n".join(rows)

    entity_rows = []
    for entity in graph["entities"]:
        entity_rows.append(
            f'<button class="hit" data-focus="{_e(entity.get("canonical", ""))}">'
            f'<span class="ent">{_e(entity["name"])}</span>'
            f'<small>{_e(entity.get("title", ""))} · {len(entity.get("members", []))} columns</small>'
            "</button>"
        )
    stats = (
        f'<div class="stats"><span><b>{len(graph["databases"])}</b> databases</span>'
        f'<span><b>{len(graph["tables"])}</b> tables</span>'
        f'<span><b>{len(graph["columns"])}</b> columns</span>'
        f'<span><b>{len(graph["edges"])}</b> edges</span></div>'
    )
    return (
        stats
        + "<section><h3>Entities</h3>"
        + ("".join(entity_rows) or '<p class="more">none</p>')
        + "</section>"
        + '<section class="howto"><h3>Legend</h3>'
        '<p><span class="badge c">C</span> canonical&nbsp;&nbsp;'
        '<span class="badge a">A</span> alias&nbsp;&nbsp;<span class="badge k">K</span> business key</p>'
        "<p>Drag to pan, scroll to zoom, double-click / button to fit.</p></section>"
    )


def render_html(graph: dict, impact: dict | None = None, focus: str | None = None) -> str:
    if impact:
        impact = dict(impact)
        impact["affected_set"] = set(impact.get("affected", []))
        impact["collision_set"] = {
            item["qualified"]
            for items in (impact.get("collisions") or {}).values()
            for item in items
        }
        impact["proposed"] = {
            column for column, meta in (impact.get("changed") or {}).items()
            if meta.get("action") == "add"
        }
    layout = _layout(graph)
    svg, impact_active = _svg(graph, layout, impact)
    panel = _panel(graph, impact)
    title = "DataAsset · schema impact map"
    if impact_active:
        title = f"DataAsset · impact · {impact['name']}"
    subtitle = (
        f"{graph['name']} · {len(graph['databases'])} databases / {len(graph['tables'])} tables / "
        f"{len(graph['columns'])} columns / {len(graph['edges'])} edges"
    )
    toggle = '<button class="btn" data-act="dim" id="dim">Impact only</button>' if impact_active else ""
    focus_json = json.dumps(focus or "", ensure_ascii=False)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title>
<style>
  :root {{ --bg:#fbfbfd; --ink:#1c1f23; --muted:#6b7280; --line:#dbe4ef;
           --red:#d64545; --amber:#d98324; --blue:#4a7ebb; }}
  * {{ box-sizing:border-box; }}
  html,body {{ height:100%; margin:0; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;
          color:var(--ink); background:var(--bg); overflow:hidden; }}
  .app {{ height:100%; display:flex; flex-direction:column; }}
  header {{ height:64px; flex:none; display:flex; align-items:center; justify-content:space-between;
            padding:10px 18px; border-bottom:1px solid var(--line); background:#fff; z-index:5; }}
  h1 {{ font-size:16px; margin:0 0 3px; }}
  .sub {{ font-size:11.5px; color:var(--muted); }}
  .actions {{ display:flex; gap:8px; align-items:center; }}
  .btn {{ border:1px solid var(--line); background:#fff; color:#374151; border-radius:6px;
          padding:6px 10px; font-size:12px; cursor:pointer; }}
  .btn:hover {{ background:#f3f6fa; }}
  .btn.on {{ border-color:var(--red); color:var(--red); background:#fff5f5; }}
  .search {{ width:190px; border:1px solid var(--line); border-radius:6px; padding:6px 9px;
             font-size:12px; color:#374151; outline:none; }}
  .search:focus {{ border-color:#9db7d8; box-shadow:0 0 0 2px #e8f0fa; }}
  main {{ flex:1; min-height:0; display:flex; }}
  #stage {{ flex:1; position:relative; min-width:0; overflow:hidden; }}
  #stage svg {{ width:100%; height:100%; display:block; cursor:grab; touch-action:none; user-select:none; }}
  #stage svg.dragging {{ cursor:grabbing; }}
  aside {{ width:330px; flex:none; border-left:1px solid var(--line); background:#fff;
           overflow:auto; padding:14px 14px 30px; }}
  aside h2 {{ font-size:14px; margin:4px 0 8px; }}
  aside h3 {{ font-size:11.5px; text-transform:uppercase; letter-spacing:.06em;
              color:var(--muted); margin:18px 0 7px; }}
  .stats {{ display:flex; gap:8px; flex-wrap:wrap; }}
  .stats span {{ background:#f3f6fa; border-radius:5px; padding:5px 8px; font-size:11px; color:#4b5563; }}
  .stats b {{ color:#1f2937; }}
  .kicker {{ font-size:10.5px; color:var(--red); letter-spacing:.08em; font-weight:700; }}
  .counts {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }}
  .counts span {{ border-radius:5px; padding:5px 8px; font-size:11px; background:#fdf2f2; }}
  .counts .amber {{ background:#fff7e8; }}
  .counts .yellow {{ background:#fdf8e3; }}
  .counts .red {{ background:#fdecec; }}
  .hit {{ display:block; width:100%; text-align:left; border:0; border-radius:6px;
          background:#fff; padding:6px; font-size:11.5px; color:#374151; cursor:pointer;
          overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .hit:hover {{ background:#f3f6fa; }}
  .hit.changed {{ color:#a42d2d; font-weight:600; background:#fff6f6; }}
  .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
  .dot.red {{ background:var(--red); }}
  .dot.amber {{ background:var(--amber); }}
  .dot.yellow {{ background:#d4a017; }}
  .stmt {{ font-size:11px; color:#4b5563; padding:5px 4px; border-bottom:1px dashed #eef1f5; }}
  .stmt .svc {{ display:inline-block; background:#eef4fb; color:#3b6a9e; border-radius:4px;
                padding:1px 5px; font-size:10px; margin-right:4px; }}
  .stmt small {{ color:#9aa4b2; }}
  .ent {{ display:block; font-weight:600; color:#8a4b12; }}
  .hit small {{ display:block; color:#9aa4b2; font-size:10px; margin-top:2px; }}
  .howto p {{ font-size:11px; line-height:1.7; color:#4b5563; margin:4px 0; }}
  .badge {{ display:inline-block; width:16px; height:16px; line-height:16px; text-align:center;
            border-radius:50%; font-size:9px; font-weight:700; }}
  .badge.c {{ background:#f6e3d0; color:#a45b1f; }}
  .badge.a {{ background:#e8eef7; color:#5b7391; }}
  .badge.k {{ background:#e3f2e9; color:#3f7a55; }}
  #hint {{ position:absolute; left:14px; bottom:12px; font-size:10.5px; color:#8b95a3;
           background:rgba(255,255,255,.86); border:1px solid var(--line); border-radius:5px;
           padding:4px 8px; pointer-events:none; }}
  .db-box {{ fill:#f4f7fb; stroke:#b9c8da; stroke-width:1.2; }}
  .db-box.impact-db.hard {{ fill:#fff3f3; stroke:var(--red); stroke-width:2; stroke-dasharray:7 5; }}
  .db-box.impact-db.soft {{ fill:#fffaf0; stroke:var(--amber); stroke-width:1.6; stroke-dasharray:6 5; }}
  .db-title {{ fill:#334155; }}
  .table-card > rect:first-child {{ fill:#fff; stroke:#c9d5e4; stroke-width:1; }}
  .table-card.impact-table.hard > rect:first-child {{ stroke:var(--red); stroke-width:2; }}
  .table-card.impact-table.soft > rect:first-child {{ stroke:var(--amber); stroke-width:1.5; }}
  .table-head {{ fill:#eef3fa; }}
  .table-card.impact-table.hard .table-head {{ fill:#fdecec; }}
  .table-card.impact-table.soft .table-head {{ fill:#fff7e8; }}
  .table-name {{ fill:#263243; }}
  .table-meta {{ fill:#8b95a3; }}
  .field > rect {{ fill:transparent; }}
  .field-name {{ fill:#3b414a; font-size:11px; }}
  .field:hover > rect {{ fill:#eef6ff; }}
  .field-badge {{ fill:#8a99ad; font-size:9px; font-weight:700; text-anchor:end; }}
  .field-badge.proposed-badge {{ fill:var(--amber); }}
  .field.changed > rect {{ fill:#fde1e1 !important; }}
  .field.changed.changed-add > rect {{ fill:#fff0d6 !important; stroke:var(--amber); stroke-dasharray:3 2; }}
  .field.proposed > rect {{ fill:#fff0d6; stroke:var(--amber); stroke-dasharray:3 2; }}
  .field.affected > rect {{ fill:#fff7d9; }}
  .field.collision > rect {{ fill:#fff1cf; }}
  .field.changed .field-name {{ fill:#a42d2d !important; font-weight:600; }}
  .field.affected .field-name {{ fill:#8a5a00; }}
  .edge {{ stroke:#9fb0c4; stroke-width:1; stroke-opacity:.42; }}
  .edge.edge-impact {{ stroke:var(--red); stroke-width:2; stroke-opacity:.9; }}
  .edge.edge-proposed {{ stroke:var(--amber); stroke-width:1.8; stroke-opacity:.95; }}
  .field.flash > rect {{ stroke:var(--red); stroke-width:2; fill:#ffe6e6; }}
  #viewport.impact-only .field:not(.changed):not(.affected):not(.collision) {{ opacity:.10; }}
  #viewport.impact-only .table-card:not(.impact-table) {{ opacity:.10; }}
  #viewport.impact-only .edge:not(.edge-impact) {{ opacity:.02; }}
  #viewport.impact-only .db-box {{ opacity:.55; }}
</style>
</head>
<body>
<div class="app">
  <header>
    <div><h1>{_e(title)}</h1><div class="sub">{_e(subtitle)}</div></div>
    <div class="actions">
      {toggle}
      <input id="search" class="search" placeholder="Search table / column…" autocomplete="off">
      <button class="btn" data-act="fit">Fit</button>
      <button class="btn" data-act="in">+</button>
      <button class="btn" data-act="out">−</button>
    </div>
  </header>
  <main>
    <div id="stage">{svg}<div id="hint">Drag to pan · scroll to zoom · click a panel item to focus</div></div>
    <aside>{panel}</aside>
  </main>
</div>
<script>
(function () {{
  const svg = document.getElementById('map');
  const content = document.getElementById('viewport');
  const stage = document.getElementById('stage');
  const focusTarget = {focus_json};
  let x = 0, y = 0, k = 1;
  function apply() {{ content.setAttribute('transform', 'translate(' + x + ',' + y + ') scale(' + k + ')'); }}
  function fit() {{
    const box = content.getBBox();
    const vw = stage.clientWidth, vh = stage.clientHeight;
    if (!box.width || !box.height) return;
    k = Math.min((vw - 40) / box.width, (vh - 40) / box.height, 1.2);
    x = (vw - box.width * k) / 2 - box.x * k;
    y = (vh - box.height * k) / 2 - box.y * k;
    apply();
  }}
  function focus(qualified, scale) {{
    const target = Array.from(document.querySelectorAll('[data-q]'))
      .find((el) => el.getAttribute('data-q') === qualified);
    if (!target) return false;
    const box = target.getBBox();
    k = scale || 1.2;
    x = stage.clientWidth / 2 - (box.x + box.width / 2) * k;
    y = stage.clientHeight / 2 - (box.y + box.height / 2) * k;
    apply();
    target.classList.add('flash');
    setTimeout(() => target.classList.remove('flash'), 1600);
    return true;
  }}
  let drag = null;
  svg.addEventListener('pointerdown', (event) => {{
    if (event.button !== 0) return;
    drag = {{ x: event.clientX, y: event.clientY }};
    svg.setPointerCapture(event.pointerId);
    svg.classList.add('dragging');
  }});
  svg.addEventListener('pointermove', (event) => {{
    if (!drag) return;
    x += event.clientX - drag.x; y += event.clientY - drag.y;
    drag = {{ x: event.clientX, y: event.clientY }}; apply();
  }});
  function endDrag(event) {{
    if (!drag) return;
    drag = null; svg.classList.remove('dragging');
    try {{ svg.releasePointerCapture(event.pointerId); }} catch (e) {{}}
  }}
  svg.addEventListener('pointerup', endDrag);
  svg.addEventListener('pointercancel', endDrag);
  stage.addEventListener('wheel', (event) => {{
    event.preventDefault();
    const rect = stage.getBoundingClientRect();
    const mx = event.clientX - rect.left, my = event.clientY - rect.top;
    const next = Math.min(3.5, Math.max(0.08, k * (event.deltaY < 0 ? 1.12 : 1 / 1.12)));
    x = mx - (mx - x) * (next / k);
    y = my - (my - y) * (next / k);
    k = next; apply();
  }}, {{ passive: false }});
  document.querySelectorAll('[data-act]').forEach((button) => {{
    button.addEventListener('click', () => {{
      const act = button.getAttribute('data-act');
      if (act === 'fit') fit();
      if (act === 'in') {{ k = Math.min(3.5, k * 1.25); apply(); }}
      if (act === 'out') {{ k = Math.max(0.08, k / 1.25); apply(); }}
      if (act === 'dim') {{
        content.classList.toggle('impact-only');
        button.classList.toggle('on');
        button.textContent = content.classList.contains('impact-only') ? 'Show all' : 'Impact only';
      }}
    }});
  }});
  document.querySelectorAll('[data-focus]').forEach((button) => {{
    button.addEventListener('click', () => focus(button.getAttribute('data-focus')));
  }});
  const search = document.getElementById('search');
  search.addEventListener('keydown', (event) => {{
    if (event.key !== 'Enter') return;
    const query = search.value.trim().toLowerCase();
    if (!query) return;
    const hit = Array.from(document.querySelectorAll('[data-q]'))
      .find((el) => el.getAttribute('data-q').toLowerCase().includes(query));
    if (hit) focus(hit.getAttribute('data-q'));
  }});
  requestAnimationFrame(() => {{ if (!focusTarget || !focus(focusTarget, 1.15)) fit(); }});
}})();
</script>
</body>
</html>
"""


def write_html(path: Path, graph: dict, impact: dict | None = None,
               focus: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(graph, impact, focus), encoding="utf-8")
