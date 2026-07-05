"""Report per-region bill counts + full-text coverage + stored language — the scope map.

Why
---
Before promoting any extracted dimension (eco-modulation, recycled-content minimums,
fee/penalty magnitudes) into a structured field, we need the denominators: for each
region, how many bills are ``ce_relevant`` and how many actually have full text stored
in ``bill_texts.text`` (extraction needs text). The existing ``GET /bills/text-coverage``
endpoint reports this only in aggregate; this script breaks it out per region and
annotates the language the source stores text in, because non-English text is the gating
constraint for the Sonnet extractor (its windowing anchors are English-only).

Read-only: issues a single GROUP BY SELECT, never writes. Point --dsn at prod via the
Cloud SQL Auth Proxy to measure prod (same pattern as scan_bill_polymers.py).

    python scripts/coverage_by_region.py                                  # local
    python scripts/coverage_by_region.py --dsn "postgresql://signalscout@127.0.0.1:5434/signalscout"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402

# Language the source ADAPTER stores text in (from app/ingestion/foreign.py + eurlex.py).
# English regions are extraction-ready today; native-language regions gate on the Phase 2
# language spike. Unlisted regions default to "?" and should be treated as native/unknown.
REGION_LANG = {
    "US": "en", "EU": "en", "UK": "en", "IE": "en", "CA": "en/fr", "AU": "en", "ZA": "en",
    "FR": "fr", "DE": "de", "AT": "de", "CH": "de/fr/it", "NL": "nl", "ES": "es",
    "CL": "es", "SE": "sv", "PL": "pl", "CZ": "cs", "BR": "pt", "KR": "ko", "JP": "ja",
    "CN": "zh", "IT": "it",
}
ENGLISH = {"US", "EU", "UK", "IE", "CA", "AU", "ZA"}  # CA is bilingual but stores EN


def _normalize_dsn(dsn: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return dsn if prefix == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(prefix):]
    return dsn


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    args = ap.parse_args()

    engine = create_async_engine(_normalize_dsn(args.dsn or settings.database_url))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    sql = text(
        "SELECT b.region, "
        "       COUNT(*) AS total, "
        "       COUNT(*) FILTER (WHERE b.ce_relevant) AS relevant, "
        "       COUNT(*) FILTER (WHERE b.ce_relevant AND bt.text IS NOT NULL) AS has_text "
        "FROM bills b LEFT JOIN bill_texts bt ON b.id = bt.bill_id "
        "GROUP BY b.region ORDER BY relevant DESC"
    )

    async with Session() as db:
        rows = (await db.execute(sql)).all()

    hdr = f"{'region':<8}{'lang':<9}{'ready':<7}{'total':>8}{'relevant':>10}{'has_text':>10}{'cover%':>9}"
    print(hdr)
    print("-" * len(hdr))
    tot_rel = tot_txt = tot_rel_en = tot_txt_en = 0
    for r in rows:
        region = r.region or "?"
        lang = REGION_LANG.get(region, "?")
        ready = "en" if region in ENGLISH else "spike"
        cover = (r.has_text / r.relevant * 100) if r.relevant else 0.0
        print(f"{region:<8}{lang:<9}{ready:<7}{r.total:>8}{r.relevant:>10}{r.has_text:>10}{cover:>8.0f}%")
        tot_rel += r.relevant
        tot_txt += r.has_text
        if region in ENGLISH:
            tot_rel_en += r.relevant
            tot_txt_en += r.has_text
    print("-" * len(hdr))
    print(f"{'ALL':<24}{'':>8}{tot_rel:>10}{tot_txt:>10}"
          f"{(tot_txt / tot_rel * 100) if tot_rel else 0:>8.0f}%")
    print(f"{'ENGLISH (ready)':<24}{'':>8}{tot_rel_en:>10}{tot_txt_en:>10}"
          f"{(tot_txt_en / tot_rel_en * 100) if tot_rel_en else 0:>8.0f}%")
    print(f"{'NON-ENGLISH (spike)':<24}{'':>8}{tot_rel - tot_rel_en:>10}{tot_txt - tot_txt_en:>10}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
