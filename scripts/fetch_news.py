#!/usr/bin/env python3
"""Build today's news briefing: fetch RSS feeds, group duplicate stories,
have Gemini pick and summarize the ones that matter, and write
data/news/YYYY-MM-DD.json (the date is today in America/Chicago).

Standard library only. GEMINI_API_KEY is read from the environment; without
it, or if every Gemini attempt fails, the briefing falls back to ranking by
how many outlets carry a story and using each feed's own blurb. Failures are
recorded in the JSON (status, error, feeds_failed), never silently skipped.
"""
from __future__ import annotations

import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NEWS_DIR = Path("data/news")
KEEP_DAYS = 14
LOCAL_TZ = ZoneInfo("America/Chicago")
MAX_AGE_HOURS = 36
MAX_CANDIDATES = 220
PER_REGION = 50  # candidates reserved for each feed region before the rest fill by score

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
# NEWS_MODEL (set in the workflow) is tried first; the rest are fallbacks.
DEFAULT_MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest"]

# Section id -> (heading, how many items). Order is the page order.
SECTIONS = {
    "top": ("Top stories", 5),
    "us": ("United States", 6),
    "india": ("India", 6),
    "world": ("World", 4),
    "business_tech": ("Business & Tech", 4),
}

# (source name, region hint, url). The region hint only guides the fallback
# ranking; Gemini decides the section itself.
FEEDS = [
    ("NPR", "us", "https://feeds.npr.org/1001/rss.xml"),
    ("New York Times", "us", "https://rss.nytimes.com/services/xml/rss/nyt/US.xml"),
    ("New York Times", "us", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ("PBS NewsHour", "us", "https://www.pbs.org/newshour/feeds/rss/headlines"),
    ("CBS News", "us", "https://www.cbsnews.com/latest/rss/main"),
    ("ABC News", "us", "https://feeds.abcnews.com/abcnews/topstories"),
    ("Google News US", "us", "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"),
    ("The Hindu", "india", "https://www.thehindu.com/news/national/feeder/default.rss"),
    ("Indian Express", "india", "https://indianexpress.com/section/india/feed/"),
    ("NDTV", "india", "https://feeds.feedburner.com/ndtvnews-top-stories"),
    ("Hindustan Times", "india", "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml"),
    ("Times of India", "india", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"),
    ("BBC News India", "india", "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml"),
    ("Google News India", "india", "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"),
    ("BBC News", "world", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("The Guardian", "world", "https://www.theguardian.com/world/rss"),
    ("Al Jazeera", "world", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("New York Times", "world", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("CNBC", "business_tech", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("New York Times", "business_tech", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    ("Mint", "business_tech", "https://www.livemint.com/rss/news"),
    ("Ars Technica", "business_tech", "https://feeds.arstechnica.com/arstechnica/index"),
    ("The Verge", "business_tech", "https://www.theverge.com/rss/index.xml"),
]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 claude-playground-news/1.0"
)

STOPWORDS = set(
    "a an the and or but of to in on at for with from by as is are was were be been it its "
    "this that these those after before over under into amid about says said say new news "
    "live updates update how why what who when will would could may can not no more than "
    "up out off his her their our your he she they we you i vs".split()
)


# ---------------------------------------------------------------- feeds ----

def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def clean(s: str, limit: int | None = None) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(s or "")))
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[: limit - 1].rsplit(" ", 1)[0] + "…"
    return s


def parse_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml_bytes: bytes, source: str, region: str) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    for el in root.iter():
        name = local(el.tag)
        if name not in ("item", "entry"):
            continue
        fields: dict[str, ET.Element] = {}
        for child in el:
            fields.setdefault(local(child.tag), child)
        title = clean(_text(fields.get("title")))
        link = _text(fields.get("link"))
        if not link and fields.get("link") is not None:  # Atom
            link = fields["link"].get("href", "")
        if name == "entry":
            for child in el:
                if local(child.tag) == "link" and child.get("rel", "alternate") == "alternate":
                    link = child.get("href", link)
                    break
        blurb = clean(
            _text(fields.get("description")) or _text(fields.get("summary")) or _text(fields.get("content")),
            limit=280,
        )
        published = parse_date(
            _text(fields.get("pubDate")) or _text(fields.get("published"))
            or _text(fields.get("updated")) or _text(fields.get("date"))
        )
        outlet = source
        if source.startswith("Google News"):
            # Google News titles end in " - Outlet"; <source> names the outlet.
            src = fields.get("source")
            if src is not None and _text(src):
                outlet = _text(src)
            if title.endswith(" - " + outlet):
                title = title[: -len(" - " + outlet)]
            if blurb.startswith(title):  # its description just repeats the headline
                blurb = ""
        if not title or not link.startswith("http"):
            continue
        items.append(
            {
                "title": title,
                "link": link.strip(),
                "source": outlet,
                "feed": source,
                "region": region,
                "blurb": blurb if blurb != title else "",
                "published": published.isoformat(timespec="seconds") if published else None,
            }
        )
    return items


def fetch_feed(feed: tuple[str, str, str]) -> tuple[tuple[str, str, str], list[dict] | None, str | None]:
    source, region, url = feed
    last_err = None
    for attempt in range(2):
        if attempt:
            time.sleep(3)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                items = parse_feed(resp.read(), source, region)
            if items:
                return feed, items, None
            last_err = "feed returned no items"
        except Exception as exc:  # noqa: BLE001 - any feed failure is recorded and skipped
            last_err = f"{type(exc).__name__}: {exc}"
    return feed, None, last_err


def fetch_all() -> tuple[list[dict], list[str], list[dict]]:
    items, ok, failed = [], [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for (source, region, url), got, err in pool.map(fetch_feed, FEEDS):
            if got is None:
                failed.append({"source": source, "url": url, "error": err})
                print(f"  feed failed: {source} ({url}): {err}", file=sys.stderr)
            else:
                ok.append(source)
                items.extend(got)
                print(f"  {len(got):3d} items  {source}  {url}")
    return items, sorted(set(ok)), failed


# ------------------------------------------------------------ grouping ----

def tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def cluster(items: list[dict], now: datetime) -> list[dict]:
    """Group items that are the same story (by headline word overlap)."""
    cutoff = now - timedelta(hours=MAX_AGE_HOURS)
    fresh, seen_links = [], set()
    for it in items:
        if it["link"] in seen_links:
            continue
        seen_links.add(it["link"])
        pub = datetime.fromisoformat(it["published"]) if it["published"] else None
        if pub and pub < cutoff:
            continue
        it["_tok"] = tokens(it["title"])
        fresh.append(it)
    # Newest first so each cluster's lead item is the freshest report.
    fresh.sort(key=lambda it: it["published"] or "", reverse=True)

    clusters: list[dict] = []
    for it in fresh:
        best, best_sim = None, 0.0
        for c in clusters:
            inter = len(it["_tok"] & c["tok"])
            sim = inter / (min(len(it["_tok"]), len(c["tok"])) or 1)
            # Same story: 3+ shared words covering half the shorter headline,
            # or 2 shared words that make up nearly all of it.
            if (inter >= 3 and sim >= 0.5) or (inter >= 2 and sim >= 0.8):
                if sim > best_sim:
                    best, best_sim = c, sim
        if best is not None:
            best["items"].append(it)
        else:
            clusters.append({"items": [it], "tok": set(it["_tok"])})

    out = []
    for c in clusters:
        its = c["items"]
        outlets = []
        for it in its:
            if it["source"] not in outlets:
                outlets.append(it["source"])
        regions = sorted(it["region"] for it in its)
        lead = next((it for it in its if it["blurb"]), its[0])
        out.append(
            {
                "title": lead["title"],
                "blurb": lead["blurb"],
                "region": max(sorted(set(regions)), key=regions.count),
                "published": max((it["published"] for it in its if it["published"]), default=None),
                "outlets": outlets,
                "links": [{"source": it["source"], "url": it["link"]} for it in its],
            }
        )
    for c in out:
        c["score"] = score(c, now)
    out.sort(key=lambda c: c["score"], reverse=True)
    for i, c in enumerate(out):
        c["id"] = f"s{i + 1}"
    return out


def score(c: dict, now: datetime) -> float:
    age_h = MAX_AGE_HOURS
    if c["published"]:
        age_h = max(0.0, (now - datetime.fromisoformat(c["published"])).total_seconds() / 3600)
    return len(c["outlets"]) * 2 + len(c["links"]) * 0.5 - age_h / 12


def pick_links(c: dict, limit: int = 4) -> list[dict]:
    """One link per outlet, preferring direct outlet links over Google News redirects."""
    links = sorted(c["links"], key=lambda l: "news.google.com" in l["url"])
    out, seen = [], set()
    for l in links:
        if l["source"] in seen:
            continue
        seen.add(l["source"])
        out.append(l)
        if len(out) == limit:
            break
    return out


# -------------------------------------------------------------- gemini ----

PROMPT = """You are the editor of a short daily news briefing for one reader: an Indian
living in the United States. They read it once each morning in 2-3 minutes and
want to know everything major in the US, the important news from India, and
big world events. Also give priority to anything that affects Indians in the US
(US immigration and visas such as H-1B and green cards, US-India relations,
the rupee and remittances).

Below are today's candidate stories, one per line:
id | outlets carrying it | hours old | headline | feed blurb

Choose the stories that matter most and fill these sections:
- "top": the {top} most important stories of the day from any region.
- "us": {us} more US stories.
- "india": {india} more India stories.
- "world": {world} more world stories (not US or India).
- "business_tech": {business_tech} business, markets, economy or technology stories.

Rules:
- Use each story at most once across all sections; the top stories must not be
  repeated in other sections.
- Prefer consequential hard news: policy, politics, economy, conflicts,
  disasters, major court rulings, big business and tech moves. Skip celebrity
  gossip, listicles, horoscopes, opinion pieces, live blogs that don't name an
  event, and minor sports (cricket or other sports only if genuinely major).
- If several ids are the same story, list them all in "ids" (most detailed
  first).
- "headline": a plain, factual headline of at most 12 words. No clickbait.
- "summary": one sentence of at most 30 words stating what happened. Use only
  facts present in the candidate lines. Never invent numbers, names or quotes.
- "why" (top stories only): at most 15 words on why it matters to this reader.
- If a section has fewer good stories than asked, return fewer.

Reply with JSON only, in exactly this shape:
{{"top": [{{"ids": ["s1"], "headline": "...", "summary": "...", "why": "..."}}],
 "us": [{{"ids": ["s7", "s12"], "headline": "...", "summary": "..."}}],
 "india": [...], "world": [...], "business_tech": [...]}}

Candidates:
{candidates}
"""


def candidates(clusters: list[dict]) -> list[dict]:
    """The best stories overall, but with PER_REGION reserved for each region so
    single-outlet India or world stories aren't crowded out by fresher US ones."""
    chosen, per_region = set(), {}
    for c in clusters:
        n = per_region.get(c["region"], 0)
        if n < PER_REGION:
            per_region[c["region"]] = n + 1
            chosen.add(c["id"])
    for c in clusters:
        if len(chosen) >= MAX_CANDIDATES:
            break
        chosen.add(c["id"])
    return [c for c in clusters if c["id"] in chosen][:MAX_CANDIDATES]


def candidate_lines(clusters: list[dict], now: datetime) -> str:
    lines = []
    for c in candidates(clusters):
        age = "?"
        if c["published"]:
            age = str(round((now - datetime.fromisoformat(c["published"])).total_seconds() / 3600))
        blurb = c["blurb"][:200].replace("|", "/")
        lines.append(f'{c["id"]} | {len(c["outlets"])} | {age} | {c["title"].replace("|", "/")} | {blurb}')
    return "\n".join(lines)


def call_gemini(prompt: str, api_key: str, model: str, json_mode: bool = True) -> dict:
    request = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
    if json_mode:
        request["response_format"] = {"type": "json_object"}
    body = json.dumps(request).encode()
    req = urllib.request.Request(
        GEMINI_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read())
    text = payload["choices"][0]["message"]["content"] or ""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    if not text.startswith("{") and "{" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    picked = json.loads(text)
    if not isinstance(picked, dict) or not any(isinstance(picked.get(k), list) for k in SECTIONS):
        raise ValueError(f"unexpected reply: {text[:200]}")
    return picked


def summarize(clusters: list[dict], now: datetime) -> tuple[dict | None, str | None, str | None]:
    """Return (sections from Gemini, model used, error)."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None, None, "GEMINI_API_KEY is not set"
    models = [m for m in [os.environ.get("NEWS_MODEL", "").strip()] + DEFAULT_MODELS if m]
    models = list(dict.fromkeys(models))
    prompt = PROMPT.format(candidates=candidate_lines(clusters, now), **{k: n for k, (_, n) in SECTIONS.items()})
    errors = []
    for model in models:
        json_mode = True
        for attempt in range(3):
            try:
                print(f"Asking {model} (attempt {attempt + 1}{'' if json_mode else ', no JSON mode'})…")
                return call_gemini(prompt, api_key, model, json_mode), model, None
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:300]
                errors.append(f"{model}: HTTP {exc.code} {detail}")
                print(f"  {errors[-1]}", file=sys.stderr)
                if exc.code == 400 and json_mode:
                    json_mode = False  # the endpoint may not accept response_format
                    continue
                if exc.code in (400, 401, 403, 404):
                    break  # bad model name or key; retrying won't help
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{model}: {type(exc).__name__}: {exc}")
                print(f"  {errors[-1]}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
    return None, None, errors[-1] if errors else "unknown error"


# ------------------------------------------------------------ assemble ----

def story(c: dict, headline: str | None = None, summary: str | None = None, why: str | None = None,
          extra: list[dict] = ()) -> dict:
    merged = dict(c)
    for e in extra:  # other clusters Gemini said are the same story
        merged["links"] = merged["links"] + e["links"]
        merged["outlets"] = merged["outlets"] + [o for o in e["outlets"] if o not in merged["outlets"]]
    out = {
        "headline": clean(headline or c["title"], 160),
        "summary": clean(summary or c["blurb"], 320),
        "outlets": len(merged["outlets"]),
        "published": c["published"],
        "links": pick_links(merged),
    }
    if why:
        out["why"] = clean(why, 160)
    return out


def assemble(clusters: list[dict], picked: dict | None) -> dict:
    by_id = {c["id"]: c for c in clusters}
    used: set[str] = set()
    sections: dict[str, list[dict]] = {k: [] for k in SECTIONS}

    if picked is not None:
        for key, (_, limit) in SECTIONS.items():
            for entry in picked.get(key) or []:
                if len(sections[key]) >= limit or not isinstance(entry, dict):
                    continue
                ids = [i for i in (entry.get("ids") or [entry.get("id")]) if i in by_id and i not in used]
                if not ids:
                    continue  # unknown or already used id: never show a link we didn't fetch
                used.update(ids)
                sections[key].append(
                    story(by_id[ids[0]], entry.get("headline"), entry.get("summary"),
                          entry.get("why") if key == "top" else None, [by_id[i] for i in ids[1:]])
                )

    if picked is not None:
        return sections  # Gemini may return fewer on purpose; don't pad with junk.

    # Without Gemini: rank by how many outlets carry each story.
    for key, (_, limit) in SECTIONS.items():
        for c in clusters:
            if len(sections[key]) >= limit:
                break
            if c["id"] in used or (key != "top" and c["region"] != key):
                continue
            used.add(c["id"])
            sections[key].append(story(c))
    return sections


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    date = now.astimezone(LOCAL_TZ).date().isoformat()
    print(f"Briefing for {date} ({now.isoformat()})")

    items, feeds_ok, feeds_failed = fetch_all()
    clusters = cluster(items, now)
    print(f"{len(items)} items from {len(feeds_ok)} outlets -> {len(clusters)} stories")

    record = {
        "date": date,
        "generated_at": now.isoformat(),
        "status": "ok",
        "model": None,
        "error": None,
        "feeds_ok": feeds_ok,
        "feeds_failed": feeds_failed,
        "sections": {},
    }
    if not clusters:
        record["status"] = "error"
        record["error"] = "No stories fetched from any feed"
    else:
        picked, model, err = summarize(clusters, now)
        record["model"] = model
        if picked is None:
            record["status"] = "fallback"
            record["error"] = err
        record["sections"] = assemble(clusters, picked)

    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    (NEWS_DIR / f"{date}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    keep = sorted(NEWS_DIR.glob("????-??-??.json"))[-KEEP_DAYS:]
    for old in NEWS_DIR.glob("????-??-??.json"):
        if old not in keep:
            old.unlink()
    print(f"status={record['status']} model={record['model']} error={record['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
