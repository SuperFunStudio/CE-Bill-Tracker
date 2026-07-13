"""Backfill covered-product coverage for electronics + battery bills (product-coverage Phase 2).

For each in-scope bill it fetches the FULL bill text (from the source_url we already hold — the
same robust path the deadline backfill uses, which handles PDFs, CA's JS shell, and bad TLS), runs
the cited extractor (app/synthesis/product_coverage.py), and writes a reviewable JSON artifact.
With --persist it idempotently replaces that bill's rows in bill_product_coverage.

In scope = ce_relevant AND tagged electronics/batteries AND instrument_type in
(epr, right_to_repair, deposit_return) — the Phase 0 pre-filter that drops the other/budget/
preemption mistags before spending extraction calls.

Usage (read-only dry run, writes only the JSON artifact):
    cloud-sql-proxy --address 127.0.0.1 --port 5434 ce-bill-tracker:us-central1:signalscout-pg &
    venv/Scripts/python.exe scripts/build_product_coverage.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout" --limit 15
    # add --persist to write bill_product_coverage; --category electronics|batteries to restrict.

Needs ANTHROPIC_API_KEY and OPEN_STATES_API_KEY in the environment / .env.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # bill excerpts carry em-dashes; Windows is cp1252
except Exception:
    pass

from app.ingestion.openstates import OpenStatesClient  # noqa: E402
from app.synthesis.product_coverage import (  # noqa: E402
    MODELS,
    ProductCoverageExtractor,
    RELATIONSHIP_BY_INSTRUMENT,
)
from app.synthesis.product_taxonomy import BY_SLUG  # noqa: E402

TMP = Path(__file__).parent.parent / "tmp"
CATEGORIES = ("electronics", "batteries")


async def persist(dsn: str, coverages: list, processed_bill_ids: list[int], model: str) -> int:
    """Idempotently replace coverage for the processed bills: delete their rows (so bills that now
    yield nothing are cleared), then insert the fresh set. Re-running converges."""
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM bill_product_coverage WHERE bill_id = ANY($1::int[])",
                processed_bill_ids,
            )
            if coverages:
                await conn.executemany(
                    "INSERT INTO bill_product_coverage "
                    "(bill_id, product_slug, category, relationship_type, status, "
                    " defined_by_reference, source_excerpt, threshold_value, threshold_unit, "
                    " confidence, extractor_model) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                    [(c.bill_id, c.product_slug, c.category, c.relationship_type, c.status,
                      c.defined_by_reference, c.source_excerpt, c.threshold_value,
                      c.threshold_unit, c.confidence, model) for c in coverages],
                )
    finally:
        await conn.close()
    return len(coverages)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True, help="Postgres DSN (via the Cloud SQL proxy).")
    ap.add_argument("--limit", type=int, default=None, help="Only process N bills (cheap test run).")
    ap.add_argument("--concurrency", type=int, default=5, help="Parallel fetch+extract pipelines.")
    ap.add_argument("--category", choices=CATEGORIES, default=None,
                    help="Restrict to one stream (default: electronics + batteries).")
    ap.add_argument("--bill-ids", default=None,
                    help="Comma-separated bill ids to (re)process — e.g. retry the no-text set.")
    ap.add_argument("--persist", action="store_true",
                    help="Write to bill_product_coverage (replaces rows for processed bills).")
    ap.add_argument("--model", choices=sorted(MODELS), default="sonnet",
                    help="Extraction model (haiku is ~10x cheaper; validate recall first).")
    args = ap.parse_args()

    wanted = [args.category] if args.category else list(CATEGORIES)
    instruments = list(RELATIONSHIP_BY_INSTRUMENT)

    bill_ids = [int(x) for x in args.bill_ids.split(",") if x.strip()] if args.bill_ids else None

    conn = await asyncpg.connect(args.dsn)
    try:
        q = (
            "SELECT id, state, bill_number, title, status, instrument_type, source_url, "
            "       openstates_id, material_categories, compliance_details "
            "FROM bills "
            "WHERE ce_relevant = true "
            "  AND material_categories ?| $1::text[] "
            "  AND instrument_type = ANY($2::text[]) "
        )
        params: list = [wanted, instruments]
        if bill_ids:
            q += "  AND id = ANY($3::int[]) "
            params.append(bill_ids)
        q += "ORDER BY (status = 'enacted') DESC, state, bill_number"
        if args.limit:
            q += f" LIMIT {int(args.limit)}"
        rows = await conn.fetch(q, *params)
    finally:
        await conn.close()

    def _as_list(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v or []

    bills = []
    for r in rows:
        mats = _as_list(r["material_categories"])
        cats = [c for c in wanted if c in mats]
        if not cats:
            continue
        details = r["compliance_details"]
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                details = None
        bills.append({
            "id": r["id"], "state": r["state"], "bill_number": r["bill_number"],
            "title": r["title"], "status": r["status"],
            "instrument_type": r["instrument_type"], "source_url": r["source_url"],
            "openstates_id": r["openstates_id"],
            "categories": cats, "compliance_details": details,
        })

    print(f"Extracting product coverage from {len(bills)} bills "
          f"(categories={'+'.join(wanted)}, concurrency={args.concurrency})...")

    extractor = ProductCoverageExtractor(model=MODELS[args.model])
    sem = asyncio.Semaphore(args.concurrency)
    all_cov: list = []
    total_dropped = 0
    no_text = 0
    done = 0

    async with OpenStatesClient() as os_client:
        async def _one(bill: dict):
            nonlocal total_dropped, no_text, done
            async with sem:
                try:
                    text = ""
                    if bill.get("source_url"):
                        text = await os_client.get_text_from_source(bill["source_url"])
                    # Our stored source_url is often a bill landing page with no inline text. When it
                    # yields little, fall back to the OpenStates versions API, which returns the
                    # curated document links (text/plain -> html -> PDF) instead of the status page.
                    if len((text or "").strip()) < 200 and bill.get("openstates_id"):
                        alt = await os_client.get_bill_text(bill["openstates_id"])
                        if len((alt or "").strip()) > len((text or "").strip()):
                            text = alt
                    bill["full_text"] = text
                    cov, dropped = await extractor.extract(bill)
                except Exception as e:
                    print(f"  ! {bill['state']} {bill['bill_number']}: {type(e).__name__}: {e}")
                    return
            if not (bill.get("full_text") or "").strip():
                no_text += 1
            all_cov.extend(cov)
            total_dropped += dropped
            done += 1
            flag = "*" if bill.get("status") == "enacted" else " "
            note = f"+{len(cov)}" if cov else "  -"
            print(f"  [{done}/{len(bills)}]{flag}{bill['state']} {bill['bill_number'] or '?':<10} "
                  f"{note}" + (f" ({dropped} dropped)" if dropped else "")
                  + ("  [no text]" if not (bill.get('full_text') or '').strip() else ""))

        await asyncio.gather(*[_one(b) for b in bills])

    TMP.mkdir(exist_ok=True)
    (TMP / "product_coverage.json").write_text(
        json.dumps([c.to_dict() for c in all_cov], indent=2), encoding="utf-8"
    )

    # ---- Console summary --------------------------------------------------
    by_product: Counter = Counter()
    by_status: Counter = Counter()
    for c in all_cov:
        by_product[c.product_slug] += 1
        by_status[c.status] += 1
    bills_with = len({c.bill_id for c in all_cov})

    print("\n" + "=" * 78)
    print(f"PRODUCT COVERAGE  ({len(all_cov)} rows across {bills_with} bills; "
          f"{total_dropped} dropped for provenance; {no_text} bills had no fetchable text)")
    print("=" * 78)
    print("By status: " + ", ".join(f"{k}={v}" for k, v in by_status.most_common()))
    print("\nBy product (covered/exempt/conditional rows):")
    for slug, n in by_product.most_common():
        label = BY_SLUG[slug].label if slug in BY_SLUG else slug
        print(f"  {n:>4}  {slug:<24} {label}")
    print(f"\nArtifact: {TMP / 'product_coverage.json'}")

    if args.persist:
        n = await persist(args.dsn, all_cov, [b["id"] for b in bills], MODELS[args.model])
        print(f"\nPersisted {n} coverage rows to bill_product_coverage "
              f"(replaced rows for {len(bills)} bills).")


if __name__ == "__main__":
    asyncio.run(main())
