# aiapps

Small self-hosted apps, published with GitHub Pages at
`https://chdinesh1089.github.io/claude-playground/`.

| URL path | What |
|---|---|
| `/` | Landing page listing every app (generated) |
| `/aiapps/flight-price-tracker/` | DFW ⇄ ORD weekend fare tracker (generated daily) |
| `/aiapps/tmux-cheatsheet/` | tmux cheat sheet (static) |
| `/aiapps/paper-plane/` | *The Paper Plane*, a one-minute story animated in three.js (static) |
| `/aiapps/flappy-3d/` | *Flap 3D*, a glossy 3D flappy-bird-style game (static) |

## How the site is laid out

Pages serves the **repo root** of `main`, so repo paths map 1:1 to URLs:
`aiapps/<slug>/index.html` → `/aiapps/<slug>/`. `.nojekyll` turns off
Jekyll so files are served exactly as committed.

**To add an app:** commit a self-contained `aiapps/<slug>/index.html`.
`publish-site.yml` then regenerates the landing page (`index.html`), using
the page's `<title>` and optional `<meta name="description">` for the
listing. You don't need to register it anywhere.

## The Paper Plane

`aiapps/paper-plane/index.html` is a self-contained three.js animation. Every
object is built in code (no model or image files), and the whole scene is a
pure function of one timeline value, so the scrubber can jump anywhere.

- **Look:** physically based sky with sun position by time of day, image-based
  lighting captured from that sky, soft sun shadows, ACES tone mapping, bloom,
  reflective lake, per-pixel farmland shader, and night city lights that come on
  in a wave.
- **Motion:** the flight path is a clamped C2 cubic spline in time, so speed and
  acceleration never jump; the plane banks from its real lateral acceleration.
- **Smoothness:** render resolution adapts to the device's frame rate; city
  geometry is merged (about 100–150 draw calls per frame); shaders are compiled
  behind the title card.
- `aiapps/lib/three-bundle.min.js` (shared by both 3D apps) is three.js r186 (MIT) plus the Sky, post-processing and
  BufferGeometryUtils add-ons, bundled and minified with esbuild so the page has
  no CDN dependency.
- Keyboard: Space play/pause, ←/→ skip 5 s, R restart. Honors
  `prefers-reduced-motion` (no camera drift or turbulence shake, softer lightning).

## Flap 3D

`aiapps/flappy-3d/index.html`: tap, click, Space, ↑ or W to flap; P pauses.

- Fixed 120 Hz physics with interpolated rendering, so it plays the same at any
  frame rate. Speed rises, gaps tighten, and from 15 points some pipes slide.
- Same rendering pipeline as The Paper Plane (sky, image-based lighting,
  shadows, bloom, adaptive resolution); the sky runs from morning to night as
  the score climbs.
- Feather puffs, score rings, crash flash/shake/slow-mo (off with
  `prefers-reduced-motion`), synthesized WebAudio sound with a mute button.
- Best score and mute are kept in `localStorage`; medals at 10/20/30/40.
- `window.game` exposes read-only state for automated tests.

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
