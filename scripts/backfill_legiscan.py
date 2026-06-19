"""Attach legiscan_bill_id to EPR bills for ongoing change-tracking — with a confidence guard.

Why the guard
-------------
LegiScan's getSearch is a full-text relevance search, NOT a bill-number lookup. Querying
"SB 54" in CA returns budget bills at relevance 100 and buries the real SB 54. Blindly
taking results[0] (the old behaviour) mis-assigns wholesale. Instead we:
  1. scope the search to the bill's enactment YEAR (getSearch year=YYYY),
  2. paginate a few pages and FILTER the result set for an EXACT normalized bill_number
     match in the right state,
  3. tie-break by closeness of last_action_date to the seeded enacted year,
  4. only auto-assign when a same-number, same-state match lands within +/-1 year.

Bills with no bill_number in the seed (old program-style entries, e.g. "Oregon E-Cycles")
cannot be reverse-looked-up from a program name reliably, so they are reported as
needs-manual-bill-number, never guessed.

The free LegiScan tier (30k queries/month) easily covers this: ~1-3 queries per bill.
getMasterList (bulk) stays disabled — only getSearch is used here.

Run:
    python scripts/backfill_legiscan.py                  # DRY RUN — print the match table
    python scripts/backfill_legiscan.py --apply          # write legiscan_bill_id (confident only)
    python scripts/backfill_legiscan.py --historical-only # restrict to hist:* seed rows
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

MAX_PAGES = 3  # getSearch returns 50/page; 3 pages = 150 candidates, plenty to find an exact #


def _canon(num: str | None) -> str:
    """Base-form bill number for exact comparison, tolerant of formatting variants:
    'SB-54'->'SB54', 'S-9100'/'S09100'->'S9100' (drop leading zeros),
    'S-5027C'->'S5027' (drop trailing suffix letters). Returns leading-alpha + digit-run.
    """
    if not num:
        return ""
    raw = num.upper().replace("-", "").replace(" ", "").replace(".", "")
    m = re.match(r"^([A-Z]+)0*(\d+)", raw)
    return f"{m.group(1)}{m.group(2)}" if m else raw


def _seed_year(bill) -> int | None:
    d = bill.status_date or bill.last_action_date
    return d.year if d else None


async def _gather_candidates(legiscan, query, state, year):
    out = []
    use_year = year
    for page in range(1, MAX_PAGES + 1):
        try:
            res = await legiscan.search(query, state=state, page=page, year=use_year)
        except Exception as e:  # noqa: BLE001
            # LegiScan's search index starts ~2010; older years raise "Invalid year".
            # Fall back to an unscoped (all-years) search once, then continue.
            if "Invalid year" in str(e) and use_year is not None:
                use_year = None
                try:
                    res = await legiscan.search(query, state=state, page=page, year=None)
                except Exception as e2:  # noqa: BLE001
                    print(f"    search error p{page}: {e2}")
                    break
            else:
                print(f"    search error p{page}: {e}")
                break
        out.extend(res)
        if len(res) < 50:
            break
    return out


def _best_match(bill, candidates):
    """Return (bill_id, confidence, candidate) or (None, reason, None)."""
    target = _canon(bill.bill_number)
    if not target:
        return None, "no_billnum_in_seed", None
    same = [c for c in candidates
            if (c.get("state") == bill.state) and _canon(c.get("bill_number")) == target]
    if not same:
        return None, "no_exact_match", None
    syear = _seed_year(bill)

    def _yr(c):
        d = (c.get("last_action_date") or "")[:4]
        return int(d) if d.isdigit() else 0

    same.sort(key=lambda c: abs((_yr(c) or 0) - (syear or 0)))
    best = same[0]
    diff = abs((_yr(best) or 0) - (syear or 0)) if syear else 99
    conf = "high" if diff <= 1 else "year_off"
    return best.get("bill_id"), conf, best


async def main(apply: bool, historical_only: bool):
    from sqlalchemy import select

    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.ingestion.legiscan import LegiScanClient
    from app.models import Bill

    if not settings.legiscan_api_key:
        print("No legiscan_api_key configured (.env). Aborting.")
        return

    async with AsyncSessionLocal() as db:
        q = select(Bill).where(Bill.legiscan_bill_id.is_(None), Bill.ce_relevant == True)  # noqa: E712
        if historical_only:
            q = q.where(Bill.openstates_id.like("hist:%"))
        bills = (await db.execute(q)).scalars().all()
        print(f"{len(bills)} EPR bills missing legiscan_bill_id"
              f"{' (historical only)' if historical_only else ''}\n")

        # legiscan_bill_id is UNIQUE — one LegiScan bill maps to one row. Some laws appear
        # under two categories (e.g. CA SB 212 = pharmaceuticals + medical sharps), so track
        # ids already claimed (in the DB or earlier in this run) and skip dupes.
        claimed = set(
            (await db.execute(
                select(Bill.legiscan_bill_id).where(Bill.legiscan_bill_id.isnot(None))
            )).scalars().all()
        )

        assigned = year_off = no_match = no_num = dup_id = 0
        async with LegiScanClient() as legiscan:
            for b in bills:
                year = _seed_year(b)
                if not b.bill_number:
                    no_num += 1
                    print(f"  {b.state:2} {'(no bill#)':10} {str(year):4}  SKIP  {(b.title or '')[:50]}")
                    continue
                # Query on the human bill number; exact filtering does the real work.
                query = b.bill_number.replace("-", " ")
                cands = await _gather_candidates(legiscan, query, b.state, year)
                bill_id, conf, cand = _best_match(b, cands)
                if bill_id and int(bill_id) in claimed:
                    dup_id += 1
                    print(f"  {b.state:2} {b.bill_number:10} {str(year):4}  DUP   -> {bill_id} already claimed (same law in another category) — skip")
                elif bill_id and conf == "high":
                    assigned += 1
                    claimed.add(int(bill_id))
                    if apply:
                        b.legiscan_bill_id = int(bill_id)
                    print(f"  {b.state:2} {b.bill_number:10} {str(year):4}  OK   -> {bill_id}  {(cand.get('title') or '')[:40]}")
                elif bill_id and conf == "year_off":
                    year_off += 1
                    print(f"  {b.state:2} {b.bill_number:10} {str(year):4}  ?    -> {bill_id} (yr {cand.get('last_action_date','')[:4]}) REVIEW {(cand.get('title') or '')[:32]}")
                else:
                    no_match += 1
                    print(f"  {b.state:2} {b.bill_number:10} {str(year):4}  MISS  no exact #/state match in {len(cands)} candidates")

        if apply:
            await db.commit()
        else:
            await db.rollback()

    mode = "APPLIED" if apply else "DRY RUN (no writes)"
    print(f"\n=== {mode} ===")
    print(f"  confident assigns      : {assigned}{' (written)' if apply else ''}")
    print(f"  dup id (other category): {dup_id}  (same law already wired under another category)")
    print(f"  year-off (needs review): {year_off}  (not written; re-check, then widen guard if correct)")
    print(f"  no exact match         : {no_match}")
    print(f"  no bill# in seed        : {no_num}  (add bill numbers to _historical_raw.json to enable)")
    if not apply:
        print("\n  Re-run with --apply to write the confident assigns.")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv, historical_only="--historical-only" in sys.argv))
