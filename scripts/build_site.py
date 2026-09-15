#!/usr/bin/env python3
"""Render data/history.json into a static docs/index.html for GitHub Pages."""
from __future__ import annotations

import json
from pathlib import Path

HISTORY_PATH = Path("data/history.json")
OUTPUT_PATH = Path("docs/index.html")

FROM_AIRPORT = "DFW"
TO_AIRPORT = "ORD"


def main() -> None:
    history = json.loads(HISTORY_PATH.read_text()) if HISTORY_PATH.exists() else []

    latest_weekend = history[-1]["weekend_start"] if history else None
    current_weekend_points = [
        h
        for h in history
        if h.get("weekend_start") == latest_weekend and h.get("status") == "ok"
    ]

    chart_labels = [h["checked_at"] for h in current_weekend_points]
    chart_prices = [h["price"] for h in current_weekend_points]

    rows = []
    for h in reversed(history[-200:]):
        if h.get("status") == "ok":
            price_cell = f"${h['price']:,.0f}"
            detail = ", ".join(h.get("airlines") or []) or "—"
        else:
            price_cell = "—"
            detail = (h.get("error") or "error")[:120]
        rows.append(
            f"<tr><td>{h['checked_at']}</td><td>{h['weekend_start']} &rarr; {h['weekend_end']}</td>"
            f"<td>{price_cell}</td><td>{detail}</td></tr>"
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{FROM_AIRPORT} &harr; {TO_AIRPORT} Weekend Flight Prices</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.5rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1.5rem; font-size: 0.9rem; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e0e0e0; }}
  th {{ background: #f5f5f5; }}
  .meta {{ color: #666; font-size: 0.9rem; }}
  canvas {{ max-height: 320px; }}
</style>
</head>
<body>
<h1>&#9992;&#65039; {FROM_AIRPORT} &harr; {TO_AIRPORT} Weekend Flight Prices</h1>
<p class="meta">Round-trip economy, Friday &rarr; Sunday, 1 adult. Checked daily via GitHub Actions against Google Flights.</p>
<h2>Current tracked weekend: {latest_weekend or "—"}</h2>
<canvas id="priceChart"></canvas>
<h2>History</h2>
<table>
<thead><tr><th>Checked (UTC)</th><th>Weekend</th><th>Price</th><th>Airline(s) / notes</th></tr></thead>
<tbody>
{''.join(rows) if rows else '<tr><td colspan="4">No data yet &mdash; check back after the next run.</td></tr>'}
</tbody>
</table>
<script>
new Chart(document.getElementById('priceChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(chart_labels)},
    datasets: [{{
      label: 'Round-trip price (USD)',
      data: {json.dumps(chart_prices)},
      borderColor: '#2563eb',
      backgroundColor: 'rgba(37,99,235,0.1)',
      tension: 0.2,
      fill: true
    }}]
  }},
  options: {{
    scales: {{ y: {{ beginAtZero: false }} }}
  }}
}});
</script>
</body>
</html>
"""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html)


if __name__ == "__main__":
    main()
