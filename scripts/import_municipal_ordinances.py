"""Insert curated US CITY ordinances (deconstruction, C&D diversion, reuse/foodware, bag rules) into the
bills table, attached to municipality nodes in the jurisdiction tree.

Why this exists
---------------
The ordinances usually cited as deconstruction-over-demolition law (Portland, San Antonio, Palo Alto,
Boulder) and the big-city reuse/foodware rules are municipal, so no state/federal source ingests them.
This loads them from the hand-curated data/seed/municipal_ordinances.json (entries whose status or URL
could not be verified sit in _municipal_ordinances_quarantine.json instead).

Shape of a city row
-------------------
region "US", state "<ST>-<CITY>" (e.g. "OR-PORTLAND"), jurisdiction_id -> the "US-OR-PORTLAND"
municipality node. The hyphenated state keeps city ordinances out of every exact-match state filter
(leaderboard, state profile counters, map), and the state profile lists them in their own section by
prefix. The municipality nodes come from US_MUNICIPALITIES in app/geo/jurisdictions.py — run
scripts/backfill_jurisdictions.py first so they exist.

Safety properties (same contract as import_federal_enablers.py)
--------------------------------------------------------------
- Idempotent: stable synthetic openstates_id "muni:<hash(key)>" -> re-runs UPDATE in place.
- Gated: DRY RUN by default. --check-urls validates every source_url over HTTP first.
- No full text: city sources are code pages / program guidance, so rows cite via ai_summary (like
  text-free foreign rows); the weekly link-health job re-verifies source_url.

Run:
    python scripts/import_municipal_ordinances.py --check-urls        # DRY RUN + URL check
    python scripts/import_municipal_ordinances.py --commit --dsn ...  # write rows
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402
from scripts.import_federal_enablers import _parse_date  # noqa: E402
from app.geo.jurisdictions import US_MUNICIPALITIES, jurisdiction_code  # noqa: E402
from app.models import Bill, Jurisdiction  # noqa: E402

SEED = Path(__file__).parent.parent / "data" / "seed" / "municipal_ordinances.json"
_LIVE_BUT_BLOCKED = {401, 403, 405, 406, 429}  # gatekept, not dead


def _synthetic_id(o: dict) -> str:
    return "muni:" + hashlib.sha1(o["key"].encode("utf-8")).hexdigest()[:16]


async def _check_urls(ords: list[dict]) -> dict[str, int | str]:
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    out: dict[str, int | str] = {}
    async with httpx.AsyncClient(headers={"User-Agent": ua}, verify=False) as client:
        sem = asyncio.Semaphore(6)

        async def one(o: dict) -> None:
            async with sem:
                try:
                    r = await client.get(o["source_url"], follow_redirects=True, timeout=30.0)
                    out[o["key"]] = r.status_code
                except Exception as e:  # noqa: BLE001
                    out[o["key"]] = type(e).__name__
        await asyncio.gather(*(one(o) for o in ords))
    return out


def _url_ok(status: int | str) -> bool:
    return isinstance(status, int) and (status < 400 or status in _LIVE_BUT_BLOCKED or status >= 500)


async def main(commit: bool, check_urls: bool, dsn: str | None) -> None:
    ords = json.loads(SEED.read_text(encoding="utf-8"))
    for o in ords:
        sub = f"{o['state']}-{o['city']}"
        if sub not in US_MUNICIPALITIES:
            raise SystemExit(f"{o['key']}: {sub} is not in US_MUNICIPALITIES (app/geo/jurisdictions.py)")
        if len(sub) > 16:
            raise SystemExit(f"{o['key']}: state code {sub!r} exceeds bills.state's 16 chars")

    statuses = await _check_urls(ords) if check_urls else {}
    dead = [k for k, s in statuses.items() if not _url_ok(s)]

    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    inserted = updated = 0
    report: list[str] = []
    async with Session() as db:
        nodes = {j.code: j.id for j in (await db.execute(
            select(Jurisdiction).where(Jurisdiction.level == "municipality"))).scalars()}
        for o in ords:
            if o["key"] in dead:
                report.append(f"  SKIP (dead url {statuses[o['key']]})  {o['key']}")
                continue
            state = f"{o['state']}-{o['city']}"
            jcode = jurisdiction_code("US", state)
            if jcode not in nodes:
                raise SystemExit(f"jurisdiction node {jcode} missing — run scripts/backfill_jurisdictions.py first")
            instrs = o.get("instrument_types") or ["other"]
            values = dict(
                openstates_id=_synthetic_id(o),
                region="US",
                state=state,
                jurisdiction_id=nodes[jcode],
                bill_number=o.get("bill_number"),
                title=o["title"],
                description=o.get("summary"),
                status=o.get("status", "enacted"),
                status_date=_parse_date(o.get("enacted_date")),
                last_action_date=_parse_date(o.get("effective_date") or o.get("enacted_date")),
                effective_date=_parse_date(o.get("effective_date")),
                source_url=o["source_url"],
                ce_relevant=True,
                confidence_score=1.0,
                reviewed=True,  # researcher-curated, source-checked
                material_categories=o.get("material_categories", []),
                instrument_type=instrs[0],
                instrument_types=instrs,
                policy_stance="advances",
                stance_source="heuristic",
                urgency="low",
                ai_summary=o.get("summary"),
            )
            existing = (await db.execute(
                select(Bill).where(Bill.openstates_id == values["openstates_id"]))).scalar_one_or_none()
            if existing is None:
                db.add(Bill(**values))
                inserted += 1
                tag = "INSERT"
            else:
                for k, v in values.items():
                    setattr(existing, k, v)
                updated += 1
                tag = "UPDATE"
            url_note = f"  url={statuses[o['key']]}" if statuses else ""
            report.append(f"  {tag}  {state:16} {instrs[0]:14} {o['title'][:60]}{url_note}")

        if commit:
            await db.commit()
        else:
            await db.rollback()
    await engine.dispose()

    print(f"=== Municipal ordinance import — {'COMMITTED' if commit else 'DRY RUN (no writes)'} ===")
    print(f"  seed ordinances : {len(ords)}")
    print(f"  NEW inserts     : {inserted}")
    print(f"  updated (re-run): {updated}")
    print(f"  skipped (dead)  : {len(dead)}")
    print()
    for line in report:
        print(line)
    if commit:
        print("\n  Next: re-run scripts/backfill_jurisdictions.py to refresh jurisdictions.bill_count.")
    else:
        print("\n  Re-run with --commit to write these rows.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", action="store_true", help="Write rows (default dry run).")
    ap.add_argument("--check-urls", action="store_true", help="HTTP-validate source_url; skip dead ones.")
    ap.add_argument("--dsn", default=None, help="Postgres DSN; defaults to app settings (local).")
    a = ap.parse_args()
    asyncio.run(main(commit=a.commit, check_urls=a.check_urls, dsn=a.dsn))
