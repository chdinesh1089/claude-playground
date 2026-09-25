#!/usr/bin/env python3
"""Render the daily briefing pages from data/news/YYYY-MM-DD.json.

Writes aiapps/daily-briefing/index.html (the latest day) plus one
aiapps/daily-briefing/YYYY-MM-DD.html per stored day, and removes pages for
days that are no longer stored. Output depends only on the data files.

  --issue PATH  also write {"title", "body"} JSON for the daily GitHub issue.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date as Date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

NEWS_DIR = Path("data/news")
OUT_DIR = Path("aiapps/daily-briefing")
LOCAL_TZ = ZoneInfo("America/Chicago")
SECTIONS = {
    "top": "Top stories",
    "us": "United States",
    "india": "India",
    "world": "World",
    "business_tech": "Business & Tech",
}
SHORT = {"top": "Top", "us": "US", "india": "India", "world": "World", "business_tech": "Business"}
WORDS_PER_MIN = 230

CSS = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e;
  --muted: #7a7873; --border: rgba(11,11,11,0.10); --accent: #2a78d6;
  --accent-soft: rgba(42,120,214,0.10); --warn-bg: #fdf3e1; --warn-ink: #7a4b00;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f4f4f2; --ink-2: #c3c2b7;
    --muted: #8f8d86; --border: rgba(255,255,255,0.10); --accent: #5c9eea;
    --accent-soft: rgba(92,158,234,0.14); --warn-bg: #2d2412; --warn-ink: #f0c874;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f4f4f2; --ink-2: #c3c2b7;
  --muted: #8f8d86; --border: rgba(255,255,255,0.10); --accent: #5c9eea;
  --accent-soft: rgba(92,158,234,0.14); --warn-bg: #2d2412; --warn-ink: #f0c874;
}
* { box-sizing: border-box; }
html { scroll-padding-top: 64px; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-text-size-adjust: 100%; }
main { max-width: 680px; margin: 0 auto; padding: 28px 16px 48px; }
header .kicker { color: var(--accent); font-size: 13px; font-weight: 600;
  letter-spacing: .06em; text-transform: uppercase; margin: 0; }
h1 { font-size: 28px; line-height: 1.2; font-weight: 700; margin: 4px 0 6px; letter-spacing: -.01em; }
.sub { color: var(--muted); font-size: 14px; margin: 0; }
nav.jump { position: sticky; top: 0; z-index: 2; background: var(--page);
  display: flex; gap: 6px; overflow-x: auto; padding: 12px 0; margin: 12px 0 4px;
  border-bottom: 1px solid var(--border); scrollbar-width: none; }
nav.jump::-webkit-scrollbar { display: none; }
nav.jump a { flex: none; font-size: 14px; color: var(--ink-2); text-decoration: none;
  padding: 5px 12px; border: 1px solid var(--border); border-radius: 999px; background: var(--surface); }
nav.jump a:hover, nav.jump a:focus-visible { color: var(--accent); border-color: var(--accent); }
.notice { background: var(--warn-bg); color: var(--warn-ink); border-radius: 10px;
  padding: 10px 14px; font-size: 14px; margin: 16px 0 0; }
section { margin-top: 28px; }
h2 { font-size: 13px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 4px; }
ol { list-style: none; margin: 0; padding: 0; }
li.story { padding: 14px 0; border-bottom: 1px solid var(--border); }
li.story:last-child { border-bottom: 0; }
.top li.story { display: grid; grid-template-columns: 28px 1fr; }
.num { color: var(--accent); font-weight: 700; font-size: 18px; line-height: 1.35; }
.headline { font-size: 17px; font-weight: 600; line-height: 1.35; color: var(--ink);
  text-decoration: none; }
.top .headline { font-size: 18px; }
a.headline:hover, a.headline:focus-visible { color: var(--accent); text-decoration: underline; }
.summary { color: var(--ink-2); margin: 4px 0 0; }
.why { margin: 6px 0 0; font-size: 14px; color: var(--ink-2); background: var(--accent-soft);
  border-radius: 6px; padding: 4px 8px; display: inline-block; }
.why b { color: var(--accent); font-weight: 600; }
.meta { color: var(--muted); font-size: 13px; margin: 6px 0 0; }
.meta a { color: var(--muted); }
.meta a:hover { color: var(--accent); }
.empty { color: var(--muted); font-size: 14px; padding: 8px 0; }
footer { margin-top: 36px; padding-top: 16px; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 13px; }
.days { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 12px; font-size: 15px; }
.days a { color: var(--accent); text-decoration: none; }
.days a:hover { text-decoration: underline; }
footer p { margin: 6px 0; }
@media (max-width: 420px) { h1 { font-size: 24px; } .top li.story { grid-template-columns: 24px 1fr; } }
"""

# Turns each <time> into "3h ago" for today's stories; older ones keep their date.
SCRIPT = """
document.querySelectorAll('time[data-rel]').forEach(function (el) {
  var h = (Date.now() - Date.parse(el.getAttribute('datetime'))) / 36e5;
  if (!(h >= 0) || h > 36) return;
  el.textContent = h < 1 ? Math.max(1, Math.round(h * 60)) + 'm ago' : Math.round(h) + 'h ago';
});
"""


def fmt_time(iso: str | None) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso).astimezone(LOCAL_TZ)
    return f"{dt:%b} {dt.day}, {dt.hour % 12 or 12}:{dt:%M} {'AM' if dt.hour < 12 else 'PM'} CT"


def long_date(d: str) -> str:
    dt = Date.fromisoformat(d)
    return f"{dt:%A}, {dt:%B} {dt.day}"


def short_date(d: str) -> str:
    dt = Date.fromisoformat(d)
    return f"{dt:%a} {dt:%b} {dt.day}"


def word_count(rec: dict) -> int:
    n = 0
    for items in rec["sections"].values():
        for s in items:
            n += len(f'{s["headline"]} {s["summary"]} {s.get("why", "")}'.split())
    return n


def render_story(s: dict, i: int, top: bool) -> str:
    links = s.get("links") or []
    first = links[0] if links else None
    head = escape(s["headline"])
    if first:
        head = f'<a class="headline" href="{escape(first["url"])}" target="_blank" rel="noopener">{head}</a>'
    else:
        head = f'<span class="headline">{head}</span>'
    parts = []
    if first:
        parts.append(escape(first["source"]))
    if s.get("outlets", 1) > 1:
        parts.append(f'{s["outlets"]} outlets')
    if s.get("published"):
        parts.append(f'<time datetime="{escape(s["published"])}" data-rel>{fmt_time(s["published"])}</time>')
    meta = " · ".join(parts)
    if len(links) > 1:
        more = ", ".join(
            f'<a href="{escape(l["url"])}" target="_blank" rel="noopener">{escape(l["source"])}</a>' for l in links[1:]
        )
        meta += f" · Also: {more}"
    body = [f"<div>{head}"]
    if s.get("summary"):
        body.append(f'<p class="summary">{escape(s["summary"])}</p>')
    if top and s.get("why"):
        body.append(f'<p class="why"><b>Why it matters:</b> {escape(s["why"])}</p>')
    body.append(f'<p class="meta">{meta}</p></div>')
    num = f'<span class="num">{i}</span>' if top else ""
    return f'<li class="story">{num}{"".join(body)}</li>'


def render_page(rec: dict, prev_day: str | None, next_day: str | None, is_index: bool, latest: str) -> str:
    d = rec["date"]
    sections = rec.get("sections") or {}
    count = sum(len(v) for v in sections.values())
    minutes = max(1, round(word_count(rec) / WORDS_PER_MIN))
    title = "Daily Briefing" if is_index else f"Daily Briefing · {short_date(d)}"

    notice = ""
    if rec["status"] == "fallback":
        notice = (
            '<p class="notice">AI summaries weren\'t available for this edition, so these are the '
            "most widely covered headlines with each outlet's own summary."
            f' Reason: {escape((rec.get("error") or "unknown")[:140])}</p>'
        )
    elif rec["status"] != "ok":
        notice = f'<p class="notice">{escape(rec.get("error") or "This edition failed to build.")}</p>'

    chips, blocks = [], []
    for key, heading in SECTIONS.items():
        items = sections.get(key) or []
        if not items:
            continue
        chips.append(f'<a href="#{key}">{SHORT[key]}</a>')
        lis = "\n".join(render_story(s, i + 1, key == "top") for i, s in enumerate(items))
        blocks.append(f'<section id="{key}" class="{key}"><h2>{heading}</h2><ol>\n{lis}\n</ol></section>')
    if not blocks:
        blocks.append('<p class="empty">No stories in this edition.</p>')

    def day_link(day: str | None, label: str) -> str:
        if not day:
            return "<span></span>"
        href = "./" if day == latest and not is_index else f"{day}.html"
        return f'<a href="{href}">{label}</a>'

    days = (
        f'<div class="days">{day_link(prev_day, "← " + short_date(prev_day) if prev_day else "")}'
        f'{day_link(next_day, short_date(next_day) + " →" if next_day else "")}</div>'
    )
    feeds_failed = rec.get("feeds_failed") or []
    sources = f'Sources: {", ".join(escape(s) for s in rec.get("feeds_ok") or [])}.'
    if feeds_failed:
        sources += f' {len(feeds_failed)} feed(s) failed: {", ".join(escape(f["source"]) for f in feeds_failed)}.'
    how = f'Picked and summarized by {escape(rec["model"])}' if rec.get("model") else "Ranked by how many outlets cover each story"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="A 3-minute morning read: top US, India and world news with links to the full stories. Updated daily.">
<style>{CSS}</style>
</head>
<body>
<main>
<header>
<p class="kicker">Daily Briefing</p>
<h1>{long_date(d)}</h1>
<p class="sub">{count} stories · about {minutes} min read · Updated {fmt_time(rec.get("generated_at"))}</p>
</header>
<nav class="jump" aria-label="Sections">{"".join(chips)}</nav>
{notice}
{"".join(blocks)}
<footer>
{days}
<p>{how}. Headlines link to the original reporting.</p>
<p>{sources}</p>
</footer>
</main>
<script>{SCRIPT}</script>
</body>
</html>
"""


def issue(rec: dict) -> dict:
    owner_repo = os.environ.get("GITHUB_REPOSITORY", "chdinesh1089/claude-playground")
    owner, repo = owner_repo.split("/", 1)
    url = f"https://{owner}.github.io/{repo}/aiapps/daily-briefing/"
    lines = [f"**[Read today's briefing →]({url})**", ""]
    top = (rec.get("sections") or {}).get("top") or []
    for i, s in enumerate(top, 1):
        link = (s.get("links") or [{}])[0].get("url")
        head = f"[{s['headline']}]({link})" if link else s["headline"]
        lines.append(f"{i}. **{head}** — {s.get('summary', '')}")
    if rec["status"] != "ok":
        lines += ["", f"⚠️ Status: `{rec['status']}` — {rec.get('error') or ''}"]
    return {"title": f"📰 Daily Briefing — {long_date(rec['date'])}", "body": "\n".join(lines)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", type=Path, help="write the GitHub issue title/body JSON here")
    args = ap.parse_args()

    files = sorted(NEWS_DIR.glob("????-??-??.json"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not files:
        # Placeholder so the app is listed on the landing page before the first run.
        (OUT_DIR / "index.html").write_text(
            render_page({"date": "1970-01-01", "generated_at": None, "status": "error",
                         "error": "No briefing yet. The first one appears after the next daily run.",
                         "sections": {}}, None, None, True, "")
            .replace("<h1>Thursday, January 1</h1>", "<h1>Coming soon</h1>")
            .replace("0 stories · about 1 min read · Updated ", "Updates every morning")
        )
        print("No briefing data yet; wrote a placeholder page.")
        return
    records = [json.loads(f.read_text()) for f in files]
    days = [r["date"] for r in records]
    latest = days[-1]
    wanted = {"index.html"}
    for i, rec in enumerate(records):
        prev_day = days[i - 1] if i > 0 else None
        next_day = days[i + 1] if i + 1 < len(days) else None
        (OUT_DIR / f"{rec['date']}.html").write_text(render_page(rec, prev_day, next_day, False, latest))
        wanted.add(f"{rec['date']}.html")
    (OUT_DIR / "index.html").write_text(render_page(records[-1], days[-2] if len(days) > 1 else None, None, True, latest))
    for page in OUT_DIR.glob("*.html"):
        if page.name not in wanted:
            page.unlink()
    print(f"Built {len(records)} day(s); latest {latest}")
    if args.issue:
        args.issue.write_text(json.dumps(issue(records[-1]), ensure_ascii=False))


if __name__ == "__main__":
    main()
