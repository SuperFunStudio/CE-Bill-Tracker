"""Run the design-lever synthesis over bills that already have compliance_details.

Reads bills from the prod DB (read-only; via the Cloud SQL Auth Proxy), extracts cited
design signals with chain-of-custody enforcement (app/synthesis/design_levers.py), aggregates
them into Design-for-EPR principles, and writes two artifacts for review:
    tmp/design_signals.json      — every cited signal (the atoms)
    tmp/design_principles.json   — principles with their full evidence list

NO database writes and NO schema change — this is the reviewable artifact step. Persisting to
a bill_design_signal table comes after the output is approved.

Usage:
    cloud-sql-proxy --address 127.0.0.1 --port 5434 ce-bill-tracker:us-central1:signalscout-pg &
    venv/Scripts/python.exe scripts/synthesize_design_principles.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout" [--limit N]

Needs ANTHROPIC_API_KEY in the environment / .env (same as the classification pipeline).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

# Windows consoles default to cp1252; bill excerpts carry em-dashes etc. Force UTF-8 so the
# summary print never crashes (the JSON artifacts are already written UTF-8 regardless).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.synthesis.design_levers import (  # noqa: E402
    HAIKU_MODEL,
    DesignLeverExtractor,
    aggregate_principles,
)

TMP = Path(__file__).parent.parent / "tmp"


async def persist_signals(dsn: str, signals: list, processed_bill_ids: list[int]) -> int:
    """Idempotently replace design signals for the processed bills.

    Deletes existing rows for every bill we just re-extracted (so bills that now yield zero
    signals are cleared too), then inserts the fresh set. Re-running the synthesis converges.
    """
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM bill_design_signal WHERE bill_id = ANY($1::int[])",
                processed_bill_ids,
            )
            if signals:
                def _clip(v, n):
                    return v[:n] if isinstance(v, str) and len(v) > n else v
                await conn.executemany(
                    "INSERT INTO bill_design_signal "
                    "(bill_id, lever, obligation_type, design_action, source_excerpt, "
                    " threshold_value, threshold_unit, confidence, extractor_model) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                    # Guard the narrow varchar columns — an occasional verbose Haiku threshold_unit
                    # (e.g. "percent_reuse_recycling_minimum_by_category", 43 chars) overflows
                    # varchar(40) and aborts the whole persist transaction.
                    [(s.bill_id, _clip(s.lever, 40), _clip(s.obligation_type, 20), s.design_action,
                      s.source_excerpt, s.threshold_value, _clip(s.threshold_unit, 40),
                      s.confidence, HAIKU_MODEL)
                     for s in signals],
                )
    finally:
        await conn.close()
    return len(signals)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True, help="Prod Postgres DSN (via the Cloud SQL proxy).")
    ap.add_argument("--limit", type=int, default=None, help="Only process N bills (cheap test run).")
    ap.add_argument("--concurrency", type=int, default=5, help="Parallel extraction calls.")
    ap.add_argument("--persist", action="store_true",
                    help="Write signals to bill_design_signal (replaces signals for processed bills).")
    args = ap.parse_args()

    conn = await asyncpg.connect(args.dsn)
    try:
        q = (
            "SELECT id, state, bill_number, title, status, compliance_details "
            "FROM bills WHERE ce_relevant = true AND compliance_details IS NOT NULL "
            "ORDER BY (status = 'enacted') DESC, state, bill_number"
        )
        if args.limit:
            q += f" LIMIT {int(args.limit)}"
        rows = await conn.fetch(q)
    finally:
        await conn.close()

    bills = []
    for r in rows:
        details = r["compliance_details"]
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                continue
        bills.append({
            "id": r["id"], "state": r["state"], "bill_number": r["bill_number"],
            "title": r["title"], "status": r["status"], "compliance_details": details,
        })

    print(f"Extracting design signals from {len(bills)} bills (concurrency={args.concurrency})...")
    extractor = DesignLeverExtractor()
    sem = asyncio.Semaphore(args.concurrency)
    all_signals = []
    total_dropped = 0
    done = 0

    async def _one(bill: dict):
        nonlocal total_dropped, done
        async with sem:
            try:
                signals, dropped = await extractor.extract(bill)
            except Exception as e:
                print(f"  ! {bill['state']} {bill['bill_number']}: {type(e).__name__}: {e}")
                return
        all_signals.extend(signals)
        total_dropped += dropped
        done += 1
        flag = "*" if bill.get("status") == "enacted" else " "
        print(f"  [{done}/{len(bills)}]{flag}{bill['state']} {bill['bill_number'] or '?':<10} "
              f"+{len(signals)} signals" + (f" ({dropped} dropped)" if dropped else ""))

    await asyncio.gather(*[_one(b) for b in bills])

    principles = aggregate_principles(all_signals)

    TMP.mkdir(exist_ok=True)
    (TMP / "design_signals.json").write_text(
        json.dumps([s.to_dict() for s in all_signals], indent=2), encoding="utf-8"
    )
    (TMP / "design_principles.json").write_text(
        json.dumps([{
            "lever": p.lever, "obligation_type": p.obligation_type, "statement": p.statement,
            "bill_count": p.bill_count, "states": p.states, "evidence": p.evidence,
        } for p in principles], indent=2), encoding="utf-8"
    )

    # ---- Console summary --------------------------------------------------
    print("\n" + "=" * 78)
    print(f"DESIGN PRINCIPLES  ({len(all_signals)} cited signals, {total_dropped} dropped for "
          f"provenance, across {len({s.bill_id for s in all_signals})} bills)")
    print("=" * 78)
    for p in principles:
        print(f"\n[{p.bill_count} bills - {', '.join(p.states)}]  {p.statement}")
        for e in p.evidence[:4]:
            thr = ""
            if e["threshold_value"] is not None:
                thr = f"  ({e['threshold_value']:g} {e['threshold_unit'] or ''})".rstrip()
            print(f"    {e['state']} {e['bill_number'] or '?':<11} {e['design_action']}{thr}")
            print(f"        src: \"{e['source_excerpt'][:150]}\"")
        if len(p.evidence) > 4:
            print(f"    ... +{len(p.evidence) - 4} more bills")
    print(f"\nArtifacts: {TMP / 'design_signals.json'}")
    print(f"           {TMP / 'design_principles.json'}")

    if args.persist:
        n = await persist_signals(args.dsn, all_signals, [b["id"] for b in bills])
        print(f"\nPersisted {n} signals to bill_design_signal "
              f"(replaced rows for {len(bills)} bills).")


if __name__ == "__main__":
    asyncio.run(main())
