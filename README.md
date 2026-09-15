# Flight Price Tracker — DFW ⇄ ORD

A GitHub Action that checks the round-trip economy price for the next
upcoming Friday → Sunday weekend flying Dallas/Fort Worth (DFW) ⇄ Chicago
O'Hare (ORD), publishes the history to a GitHub Pages site, and posts a
GitHub Issue update (which triggers your normal GitHub
notifications/email) with every check.

## How it works

- `.github/workflows/flight-price-tracker.yml` runs daily on a schedule
  (`workflow_dispatch` is also enabled for manual runs).
- `scripts/check_flight_price.py` computes the nearest upcoming Friday and
  Sunday, queries Google Flights (via the [`fast-flights`](https://pypi.org/project/fast-flights/)
  library — no API key required), and appends the result to
  `data/history.json`.
- `scripts/build_site.py` renders `data/history.json` into `docs/index.html`
  (a price chart + full history table).
- The workflow commits the updated data/site back to the branch, then
  creates/updates a GitHub Issue titled **"✈️ DFW ⇄ ORD Weekend Flight
  Price Tracker"** and adds a comment with the latest result — this is
  what generates your GitHub notification/email.

## One-time setup (after merging to your default branch)

1. **Merge this branch into `main`.** Scheduled (`cron`) workflows only
   fire from the repository's default branch, so the daily check won't
   run until this is merged.
2. **Enable GitHub Pages:** repo Settings → Pages → Source: "Deploy from a
   branch" → Branch: `main`, folder: `/docs` → Save. The site will be at
   `https://<your-username>.github.io/<repo>/`.
3. **⚠️ Private repo caveat:** this repository is currently **private**.
   GitHub Pages for private repos requires a GitHub Pro/Team/Enterprise
   plan — on the free plan, Pages won't publish. Either make the repo
   public, upgrade your plan, or skip Pages and just rely on the GitHub
   Issue updates (the data is still tracked in `data/history.json` and
   `docs/index.html` either way, you'd just view it by opening the file
   in the repo instead of a live URL).
4. **Notifications:** make sure "Issues" notifications are enabled for
   this repo under your GitHub notification settings (Watch the repo, or
   at minimum enable notifications for issues you're @ mentioned in / the
   labels tab). The workflow both creates the issue and comments on it, so
   you'll get one email/notification per day.

## Adjusting things

- **Airports:** change `FROM_AIRPORT` / `TO_AIRPORT` in
  `scripts/check_flight_price.py`.
- **Schedule:** edit the `cron` line in the workflow (currently
  `0 13 * * *`, i.e. daily at 13:00 UTC / ~8am Central).
- **How far ahead it looks:** `next_weekend()` in
  `scripts/check_flight_price.py` always targets the *closest* upcoming
  Fri→Sun weekend. To track multiple weekends at once, that function and
  the fetch loop would need to be extended to loop over several weekends.

## Known limitations

- `fast-flights` works by parsing Google Flights' public search page —
  there's no official free API for this. Google occasionally
  rate-limits or blocks automated requests, especially from shared
  cloud/datacenter IP ranges like GitHub Actions runners. The script
  retries a few times on failure, and failed checks are still recorded
  (visible on the Pages site and in the issue) rather than failing
  silently. If checks start failing consistently, this is the most
  likely cause.
- Price shown is for 1 adult, economy, and reflects whatever Google
  Flights returns as the top-priced result set at query time — it's a
  spot check, not a guaranteed bookable fare.
