# aiapps

Small self-hosted apps, published with GitHub Pages at
`https://chdinesh1089.github.io/claude-playground/`.

| URL path | What |
|---|---|
| `/` | Landing page listing every app (generated) |
| `/aiapps/flight-price-tracker/` | DFW ⇄ ORD weekend fare tracker (generated daily) |
| `/aiapps/tmux-cheatsheet/` | tmux cheat sheet (static) |
| `/aiapps/paper-plane/` | *The Paper Plane*, a one-minute story animated in three.js (static) |

## How the site is laid out

Pages serves the **repo root** of `main`, so repo paths map 1:1 to URLs:
`aiapps/<slug>/index.html` → `/aiapps/<slug>/`. `.nojekyll` turns off
Jekyll so files are served exactly as committed.

**To add an app:** commit a self-contained `aiapps/<slug>/index.html`.
`publish-site.yml` then regenerates the landing page (`index.html`), using
the page's `<title>` and optional `<meta name="description">` for the
listing. You don't need to register it anywhere.

## The Paper Plane

`aiapps/paper-plane/index.html` is a self-contained three.js animation: every
object is built from primitives in code, and the whole scene is a pure function
of one timeline value, so the scrubber can jump anywhere. `three.module.min.js`
next to it is three.js r186 (MIT), bundled and minified with esbuild so the page
has no CDN dependency. Keyboard: Space play/pause, ←/→ skip 5 s, R restart.
Honors `prefers-reduced-motion` (no camera shake, softer lightning).

## Flight Price Tracker

Daily, `.github/workflows/flight-price-tracker.yml`:

1. `scripts/check_flight_price.py` finds the next Friday that hasn't passed
   (Friday itself counts; on Sat/Sun it rolls to next week), queries Google
   Flights through [`fast-flights`](https://pypi.org/project/fast-flights/)
   (no API key), and appends the cheapest DFW→ORD Fri / ORD→DFW Sun round
   trip to `data/history.json`.
2. `scripts/build_site.py` renders `aiapps/flight-price-tracker/index.html`
   with the latest price, the trend for the current weekend, and every
   check.
3. The data and pages are committed back to `main`, and issue #1 gets a
   comment with the result, which triggers your GitHub notification/email.

Notes on the data:
- For round-trip searches Google returns **outbound** legs only; the price
  is the cheapest round trip that starts with that outbound flight. So
  `outbound_stops` describes only the Friday flight. (Older records have
  `segments`, the outbound leg count, which the page converts.)
- `fast-flights` scrapes Google Flights' public page, so Google can
  rate-limit it or change the format. Failed checks are recorded and
  reported rather than silently skipped.

## Adjusting

- Airports: `FROM_AIRPORT` / `TO_AIRPORT` in `scripts/check_flight_price.py`
  (and the labels in `scripts/build_site.py`).
- Schedule: the `cron` line in `flight-price-tracker.yml` (13:00 UTC; GitHub
  often runs scheduled jobs a few hours late).
