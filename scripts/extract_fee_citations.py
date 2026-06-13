"""Extract fee / threshold citations for bills that already have compliance_details.

Two grounding paths, combined per bill (see app/synthesis/fee_citations.py):
  1. LLM enacted_text — Haiku finds fees/thresholds the bill text actually states, each cited to a
     VERBATIM clause with chain-of-custody enforcement (fabricated quotes are dropped).
  2. curated published_schedule / benchmark — the existing compliance_details.fees overlay
     (scripts/enrich_bill_fees.py) turned into provenance rows, no LLM. This is where the per-ton
     EPR fees live, because they're set by agency/PRO rulemaking, not the statute.

Writes a reviewable artifact, and only writes to bill_fee_citation with --persist (idempotent: it
replaces all citations for the bills it processed, so re-running converges).

Usage:
    cloud-sql-proxy --address 127.0.0.1 --port 5434 ce-bill-tracker:us-central1:signalscout-pg &
    venv/Scripts/python.exe scripts/extract_fee_citations.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout" [--limit N] [--persist]

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

# Windows consoles default to cp1252; bill excerpts carry em-dashes etc. Force UTF-8 so the summary
# print never crashes (the JSON artifact is already written UTF-8 regardless).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.synthesis.fee_citations import (  # noqa: E402
    HAIKU_MODEL,
    FeeCitationExtractor,
    citations_from_curated_fees,
)

TMP = Path(__file__).parent.parent / "tmp"


async def persist_citations(dsn: str, citations: list, processed_bill_ids: list[int]) -> int:
    """Idempotently replace fee citations for the processed bills.

    Deletes existing rows for every bill we just re-processed (so bills that now yield zero citations
    are cleared too), then inserts the fresh set. The unique (bill_id, fact_type, basis) means an
    enacted_text and a published_schedule citation for the same fact coexist; a duplicate basis for the
    same fact would collide, so we de-dupe defensively before insert.
    """
    # De-dupe on the unique key (bill_id, fact_type, basis) — keep the first (LLM rows come first).
    seen: set[tuple] = set()
    rows = []
    for c in citations:
        key = (c.bill_id, c.fact_type, c.basis)
        if key in seen:
            continue
        seen.add(key)
        model = HAIKU_MODEL if c.basis == "enacted_text" else None
        rows.append((c.bill_id, c.fact_type, c.basis, c.extracted_value, c.value_unit,
                     c.source_excerpt, c.source_url, c.notes, c.confidence, model))

    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM bill_fee_citation WHERE bill_id = ANY($1::int[])",
                processed_bill_ids,
            )
            if rows:
                await conn.executemany(
                    "INSERT INTO bill_fee_citation "
                    "(bill_id, fact_type, basis, extracted_value, value_unit, source_excerpt, "
                    " source_url, notes, confidence, extractor_model) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                    rows,
                )
    finally:
        await conn.close()
    return len(rows)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True, help="Prod Postgres DSN (via the Cloud SQL proxy).")
    ap.add_argument("--limit", type=int, default=None, help="Only process N bills (cheap test run).")
    ap.add_argument("--concurrency", type=int, default=5, help="Parallel extraction calls.")
    ap.add_argument("--persist", action="store_true",
                    help="Write citations to bill_fee_citation (replaces rows for processed bills).")
    args = ap.parse_args()

    conn = await asyncpg.connect(args.dsn)
    try:
        q = (
            "SELECT id, state, bill_number, title, status, compliance_details "
            "FROM bills WHERE epr_relevant = true AND compliance_details IS NOT NULL "
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

    print(f"Extracting fee citations from {len(bills)} bills (concurrency={args.concurrency})...")
    extractor = FeeCitationExtractor()
    sem = asyncio.Semaphore(args.concurrency)
    all_citations = []
    total_dropped = 0
    done = 0

    async def _one(bill: dict):
        nonlocal total_dropped, done
        # Curated provenance is pure arithmetic — always available, no API call.
        curated = citations_from_curated_fees(bill)
        async with sem:
            try:
                cited, dropped = await extractor.extract(bill)
            except Exception as e:
                print(f"  ! {bill['state']} {bill['bill_number']}: {type(e).__name__}: {e}")
                cited, dropped = [], 0
        all_citations.extend(cited)
        all_citations.extend(curated)
        total_dropped += dropped
        done += 1
        flag = "*" if bill.get("status") == "enacted" else " "
        n_grounded = sum(1 for c in cited + curated if c.grounded)
        print(f"  [{done}/{len(bills)}]{flag}{bill['state']} {bill['bill_number'] or '?':<14} "
              f"+{len(cited)} text +{len(curated)} curated ({n_grounded} grounded)"
              + (f" ({dropped} dropped)" if dropped else ""))

    await asyncio.gather(*[_one(b) for b in bills])

    TMP.mkdir(exist_ok=True)
    (TMP / "fee_citations.json").write_text(
        json.dumps([c.to_dict() for c in all_citations], indent=2), encoding="utf-8"
    )

    # ---- Console summary --------------------------------------------------
    by_basis: dict[str, int] = {}
    for c in all_citations:
        by_basis[c.basis] = by_basis.get(c.basis, 0) + 1
    grounded = sum(1 for c in all_citations if c.grounded)
    print("\n" + "=" * 78)
    print(f"FEE CITATIONS  ({len(all_citations)} total, {grounded} grounded, "
          f"{total_dropped} dropped for provenance, across "
          f"{len({c.bill_id for c in all_citations})} bills)")
    print(f"  by basis: " + ", ".join(f"{b}={n}" for b, n in sorted(by_basis.items())))
    print("=" * 78)
    for c in [x for x in all_citations if x.basis == "enacted_text"][:25]:
        val = f"{c.extracted_value:g} {c.value_unit or ''}".strip() if c.extracted_value is not None else "(named)"
        print(f"  {c.state} {c.bill_number or '?':<14} {c.fact_type:<26} {val}")
        print(f"      src: \"{(c.source_excerpt or '')[:150]}\"")
    print(f"\nArtifact: {TMP / 'fee_citations.json'}")

    if args.persist:
        n = await persist_citations(args.dsn, all_citations, [b["id"] for b in bills])
        print(f"\nPersisted {n} citations to bill_fee_citation "
              f"(replaced rows for {len(bills)} bills).")


if __name__ == "__main__":
    asyncio.run(main())
