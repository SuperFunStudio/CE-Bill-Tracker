"""Curated covered-product extraction for the ENACTED consumer-electronics right-to-repair laws.

The broad backfill (build_product_coverage.py) misses these because the Haiku classifier leaves
most right-to-repair bills with an empty material_categories (it tags the *mechanism*, not the
product), so they never pass the electronics filter. This script names the canonical enacted laws
explicitly, fetches each one's real document (overriding the landing-page source_url where needed),
extracts with the shared cited extractor, and prints a state-by-state product-coverage matrix —
the "which products does each state's repair law cover" comparison.

Text acquisition per law (in order): an explicit text_file (paste), else doc_url, else the stored
source_url, else the OpenStates versions API. Some state sites hard-block automated fetches
(MN revisor.mn.gov, HI capitol) — drop a pasted text file and set text_file to include them.

Usage:
    venv/Scripts/python.exe scripts/build_r2r_electronics_set.py \
        --dsn "postgresql://postgres:dev@localhost:5432/signalscout" [--persist]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

logging.disable(logging.CRITICAL)
import structlog  # noqa: E402
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

from app.ingestion.openstates import OpenStatesClient  # noqa: E402
from app.synthesis.product_coverage import SONNET_MODEL, ProductCoverageExtractor  # noqa: E402
from app.synthesis.product_taxonomy import BY_SLUG, products_for  # noqa: E402

# The canonical enacted consumer-electronics right-to-repair laws. doc_url overrides the stored
# landing-page source_url; text_file (a path under tmp/) overrides everything for hard-blocked sites.
TARGETS = [
    {"state": "NY", "bill_number": "S-4104", "max_chars": 22000,
     "doc_url": "https://assembly.state.ny.us/leg/?bn=S04104&Text=Y&term=2021&Summary=Y"},
    {"state": "MN", "bill_number": "SF-1598",
     "text_file": "tmp/mn_sf1598.txt",  # revisor.mn.gov blocks automated fetch — paste text here
     "note": "revisor.mn.gov blocks httpx + WebFetch; paste statute 325E.72 / SF-1598 text"},
    {"state": "CA", "bill_number": "SB-244"},
    {"state": "CO", "bill_number": "HB-24-1121"},
    {"state": "OR", "bill_number": "SB-1596", "max_chars": 34000},
]
ROOT = Path(__file__).parent.parent


async def acquire_text(client, t: dict, source_url: str | None, openstates_id: str | None) -> str:
    tf = t.get("text_file")
    if tf and (ROOT / tf).exists():
        return (ROOT / tf).read_text(encoding="utf-8", errors="ignore")
    if t.get("doc_url"):
        text = await client.get_text_from_source(t["doc_url"])
        if len(text.strip()) >= 200:
            return text
    if source_url:
        text = await client.get_text_from_source(source_url)
        if len(text.strip()) >= 200:
            return text
    if openstates_id:
        try:
            return await client.get_bill_text(openstates_id)
        except Exception:
            return ""
    return ""


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--persist", action="store_true")
    args = ap.parse_args()

    conn = await asyncpg.connect(args.dsn)
    extractor = ProductCoverageExtractor()
    results: dict[str, dict] = {}  # state -> {slug: status}
    all_cov: list = []
    order: list[str] = []

    async with OpenStatesClient() as client:
        for t in TARGETS:
            st, bn = t["state"], t["bill_number"]
            row = await conn.fetchrow(
                "SELECT id, title, source_url, openstates_id FROM bills "
                "WHERE state=$1 AND bill_number=$2 ORDER BY id LIMIT 1", st, bn)
            if not row:
                print(f"  ! {st} {bn}: not in DB"); continue
            text = await acquire_text(client, t, row["source_url"], row["openstates_id"])
            if len(text.strip()) < 200:
                print(f"  ! {st} {bn}: NO TEXT ({t.get('note', 'source unreachable')})")
                results[st] = {}; order.append(st); continue
            bill = {
                "id": row["id"], "state": st, "bill_number": bn, "title": row["title"],
                "instrument_type": "right_to_repair", "categories": ["electronics"],
                "full_text": text, "compliance_details": None,
            }
            cov, dropped = await extractor.extract(bill, max_chars=t.get("max_chars", 14000))
            all_cov.extend(cov)
            results[st] = {c.product_slug: c.status for c in cov}
            order.append(st)
            print(f"  {st} {bn:<12} {len(text):>6} chars -> {len(cov)} products"
                  + (f" ({dropped} dropped)" if dropped else ""))

    if args.persist and all_cov:
        ids = sorted({c.bill_id for c in all_cov})
        async with conn.transaction():
            await conn.execute("DELETE FROM bill_product_coverage WHERE bill_id = ANY($1::int[])", ids)
            await conn.executemany(
                "INSERT INTO bill_product_coverage (bill_id, product_slug, category, "
                "relationship_type, status, defined_by_reference, source_excerpt, threshold_value, "
                "threshold_unit, confidence, extractor_model) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                [(c.bill_id, c.product_slug, c.category, c.relationship_type, c.status,
                  c.defined_by_reference, c.source_excerpt, c.threshold_value, c.threshold_unit,
                  c.confidence, SONNET_MODEL) for c in all_cov])
        print(f"\nPersisted {len(all_cov)} rows across {len(ids)} bills.")
    await conn.close()

    # ---- State-by-state coverage matrix -----------------------------------
    glyph = {"covered": "●", "exempt": "○", "conditional": "◐"}
    print("\n" + "=" * 70)
    print("ENACTED ELECTRONICS RIGHT-TO-REPAIR — PRODUCT COVERAGE BY STATE")
    print("=" * 70)
    print("  ● covered   ○ exempt   ◐ conditional   · not addressed\n")
    hdr = "  ".join(f"{s:>3}" for s in order)
    print(f"{'product':<26} {hdr}")
    for p in products_for("electronics"):
        cells = "  ".join(f"{glyph.get(results.get(s, {}).get(p.slug), '·'):>3}" for s in order)
        # Skip rows no state addresses, to keep the matrix readable.
        if any(results.get(s, {}).get(p.slug) for s in order):
            print(f"{p.label:<26} {cells}")


if __name__ == "__main__":
    asyncio.run(main())
