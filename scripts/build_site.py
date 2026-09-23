#!/usr/bin/env python3
"""Render data/history.json into aiapps/flight-price-tracker/index.html."""
from __future__ import annotations

import json
from datetime import date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

HISTORY_PATH = Path("data/history.json")
OUTPUT_PATH = Path("aiapps/flight-price-tracker/index.html")

FROM_AIRPORT = "DFW"
TO_AIRPORT = "ORD"
LOCAL_TZ = ZoneInfo("America/Chicago")


def outbound_stops(entry: dict) -> int | None:
    if "outbound_stops" in entry:
        return entry["outbound_stops"]
    # Older records stored the outbound leg count as "segments".
    if "segments" in entry:
        return entry["segments"] - 1
    return None


def stops_label(stops: int | None) -> str:
    if stops is None:
        return "—"
    if stops == 0:
        return "Nonstop"
    return f"{stops} stop" + ("s" if stops > 1 else "")


def local_time(iso_utc: str) -> datetime:
    return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(LOCAL_TZ)


def fmt_checked(iso_utc: str) -> str:
    return local_time(iso_utc).strftime("%b %-d, %-I:%M %p CT")


def fmt_day(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%a %b %-d")


def weekend_label(entry: dict) -> str:
    return f"{fmt_day(entry['weekend_start'])} → {fmt_day(entry['weekend_end'])}"


def build_hero(history: list[dict]) -> str:
    if not history:
        return '<p class="empty">No checks yet. The first one runs on the next scheduled job.</p>'

    latest = history[-1]
    ok_entries = [h for h in history if h.get("status") == "ok"]
    last_ok = ok_entries[-1] if ok_entries else None

    parts = []
    if latest.get("status") != "ok":
        parts.append(
            '<p class="status status-critical"><span aria-hidden="true">&#9888;</span> '
            f"Latest check failed ({escape(fmt_checked(latest['checked_at']))}): "
            f"{escape(latest.get('error') or 'unknown error')}</p>"
        )

    if last_ok is None:
        return "\n".join(parts)

    delta_html = ""
    if len(ok_entries) >= 2:
        diff = last_ok["price"] - ok_entries[-2]["price"]
        if diff > 0:
            delta_html = f'<span class="delta delta-up">&#9650; ${diff:,.0f} since previous check</span>'
        elif diff < 0:
            delta_html = f'<span class="delta delta-down">&#9660; ${-diff:,.0f} since previous check</span>'
        else:
            delta_html = '<span class="delta">No change since previous check</span>'

    airlines = ", ".join(last_ok.get("airlines") or []) or "Unknown airline"
    parts.append(
        f"""<div class="tile">
  <div class="tile-label">Cheapest round trip &middot; {escape(weekend_label(last_ok))}</div>
  <div class="tile-value">${last_ok['price']:,.0f}</div>
  {delta_html}
  <div class="tile-meta">{escape(airlines)} &middot; {escape(stops_label(outbound_stops(last_ok)))} outbound &middot; checked {escape(fmt_checked(last_ok['checked_at']))}</div>
</div>"""
    )
    return "\n".join(parts)


def build_rows(history: list[dict]) -> str:
    rows = []
    for h in reversed(history):
        checked = escape(fmt_checked(h["checked_at"]))
        weekend = escape(weekend_label(h))
        if h.get("status") == "ok":
            rows.append(
                f'<tr><td>{checked}</td><td class="num">${h["price"]:,.0f}</td><td>{weekend}</td>'
                f"<td>{escape(', '.join(h.get('airlines') or []) or '—')}</td>"
                f"<td>{escape(stops_label(outbound_stops(h)))}</td></tr>"
            )
        else:
            rows.append(
                f'<tr><td>{checked}</td><td class="num">—</td><td>{weekend}</td>'
                f'<td colspan="2" class="wrap"><span class="status-critical"><span aria-hidden="true">&#9888;</span> Failed:</span> '
                f"{escape((h.get('error') or 'unknown error')[:160])}</td></tr>"
            )
    return "\n".join(rows)


def chart_points(history: list[dict]) -> tuple[str | None, list[dict]]:
    if not history:
        return None, []
    current = history[-1]
    points = [
        {
            "t": h["checked_at"],
            "label": fmt_checked(h["checked_at"]),
            "price": h["price"],
            "airline": ", ".join(h.get("airlines") or []),
            "stops": stops_label(outbound_stops(h)),
        }
        for h in history
        if h.get("weekend_start") == current["weekend_start"] and h.get("status") == "ok"
    ]
    return weekend_label(current), points


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Daily-checked round-trip economy price for the next Friday to Sunday weekend, __FROM__ to __TO__.">
<title>__FROM__ ⇄ __TO__ Weekend Fares</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7;
  --surface: #fcfcfb;
  --ink: #0b0b0b;
  --ink-2: #52514e;
  --muted: #898781;
  --grid: #e1e0d9;
  --axis: #c3c2b7;
  --border: rgba(11,11,11,0.10);
  --series: #2a78d6;
  --series-wash: rgba(42,120,214,0.10);
  --good: #006300;
  --critical: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d;
    --surface: #1a1a19;
    --ink: #ffffff;
    --ink-2: #c3c2b7;
    --muted: #898781;
    --grid: #2c2c2a;
    --axis: #383835;
    --border: rgba(255,255,255,0.10);
    --series: #3987e5;
    --series-wash: rgba(57,135,229,0.12);
    --good: #0ca30c;
    --critical: #e66767;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d;
  --surface: #1a1a19;
  --ink: #ffffff;
  --ink-2: #c3c2b7;
  --muted: #898781;
  --grid: #2c2c2a;
  --axis: #383835;
  --border: rgba(255,255,255,0.10);
  --series: #3987e5;
  --series-wash: rgba(57,135,229,0.12);
  --good: #0ca30c;
  --critical: #e66767;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--page); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}
main { max-width: 880px; margin: 0 auto; padding: 24px 16px 48px; }
a { color: var(--series); }
.crumb { font-size: 13px; color: var(--muted); margin: 0 0 16px; }
.crumb a { color: var(--ink-2); text-decoration: none; }
.crumb a:hover { text-decoration: underline; }
h1 { font-size: 22px; font-weight: 600; margin: 0 0 4px; }
.sub { color: var(--ink-2); margin: 0 0 24px; }
h2 { font-size: 15px; font-weight: 600; margin: 0 0 4px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 20px; }
.tile-label { font-size: 13px; color: var(--ink-2); }
.tile-value { font-size: 48px; font-weight: 600; line-height: 1.1; margin: 4px 0; }
.tile-meta { font-size: 13px; color: var(--muted); margin-top: 6px; }
.delta { font-size: 14px; color: var(--ink-2); }
.delta-up { color: var(--critical); }
.delta-down { color: var(--good); }
.status { margin: 0 0 12px; }
.status-critical { color: var(--critical); font-weight: 600; }
.empty { color: var(--muted); margin: 0; }
.chart-sub { font-size: 13px; color: var(--muted); margin: 0 0 12px; }
.chart { position: relative; }
.chart svg { display: block; width: 100%; height: 240px; overflow: visible; touch-action: pan-y; }
.chart text { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.tooltip {
  position: absolute; pointer-events: none; background: var(--surface); color: var(--ink);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 13px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12); white-space: nowrap; transform: translate(-50%, calc(-100% - 12px));
  display: none;
}
.tooltip .tt-price { font-weight: 600; font-size: 15px; }
.tooltip .tt-meta { color: var(--ink-2); }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { font-size: 12px; font-weight: 600; color: var(--ink-2); }
td { white-space: nowrap; }
td.wrap { white-space: normal; min-width: 220px; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:last-child td { border-bottom: none; }
footer { font-size: 12px; color: var(--muted); margin-top: 24px; }
</style>
</head>
<body>
<main>
<p class="crumb"><a href="../../">&larr; aiapps</a></p>
<h1>__FROM__ ⇄ __TO__ weekend fares</h1>
<p class="sub">Cheapest round-trip economy fare for one adult, flying out Friday and back Sunday. Checked daily on Google Flights.</p>

<section class="card">
__HERO__
</section>

<section class="card">
<h2>Price trend for the upcoming weekend</h2>
<p class="chart-sub">__CHART_SUB__</p>
<div class="chart" id="chart">
  <svg id="chart-svg" role="img" aria-label="Round-trip price by check date"></svg>
  <div class="tooltip" id="tooltip"></div>
</div>
</section>

<section class="card">
<h2>All checks</h2>
<div class="table-wrap">
<table>
<thead><tr><th>Checked</th><th class="num">Price</th><th>Weekend</th><th>Airline</th><th>Outbound</th></tr></thead>
<tbody>
__ROWS__
</tbody>
</table>
</div>
</section>

<footer>Last check __LAST_CHECK__. Prices are spot checks, not guaranteed fares.</footer>
</main>

<script type="application/json" id="points">__POINTS__</script>
<script>
(function () {
  const points = JSON.parse(document.getElementById("points").textContent);
  const svg = document.getElementById("chart-svg");
  const tooltip = document.getElementById("tooltip");
  const wrap = document.getElementById("chart");
  const NS = "http://www.w3.org/2000/svg";
  const H = 240, PAD = { top: 16, right: 16, bottom: 28, left: 48 };

  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    (parent || svg).appendChild(node);
    return node;
  }

  function niceStep(range) {
    const raw = range / 4;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const n = raw / mag;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag;
  }

  function render() {
    svg.textContent = "";
    tooltip.style.display = "none";
    const W = svg.clientWidth;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);

    if (!points.length) {
      const t = el("text", { x: W / 2, y: H / 2, "text-anchor": "middle" });
      t.textContent = "No successful checks for this weekend yet";
      return;
    }

    const prices = points.map(p => p.price);
    let lo = Math.min(...prices), hi = Math.max(...prices);
    if (lo === hi) { lo -= 50; hi += 50; }
    const step = niceStep(hi - lo);
    lo = Math.floor(lo / step) * step;
    hi = Math.ceil(hi / step) * step;

    const times = points.map(p => Date.parse(p.t));
    const t0 = Math.min(...times), t1 = Math.max(...times);
    const plotW = W - PAD.left - PAD.right, plotH = H - PAD.top - PAD.bottom;
    const x = t => t1 === t0 ? PAD.left + plotW / 2 : PAD.left + (t - t0) / (t1 - t0) * plotW;
    const y = v => PAD.top + (hi - v) / (hi - lo) * plotH;

    for (let v = lo; v <= hi + 1e-9; v += step) {
      el("line", { x1: PAD.left, x2: W - PAD.right, y1: y(v), y2: y(v), stroke: v === lo ? "var(--axis)" : "var(--grid)", "stroke-width": 1 });
      const lbl = el("text", { x: PAD.left - 8, y: y(v) + 4, "text-anchor": "end" });
      lbl.textContent = "$" + v.toLocaleString();
    }

    const xy = points.map((p, i) => [x(times[i]), y(p.price)]);
    const dayFmt = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
    const maxLabels = Math.max(1, Math.floor(plotW / 70));
    const every = Math.ceil(points.length / maxLabels);
    points.forEach((p, i) => {
      if (i % every !== 0 && i !== points.length - 1) return;
      const lbl = el("text", { x: xy[i][0], y: H - 8, "text-anchor": "middle" });
      lbl.textContent = dayFmt.format(new Date(times[i]));
    });

    if (xy.length > 1) {
      const d = xy.map((q, i) => (i ? "L" : "M") + q[0] + "," + q[1]).join(" ");
      el("path", { d: d + " L" + xy[xy.length - 1][0] + "," + y(lo) + " L" + xy[0][0] + "," + y(lo) + " Z", fill: "var(--series-wash)", stroke: "none" });
      el("path", { d: d, fill: "none", stroke: "var(--series)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" });
    }

    xy.forEach(q => el("circle", { cx: q[0], cy: q[1], r: 4, fill: "var(--series)", stroke: "var(--surface)", "stroke-width": 2 }));

    const last = xy[xy.length - 1];
    const endLbl = el("text", { x: last[0], y: last[1] - 12, "text-anchor": xy.length > 1 ? "end" : "middle" });
    endLbl.style.fill = "var(--ink)";
    endLbl.style.fontWeight = "600";
    endLbl.textContent = "$" + points[points.length - 1].price.toLocaleString();

    const cross = el("line", { y1: PAD.top, y2: H - PAD.bottom, stroke: "var(--axis)", "stroke-width": 1, visibility: "hidden" });
    const focus = el("circle", { r: 6, fill: "var(--series)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" });

    function show(i) {
      const [px, py] = xy[i];
      cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.setAttribute("visibility", "visible");
      focus.setAttribute("cx", px); focus.setAttribute("cy", py); focus.setAttribute("visibility", "visible");
      const p = points[i];
      tooltip.innerHTML = "";
      const price = document.createElement("div"); price.className = "tt-price"; price.textContent = "$" + p.price.toLocaleString();
      const meta = document.createElement("div"); meta.className = "tt-meta"; meta.textContent = p.airline + " · " + p.stops + " outbound";
      const when = document.createElement("div"); when.className = "tt-meta"; when.textContent = p.label;
      tooltip.append(price, meta, when);
      tooltip.style.display = "block";
      const tw = tooltip.offsetWidth;
      tooltip.style.left = Math.min(Math.max(px, tw / 2), W - tw / 2) + "px";
      tooltip.style.top = py + "px";
    }
    function hide() {
      cross.setAttribute("visibility", "hidden");
      focus.setAttribute("visibility", "hidden");
      tooltip.style.display = "none";
    }
    svg.onpointermove = e => {
      const r = svg.getBoundingClientRect();
      const mx = e.clientX - r.left;
      let best = 0;
      xy.forEach((q, i) => { if (Math.abs(q[0] - mx) < Math.abs(xy[best][0] - mx)) best = i; });
      show(best);
    };
    svg.onpointerleave = hide;
  }

  render();
  let timer;
  window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(render, 100); });
})();
</script>
</body>
</html>
"""


def main() -> None:
    history = json.loads(HISTORY_PATH.read_text()) if HISTORY_PATH.exists() else []
    weekend, points = chart_points(history)
    chart_sub = f"{weekend} · each dot is one daily check" if weekend else "No data yet"
    rows = build_rows(history) or '<tr><td colspan="5">No checks yet.</td></tr>'

    replacements = {
        "__FROM__": FROM_AIRPORT,
        "__TO__": TO_AIRPORT,
        "__HERO__": build_hero(history),
        "__CHART_SUB__": escape(chart_sub),
        "__ROWS__": rows,
        "__LAST_CHECK__": escape(fmt_checked(history[-1]["checked_at"])) if history else "never",
        "__POINTS__": json.dumps(points).replace("</", "<\\/"),
    }
    html = PAGE_TEMPLATE
    for key, value in replacements.items():
        html = html.replace(key, value)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html)


if __name__ == "__main__":
    main()
