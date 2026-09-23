#!/usr/bin/env python3
"""Fetch the round-trip economy price for the upcoming Fri->Sun DFW<->ORD
weekend from Google Flights and append the result to data/history.json.

Also writes data/latest_summary.json (single most recent record, with a
trend vs. the previous successful check) for the notification step.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fast_flights import FlightQuery, Passengers, create_query, get_flights

FROM_AIRPORT = "DFW"
TO_AIRPORT = "ORD"
HISTORY_PATH = Path("data/history.json")
SUMMARY_PATH = Path("data/latest_summary.json")
MAX_HISTORY_ENTRIES = 1000
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 15


def next_weekend() -> tuple[date, date]:
    """Return (friday, sunday) for the closest upcoming Fri->Sun weekend.

    If today is Friday, that weekend is used (same-day departure). If
    today is Saturday or Sunday, this weekend's Friday has already
    passed as a bookable departure date, so we roll forward to *next*
    Friday instead.
    """
    today = date.today()
    weekday = today.weekday()  # Mon=0 ... Fri=4, Sat=5, Sun=6
    days_ahead = (4 - weekday) % 7
    friday = today + timedelta(days=days_ahead)
    sunday = friday + timedelta(days=2)
    return friday, sunday


def fetch_price(friday: date, sunday: date) -> dict:
    query = create_query(
        flights=[
            FlightQuery(date=str(friday), from_airport=FROM_AIRPORT, to_airport=TO_AIRPORT),
            FlightQuery(date=str(sunday), from_airport=TO_AIRPORT, to_airport=FROM_AIRPORT),
        ],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(adults=1),
        currency="USD",
    )

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = get_flights(query)
            if not result:
                raise RuntimeError("No flights returned for this route/date")

            airline_names = {a.code: a.name for a in result.metadata.airlines}
            best = min(result, key=lambda f: f.price)

            return {
                "status": "ok",
                "price": best.price,
                "airlines": [airline_names.get(code, code) for code in best.airlines],
                "segments": len(best.flights),
                "fare_type": best.type,
            }
        except Exception as exc:  # noqa: BLE001 - want to record *any* failure
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS * attempt)

    return {"status": "error", "error": last_error or "Unknown error"}


def load_history() -> list[dict]:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text())
    return []


def describe_trend(current_price: float, previous_price: float) -> str:
    diff = current_price - previous_price
    if diff > 0:
        return f"up ${diff:,.0f} from ${previous_price:,.0f}"
    if diff < 0:
        return f"down ${abs(diff):,.0f} from ${previous_price:,.0f}"
    return "unchanged"


def main() -> None:
    friday, sunday = next_weekend()
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    result = fetch_price(friday, sunday)

    history = load_history()
    previous_ok = next((h for h in reversed(history) if h.get("status") == "ok"), None)

    entry = {
        "checked_at": checked_at,
        "weekend_start": str(friday),
        "weekend_end": str(sunday),
        "from_airport": FROM_AIRPORT,
        "to_airport": TO_AIRPORT,
        "currency": "USD",
        **result,
    }
    history.append(entry)
    history = history[-MAX_HISTORY_ENTRIES:]

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2) + "\n")

    trend = None
    if entry["status"] == "ok" and previous_ok is not None:
        trend = describe_trend(entry["price"], previous_ok["price"])

    summary = {**entry, "trend": trend}
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n")

    if entry["status"] != "ok":
        print(f"Flight price check failed: {entry.get('error')}", file=sys.stderr)


if __name__ == "__main__":
    main()
