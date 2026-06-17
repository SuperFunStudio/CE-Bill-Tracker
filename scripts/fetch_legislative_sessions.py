"""Generate real legislative session windows for the /beta Legislative Timeline.

Source: the OpenStates monthly Postgres dump (opencivicdata_legislativesession), restored
into the local scratch DB on port 5433 — the SAME bulk dump we used for the historical bill
backfill (see app/ingestion/openstates_pgdump.py). This avoids the rate-limited v3 API
(250/day) entirely and is repeatable: when a newer monthly dump is restored, rerun this.

Writes a static JSON consumed by dashboard-next:
    dashboard-next/src/components/beta/legislative-sessions.json

Run from repo root:
    PYTHONPATH=. ./venv/Scripts/python.exe scripts/fetch_legislative_sessions.py

Caveats baked into the data:
  * For biennium states (CA, NY, NJ, IL, MI, OH, ...) the regular-session row spans the
    FULL two years, so end_date is the end of the biennium, not the annual adjournment.
  * OpenStates does NOT carry procedural cutoffs (crossover / committee deadlines). Those
    remain a separate curated layer in the component (clearly labeled).
"""

import asyncio
import json
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# The restored OpenStates monthly dump (scratch DB on the second local Postgres instance).
DUMP_DSN = "postgresql+asyncpg://postgres:dev@localhost:5433/openstates_dump"

OUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "dashboard-next"
    / "src"
    / "components"
    / "beta"
    / "legislative-sessions.json"
)

# Keep sessions overlapping this window — matches the timeline axis.
WINDOW_START = "2024-12-01"
WINDOW_END = "2026-12-31"

_STATE_RE = re.compile(r"/state:([a-z]{2})/")
_SPECIAL_RE = re.compile(r"special|extraordinary|extra session", re.IGNORECASE)

QUERY = text(
    """
    SELECT jurisdiction_id, identifier, name, classification, start_date, end_date, active
    FROM opencivicdata_legislativesession
    WHERE jurisdiction_id ~ '/state:[a-z]{2}/'
      AND end_date >= :win_start
      AND start_date <= :win_end
      AND start_date <> ''
      AND end_date <> ''
    ORDER BY start_date
    """
)


def _is_special(classification: str, name: str) -> bool:
    return (classification or "").lower() == "special" or bool(_SPECIAL_RE.search(name or ""))


async def main() -> None:
    engine = create_async_engine(DUMP_DSN, echo=False)
    by_state: dict[str, list[dict]] = {}
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(QUERY, {"win_start": WINDOW_START, "win_end": WINDOW_END})).all()
    finally:
        await engine.dispose()

    for r in rows:
        m = _STATE_RE.search(r.jurisdiction_id or "")
        if not m:
            continue
        st = m.group(1).upper()
        by_state.setdefault(st, []).append(
            {
                "start": r.start_date,
                "end": r.end_date,
                "label": r.name or r.identifier or "session",
                "special": _is_special(r.classification, r.name),
                "active": bool(r.active),
            }
        )

    for sessions in by_state.values():
        sessions.sort(key=lambda s: s["start"])

    payload = {
        "_source": "OpenStates monthly Postgres dump (opencivicdata_legislativesession)",
        "_window": {"start": WINDOW_START, "end": WINDOW_END},
        "_note": (
            "Convene/adjourn from OpenStates. Biennium states span the full 2 years "
            "(end_date = end of biennium, not annual adjournment). Procedural cutoffs NOT included."
        ),
        "states": by_state,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    total = sum(len(v) for v in by_state.values())
    print(f"Wrote {OUT_PATH}")
    print(f"  {len(by_state)} states, {total} sessions in window")
    for st in ["CA", "WA", "OR", "NY", "NJ", "MN", "ME", "CO", "MD", "IL"]:
        for s in by_state.get(st, []):
            tag = " [special]" if s["special"] else ""
            print(f"    {st}  {s['start']} -> {s['end']}  {s['label']}{tag}")


if __name__ == "__main__":
    asyncio.run(main())
