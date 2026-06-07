"""Refresh stale bill statuses from LegiScan (free tier).

Bills imported from the OpenStates dump often carry a stale status — e.g. a law that
was signed shows as `introduced` because the dump's latest action predates enactment.
This pulls authoritative status from LegiScan's getMasterList (per state, per session),
matches to local bills by (state, normalized bill number, reference year), and ADVANCES
the stored status when LegiScan shows further progress.

Advance-only: never moves a bill backward (e.g. enacted -> introduced). Safe to re-run.

Caveats it can't fix (reported as "no match"/"not advanced"):
  - Omnibus enactments: a named bill (e.g. MN SF1598) whose provisions were enacted
    inside a different omnibus bill stays `introduced` in LegiScan too.
  - Bills whose number/session doesn't line up with LegiScan's record.

Usage (LegiScan key read from settings/.env):
    python scripts/refresh_status_legiscan.py --states OR,WA,NY,CO,CA,MN,NV,MA --dry-run
    python scripts/refresh_status_legiscan.py --states OR,WA,NY,CO,CA,MN,NV,MA      # apply
Target the local DB by default; pass --dsn to point elsewhere.
"""
import argparse
import asyncio
import re
import sys
from datetime import date, datetime
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.legiscan import LegiScanClient  # noqa: E402

# LegiScan progress codes -> our canonical status. Verified empirically against real data
# (code 4 = "Secretary of State / Chapter N" = signed into law). NOTE this is the CORRECT
# mapping; app/ingestion/coordinator._legiscan_status_map is stale/wrong (it maps 5->enacted).
LEGISCAN_STATUS = {
    1: "introduced",
    2: "passed_chamber",   # engrossed (passed one chamber)
    3: "passed",           # enrolled (passed both, awaiting signature)
    4: "enacted",          # passed & chaptered / signed
    5: "vetoed",
    6: "failed",
}
# Rank for advance-only comparison. Terminal states (enacted/vetoed/failed) outrank progress.
RANK = {
    None: -1, "": -1,
    "introduced": 0, "in_committee": 1, "passed_chamber": 2, "passed": 3,
    "failed": 4, "vetoed": 4, "enacted": 5,
}
MIN_YEAR = 2019  # ignore sessions that ended before this


def norm_number(num: str | None) -> str:
    """Normalize a bill number for matching: uppercase, strip non-alphanumerics."""
    return re.sub(r"[^A-Z0-9]", "", (num or "").upper())


def parse_date(s: str | None) -> date | None:
    """LegiScan status_date is a 'YYYY-MM-DD' string (or empty/0000-00-00)."""
    if not s or s.startswith("0000"):
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--states", required=True, help="Comma-separated state codes (e.g. OR,WA,NY).")
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--dry-run", action="store_true", help="Report proposed changes without writing.")
    args = ap.parse_args()

    states = [s.strip().upper() for s in args.states.split(",") if s.strip()]
    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url

    conn = await asyncpg.connect(dsn)
    changes: list[dict] = []
    no_match = 0
    try:
        async with LegiScanClient() as ls:
            for state in states:
                local = await conn.fetch(
                    "SELECT id, bill_number, status, status_date, last_action_date "
                    "FROM bills WHERE state = $1 AND bill_number IS NOT NULL",
                    state,
                )
                if not local:
                    continue

                sessions = await ls.get_session_list(state)
                sessions = [s for s in sessions if int(s.get("year_end", 0)) >= MIN_YEAR]
                # session_id -> {norm_number -> entry}; plus year ranges for disambiguation
                masters: dict[int, dict[str, dict]] = {}
                yranges: dict[int, tuple[int, int]] = {}
                for s in sessions:
                    sid = int(s["session_id"])
                    ml = await ls.get_master_list(state, sid)
                    masters[sid] = {}
                    for e in ml.values():
                        masters[sid][norm_number(e.get("number"))] = e
                    yranges[sid] = (int(s.get("year_start", 0)), int(s.get("year_end", 0)))

                for b in local:
                    nn = norm_number(b["bill_number"])
                    ref = b["status_date"] or b["last_action_date"]
                    ref_year = ref.year if ref else None
                    if ref_year is None:
                        no_match += 1
                        continue
                    # HARD restrict to sessions whose year range contains the bill's reference
                    # year — states reuse bill numbers every session, so cross-session matches
                    # are false positives (e.g. CA AB-2 exists in 2019/2021/2023/2025).
                    cand_sids = [
                        sid for sid in masters
                        if yranges[sid][0] <= ref_year <= yranges[sid][1]
                    ]
                    best = None
                    # Some states prefix the session year into the number (CO "HB-23-1011"
                    # = HB 1011 of the 2023 session); LegiScan uses the bare "HB1011".
                    prefix_m = re.match(r"^([A-Z]+)(\d{2})(\d+)$", nn)
                    for sid in cand_sids:
                        keys = [nn]
                        if prefix_m and int(prefix_m.group(2)) in (
                            yranges[sid][0] % 100, yranges[sid][1] % 100
                        ):
                            keys.append(prefix_m.group(1) + prefix_m.group(3))
                        e = next((masters[sid][k] for k in keys if k in masters[sid]), None)
                        if not e:
                            continue
                        cand = LEGISCAN_STATUS.get(e.get("status"))
                        if best is None or RANK.get(cand, -1) > RANK.get(best[0], -1):
                            best = (cand, e)
                    if best is None:
                        no_match += 1
                        continue
                    new_status, entry = best
                    if RANK.get(new_status, -1) > RANK.get(b["status"], -1):
                        changes.append({
                            "id": b["id"], "state": state, "number": b["bill_number"],
                            "old": b["status"], "new": new_status,
                            "status_date": parse_date(entry.get("status_date")), "url": entry.get("url"),
                        })

        changes.sort(key=lambda c: (c["state"], -RANK.get(c["new"], -1)))
        print(f"{len(changes)} status changes proposed ({no_match} local bills had no LegiScan match)\n")
        enacted = [c for c in changes if c["new"] == "enacted"]
        print(f"  -> {len(enacted)} would become ENACTED")
        for c in changes:
            print(f"  {c['state']} {c['number']:12s} {c['old'] or '(none)':14s} -> {c['new']:14s} {c['status_date'] or ''}")

        if args.dry_run:
            print("\n(dry run — no changes written)")
            return

        # Only status/status_date are updated; source_url is left alone so the authoritative
        # OpenStates/official state URLs already on the rows are preserved (LegiScan's url is a
        # legiscan.com link — kept in the dry-run report for reference only).
        async with conn.transaction():
            for c in changes:
                await conn.execute(
                    "UPDATE bills SET status=$1, status_date=COALESCE($2, status_date), "
                    "updated_at=now() WHERE id=$3",
                    c["new"], c["status_date"], c["id"],
                )
        print(f"\napplied: {len(changes)} rows updated")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
