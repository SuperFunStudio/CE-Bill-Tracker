"""Reconcile our bills.status 'enacted' against the OpenStates dump's normalized enacting actions.

Our daily incremental misses some governor signatures (bills stuck at 'introduced' though signed);
the dump's action classification (executive-signature / became-law) catches those. Conversely we hold
older/historical/LegiScan enactments the dump has no classified signature action for. This reports
both directions, recomputes the advancing-CE passage rate + per-state gap under a RECONCILED flag,
and (only with --apply) writes the dump-confirmed enactments back into bills.status.

Requires the restored dump on :5433 (see app/ingestion/dump_analytics.py) and data/analysis/
passage_rate_baseline.json from compute_dump_baseline.py.

Usage:
    python scripts/reconcile_enacted.py                 # dry-run report + corrected gap (DEFAULT)
    python scripts/reconcile_enacted.py --apply         # write corrections into bills.status (local!)
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump-dsn", default="postgresql://postgres:dev@localhost:5433/openstates_dump")
    parser.add_argument("--baseline", default="data/analysis/passage_rate_baseline.json")
    parser.add_argument("--out", default="data/analysis/enacted_reconciliation.json")
    parser.add_argument("--apply", action="store_true",
                        help="WRITE dump-confirmed enactments into bills.status/status_date. "
                             "Default is dry-run (report only). Run against local first.")
    args = parser.parse_args()

    from app.ingestion.dump_analytics import apply_enacted_corrections, reconcile_enacted

    rec = await reconcile_enacted(args.dump_dsn)
    c = rec["counts"]
    print("=== enacted reconciliation (ce_relevant bills) ===")
    print(f"  both agree:            {c['both']}")
    print(f"  only our status:       {c['only_ours']}  (dump lacks a signature action — keep)")
    print(f"  only dump action:      {c['only_dump']}  (our status STALE — fixable)")
    print(f"  neither:               {c['neither']}")
    print(f"  (bills with no openstates_id, dump-uncheckable: {c['no_osid']})")

    print("\n  stale-by-year (only_dump = our DB missed a real enactment):")
    for yr, d in rec["by_year"].items():
        if d["only_dump"]:
            print(f"    {yr}: {d['only_dump']}")

    # Corrected per-state gap (advancing CE, 2019+, reconciled enacted) vs all-bills baseline.
    base = {r["state"]: r["passage_rate"] for r in json.load(open(args.baseline))["per_state"]}
    print("\n=== corrected per-state gap (advancing CE, reconciled, 2019+, n>=15) ===")
    rows = []
    for st, d in rec["per_state_advances_2019plus"].items():
        if d["total"] < 15:
            continue
        ce = d["enacted"] / d["total"]
        b = base.get(st)
        rows.append((st, ce, d["enacted"], d["total"], b, (ce - b) if b is not None else None))
    for st, ce, en, tot, b, gap in sorted(rows, key=lambda x: -(x[5] if x[5] is not None else -9)):
        bs = f"{100 * b:5.1f}%" if b is not None else "   -- "
        gs = f"{100 * gap:+5.1f}pt" if gap is not None else "   -- "
        print(f"  {st:3} CE {100 * ce:5.1f}% ({en:2}/{tot:<3})  all-bills {bs}  gap {gs}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {args.out}  ({len(rec['corrections'])} corrections)")

    if args.apply:
        n = await apply_enacted_corrections(rec["corrections"])
        print(f"APPLIED: set status='enacted' on {n} bills.")
    else:
        print("(dry-run — re-run with --apply to write corrections into bills.status)")


if __name__ == "__main__":
    asyncio.run(main())
