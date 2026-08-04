"""Gap-A enabler recall — re-judge `ce_relevant=false` bills that carry an ENABLER signal
(recycled-content procurement, funding/incentives, right-to-repair, deposit/fee) and flip the
true circular-economy enablers back into scope.

Why (see docs/GAP_A_ENABLER_RECALL_PLAN.md)
-------------------------------------------
Enabler instruments are under-represented because the ingest classifier historically, confidently,
excluded financial/procurement/repair/deposit levers (a scope-DEFINITION problem — see the
2026-07-30 manual `ce_relevant=false` review). Many were also text-starved at classify time. This
tools that manual pass: a keyword net narrows the `ce_false` pool, then the SAME Haiku classifier
re-judges each candidate WITH its stored full-text excerpt (the fix for the starvation root cause).

Method — net -> judge -> gated apply (deterministic net kept auditable in Python, like
scripts/backfill_adjacency.py):
  1. Prefilter `ce_relevant=false` rows by a cheap ILIKE superset, then apply the precise compound
     NETS in Python (the deposit net requires a beverage/container context so "legal deposit",
     "deposit account", "subsidy repayment" etc. don't match).
  2. Re-judge each candidate with HaikuClassifier, passing title + summary + the bill_texts excerpt.
  3. Band by the judge: is_ce_relevant=true & confidence >= HIGH -> AUTO-APPLY (reviewed=true);
     is_ce_relevant=true & MID <= confidence < HIGH -> apply but needs_review=true; else DROP.
     Applied rows get instrument_type/instrument_types from the judge; `adjacency` stays NULL — these
     are CORE circular-economy bills wrongly excluded, not adjacent-scope (unlike transboundary).
  4. Every change -> classification_changes (old/new snapshot) under run_id `enabler-recall-<date>`;
     one-query undo. DEFAULTS TO DRY RUN.

Run:
    python scripts/recall_enablers.py                     # dry run (local)
    python scripts/recall_enablers.py --commit
    python scripts/recall_enablers.py --dsn "postgresql://...@127.0.0.1:55432/signalscout"   # prod tunnel, dry run
    python scripts/recall_enablers.py --commit --dsn "..."
    python scripts/recall_enablers.py --limit 40          # cap candidates (debugging / cost)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402
from app.classification.haiku_classifier import HaikuClassifier  # noqa: E402

HIGH = 0.75   # auto-apply (reviewed=true)
MID = 0.50    # apply but flag needs_review=true
CONCURRENCY = 6

# --- The enabler nets (precise; applied in Python) -------------------------------------------------
_RECYCLED_CONTENT = re.compile(
    r"(recycled|recovered|post-?consumer)\W+(?:\w+\W+){0,3}?(content|material)"
    r"\W+(?:\w+\W+){0,8}?(procure|purchas|buy|minimum|standard|mandate|require)",
    re.IGNORECASE)
_INCENTIVES = re.compile(
    r"(grant|rebate|tax\s+credit|tax\s+deduction|subsid|revolving\s+fund|low-interest\s+loan|voucher)"
    r"\W+(?:\w+\W+){0,8}?(recycl|compost|reuse|re-use|remanufactur|refurbish|repair|circular|"
    r"organics|takeback|take-back|stewardship)",
    re.IGNORECASE)
_REPAIR = re.compile(r"right\s+to\s+repair|repairab|spare\s+parts|replacement\s+parts", re.IGNORECASE)
# Deposit net TIGHTENED: a beverage/container context AND a return/refund/redemption/deposit token,
# or an unambiguous standalone phrase. Excludes "legal deposit", "deposit account/insurance", etc.
_DEPOSIT_CTX = r"beverage\s+container|drink(?:ing)?\s+(?:container|vessel|bottle)|bottle|can|packaging"
_DEPOSIT_LEVER = r"deposit[-\s]?return|container\s+deposit|redemption\s+value|refund\s+value|advance\s+disposal\s+fee|bottle\s+bill"
_DEPOSIT = re.compile(
    rf"bottle\s+bill|container\s+deposit|deposit[-\s]?return\s+(?:system|scheme|program)|advance\s+disposal\s+fee"
    rf"|(?:{_DEPOSIT_CTX})\W+(?:\w+\W+){{0,6}}?(?:{_DEPOSIT_LEVER})"
    rf"|(?:{_DEPOSIT_LEVER})\W+(?:\w+\W+){{0,6}}?(?:{_DEPOSIT_CTX})",
    re.IGNORECASE)

NETS = {
    "recycled_content": _RECYCLED_CONTENT,
    "incentives": _INCENTIVES,
    "right_to_repair": _REPAIR,
    "deposit_return": _DEPOSIT,
}
# A cheap SQL superset so we don't scan the whole ce_false corpus in Python.
_ILIKE_TOKENS = ["recycled", "recovered", "post-consumer", "grant", "rebate", "tax credit",
                 "subsid", "revolving fund", "repair", "spare parts", "replacement parts",
                 "bottle bill", "container deposit", "deposit return", "beverage container",
                 "redemption value", "advance disposal fee"]


def _blob(r) -> str:
    return f"{r['title'] or ''}\n{r['ai_summary'] or ''}\n{r['description'] or ''}"


def _net_families(blob: str) -> list[str]:
    return [fam for fam, rx in NETS.items() if rx.search(blob)]


def _new_instrument_types(primary: str, judged: list, existing: list | None) -> list[str]:
    out = [primary]
    for src in (judged or []), (existing or []):
        for it in src:
            if isinstance(it, str) and it and it not in out:
                out.append(it)
    return out


def _dump(obj) -> str:
    return json.dumps(obj)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=None, help="Postgres DSN; defaults to app settings (local).")
    ap.add_argument("--commit", action="store_true", help="Write changes (default is dry run).")
    ap.add_argument("--limit", type=int, default=None, help="Cap candidates re-judged (cost/debug).")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    run_id = f"enabler-recall-{date.today().isoformat()}"

    ilike = " OR ".join(
        [f"b.title ILIKE :t{i} OR coalesce(b.ai_summary,'') ILIKE :t{i} OR coalesce(b.description,'') ILIKE :t{i}"
         for i in range(len(_ILIKE_TOKENS))])
    params = {f"t{i}": f"%{tok}%" for i, tok in enumerate(_ILIKE_TOKENS)}
    sql = (
        "SELECT b.id, b.region, b.state, b.bill_number, b.title, b.description, b.ai_summary, b.status, "
        "       b.ce_relevant, b.confidence_score, b.instrument_type, b.instrument_types, b.needs_review, "
        "       b.adjacency, left(bt.text, 2000) AS excerpt "
        "FROM bills b LEFT JOIN bill_texts bt ON bt.bill_id = b.id "
        f"WHERE b.ce_relevant = false AND ({ilike}) "
        "ORDER BY b.region, b.state, b.bill_number"
    )
    async with Session() as db:
        rows = list((await db.execute(text(sql), params)).mappings().all())

    # Precise net in Python.
    cands = []
    for r in rows:
        fams = _net_families(_blob(r))
        if fams:
            cands.append((r, fams))
    if args.limit:
        cands = cands[:args.limit]

    print(f"Prefilter {len(rows)} ce_false rows -> {len(cands)} match the enabler nets. Re-judging with Haiku...\n")
    if not cands:
        print("Nothing to judge.")
        await engine.dispose()
        return

    clf = HaikuClassifier()
    sem = asyncio.Semaphore(CONCURRENCY)

    async def judge(item):
        r, fams = item
        async with sem:
            try:
                res = await clf.classify(
                    state=r["state"] or "", bill_number=r["bill_number"] or "",
                    title=r["title"] or "", description=r["ai_summary"] or r["description"] or "",
                    text_excerpt=r["excerpt"] or "", region=r["region"] or "US")
                return (r, fams, res)
            except Exception as e:  # noqa: BLE001
                print(f"  JUDGE-FAIL {r['region']} {r['bill_number']}: {type(e).__name__}")
                return (r, fams, None)

    judged = await asyncio.gather(*(judge(c) for c in cands))

    auto, review, drop = [], [], []
    for r, fams, res in judged:
        if res is None or not res.is_ce_relevant or res.confidence < MID:
            drop.append((r, fams, res))
        elif res.confidence >= HIGH:
            auto.append((r, fams, res))
        else:
            review.append((r, fams, res))

    def _show(bucket, tag):
        print(f"\n=== {tag}: {len(bucket)} ===")
        for r, fams, res in bucket[:60]:
            inst = res.instrument_type if res else "-"
            conf = f"{res.confidence:.2f}" if res else "-"
            print(f"  {(r['region'] or ''):3}{(r['state'] or ''):4}{(r['bill_number'] or ''):13} "
                  f"conf={conf} -> {inst:16} net={'+'.join(fams):22} {(r['title'] or '')[:52]}")

    _show(auto, "AUTO-APPLY (ce_relevant=true, reviewed=true)")
    _show(review, "NEEDS_REVIEW (ce_relevant=true, needs_review=true)")
    print(f"\n=== DROPPED (judge said out-of-scope / low-confidence): {len(drop)} ===")
    by_region = Counter((r["region"] or "?") for r, _, _ in auto + review)
    by_inst = Counter((res.instrument_type for _, _, res in auto + review if res))
    print(f"\nAccepted by region: {dict(by_region)}")
    print(f"Accepted by instrument: {dict(by_inst)}")
    print(f"Totals: auto={len(auto)}  needs_review={len(review)}  dropped={len(drop)}  run_id={run_id}")

    if not args.commit:
        print("\n(dry run — re-run with --commit to apply auto + needs_review flips.)")
        await engine.dispose()
        return

    now = datetime.now(timezone.utc)
    applied = 0
    async with Session() as db:
        for bucket, reviewed_flag, needs_review_flag in ((auto, True, False), (review, False, True)):
            for r, fams, res in bucket:
                primary = res.instrument_type
                new_types = _new_instrument_types(primary, res.instrument_types, r["instrument_types"])
                old = {"ce_relevant": r["ce_relevant"], "confidence_score": r["confidence_score"],
                       "instrument_type": r["instrument_type"], "instrument_types": r["instrument_types"],
                       "needs_review": r["needs_review"], "adjacency": r["adjacency"]}
                new = {"ce_relevant": True, "confidence_score": res.confidence,
                       "instrument_type": primary, "instrument_types": new_types,
                       "needs_review": needs_review_flag, "adjacency": r["adjacency"]}
                await db.execute(text(
                    "UPDATE bills SET ce_relevant = true, confidence_score = :conf, "
                    "instrument_type = :inst, instrument_types = CAST(:its AS jsonb), "
                    "reviewed = :rev, needs_review = :nr, updated_at = now() WHERE id = :id"),
                    {"conf": res.confidence, "inst": primary, "its": _dump(new_types),
                     "rev": reviewed_flag, "nr": needs_review_flag, "id": r["id"]})
                await db.execute(text(
                    "INSERT INTO classification_changes (bill_id, run_id, old_value, new_value, created_at) "
                    "VALUES (:bid, :rid, CAST(:old AS jsonb), CAST(:new AS jsonb), :ts)"),
                    {"bid": r["id"], "rid": run_id, "old": _dump(old), "new": _dump(new), "ts": now})
                applied += 1
        await db.commit()

    print(f"\nAPPLIED {applied} flips ({len(auto)} auto + {len(review)} needs_review). Audit run_id={run_id}.")
    print(f"Undo: restore old_value for classification_changes WHERE run_id='{run_id}', then delete those rows.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
