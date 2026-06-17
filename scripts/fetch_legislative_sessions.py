"""Fetch real legislative session windows from OpenStates jurisdiction metadata.

Replaces the hand-entered guesses in the /beta Legislative Timeline prototype with
authoritative convene/adjourn dates. OpenStates carries `legislative_sessions` (with
start_date/end_date) per jurisdiction on the /jurisdictions endpoint — free, same API
key we already use for bill ingestion.

Writes a static JSON consumed by dashboard-next:
    dashboard-next/src/components/beta/legislative-sessions.json

This is a one-time/occasional generator (sessions change rarely), not a live endpoint.
Run from repo root:  ./venv/Scripts/python.exe scripts/fetch_legislative_sessions.py

Note: OpenStates does NOT carry procedural cutoffs (crossover / committee deadlines).
Those remain a separate curated layer in the component (clearly labeled).
"""

import asyncio
import json
import re
from pathlib import Path

import httpx

from app.config import settings

BASE_URL = "https://v3.openstates.org"
OUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "dashboard-next"
    / "src"
    / "components"
    / "beta"
    / "legislative-sessions.json"
)

# Only keep sessions that overlap this window — matches the timeline axis.
WINDOW_START = "2024-12-01"
WINDOW_END = "2026-12-31"

_STATE_FROM_OCD = re.compile(r"state:([a-z]{2})")


def _overlaps(start: str, end: str) -> bool:
    """True if [start, end] intersects the timeline window. Missing dates fail open
    only when the session has at least one date inside the window."""
    if not start and not end:
        return False
    s = start or end
    e = end or start
    return s <= WINDOW_END and e >= WINDOW_START


async def fetch_jurisdictions() -> list[dict]:
    """List all state jurisdictions with their legislative_sessions included."""
    results: list[dict] = []
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"X-API-KEY": settings.open_states_api_key},
        timeout=30.0,
    ) as client:
        page = 1
        while True:
            body = None
            for attempt in range(6):
                resp = await client.get(
                    "/jurisdictions",
                    params={
                        "classification": "state",
                        "include": ["legislative_sessions"],
                        "page": page,
                        "per_page": 52,
                    },
                )
                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", 0)) or 6.0 * (attempt + 1)
                    print(f"  429 on page {page}, backing off {wait:.0f}s (attempt {attempt + 1})")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                body = resp.json()
                break
            if body is None:
                raise RuntimeError(f"Gave up on page {page} after repeated 429s")
            results.extend(body.get("results", []))
            pagination = body.get("pagination", {})
            if page >= pagination.get("max_page", page):
                break
            page += 1
    return results


def build_calendar(jurisdictions: list[dict]) -> dict[str, list[dict]]:
    """Map 2-letter state code -> list of in-window sessions (sorted by start)."""
    out: dict[str, list[dict]] = {}
    for j in jurisdictions:
        m = _STATE_FROM_OCD.search(j.get("id", ""))
        if not m:
            continue
        state = m.group(1).upper()
        sessions = []
        for s in j.get("legislative_sessions", []):
            start = s.get("start_date") or ""
            end = s.get("end_date") or ""
            if not _overlaps(start, end):
                continue
            sessions.append(
                {
                    "start": start,
                    "end": end,
                    "label": s.get("name") or s.get("identifier") or "session",
                    "classification": s.get("classification") or "",
                }
            )
        if sessions:
            sessions.sort(key=lambda x: x["start"] or x["end"])
            out[state] = sessions
    return out


async def main() -> None:
    jurisdictions = await fetch_jurisdictions()
    calendar = build_calendar(jurisdictions)
    payload = {
        "_source": "OpenStates v3 /jurisdictions legislative_sessions",
        "_window": {"start": WINDOW_START, "end": WINDOW_END},
        "_note": "Convene/adjourn from OpenStates. Procedural cutoffs are NOT included here.",
        "states": calendar,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    total = sum(len(v) for v in calendar.values())
    missing_end = sum(
        1 for v in calendar.values() for s in v if not s["end"]
    )
    print(f"Wrote {OUT_PATH}")
    print(f"  {len(calendar)} states, {total} sessions in window")
    print(f"  sessions missing an end_date: {missing_end}")
    # Spot-check the states the prototype currently shows.
    for st in ["CA", "WA", "OR", "NY", "NJ", "MN", "ME", "CO", "MD", "IL"]:
        for s in calendar.get(st, []):
            print(f"    {st}  {s['start'] or '????-??-??'} -> {s['end'] or '????-??-??'}  {s['label']}")


if __name__ == "__main__":
    asyncio.run(main())
