"""Prove (or disprove) the foreign full-text RANK-REACHABILITY problem, per region.

Why
---
`coverage_by_region.py` shows that foreign bills have `bill_texts.text` stored — but that's
misleading for RANKING. The deep-read set ranks bills by an ENGLISH tsquery against an ENGLISH
tsvector (`to_tsvector('english', text)`). Foreign body text is stored in its NATIVE language,
so an English EPR query never matches it (`ts_rank ≈ 0`) and the bill falls back to ranking on
its English title+summary (`_meta_doc`) only — which is why corpus-wide answers skew US/EU.

This script quantifies that. For each region it reports, over ce_relevant bills:
  relevant      - ce_relevant bill count
  has_text      - has a bill_texts.text row
  nonempty_tsv  - text_tsv actually has tokens (native tokens still count here)
  avg_chars     - average stored body length
  body_hit_en   - body text_tsv matches a broad ENGLISH EPR probe   <- the reachability signal
  meta_hit_en   - title+ai_summary matches the same probe            <- the current fallback
  reach%        - body_hit_en / relevant

Expected result if the reframe is right: US/EN regions show high body_hit_en; FR/DE/JP/CN/KR/etc.
show has_text ~= relevant but body_hit_en ~= 0 while meta_hit_en carries whatever match exists.
That gap IS the translation-layer justification: the text is present but unrankable in English.

Read-only: one GROUP BY SELECT, never writes. Point --dsn at prod via the Cloud SQL Auth Proxy.

    # local
    venv/Scripts/python.exe scripts/foreign_rank_reachability.py
    # prod (proxy on 5436, same pattern as corpus_survey_ask.py / deploy-mechanism):
    PW=$(gcloud secrets versions access latest --secret=SIGNALSCOUT_DB_PASSWORD --project=ce-bill-tracker)
    venv/Scripts/python.exe scripts/foreign_rank_reachability.py \
        --dsn "postgresql://signalscout:$PW@127.0.0.1:5436/signalscout"
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

# Broad OR-tsquery of common English EPR/circular-economy terms. A bill "reachable in English"
# is one whose stored body matches AT LEAST ONE of these — a generous bar on purpose, so a near-zero
# body_hit_en for a region can't be blamed on a narrow probe.
PROBE = " | ".join([
    "packaging", "recycling", "recycle", "recycled", "waste", "producer", "responsibility",
    "deposit", "battery", "batteries", "plastic", "plastics", "extended", "circular", "reuse",
    "refill", "compost", "landfill", "textile", "electronic", "e-waste", "container", "beverage",
])

# Regions whose adapters store English text (from coverage_by_region.py). Everything else is native.
ENGLISH = {"US", "EU", "UK", "IE", "CA", "AU", "ZA", "IN"}


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

    # :probe is bound into to_tsquery('english', :probe) so the same parsed query hits both the
    # stored body tsvector and a freshly-built title+summary tsvector.
    sql = text(
        "WITH q AS (SELECT to_tsquery('english', :probe) AS tsq) "
        "SELECT b.region, "
        "  COUNT(*) FILTER (WHERE b.ce_relevant) AS relevant, "
        "  COUNT(*) FILTER (WHERE b.ce_relevant AND bt.text IS NOT NULL) AS has_text, "
        "  COUNT(*) FILTER (WHERE b.ce_relevant AND bt.text_tsv IS NOT NULL "
        "                   AND bt.text_tsv <> '') AS nonempty_tsv, "
        "  ROUND(AVG(bt.char_len) FILTER (WHERE b.ce_relevant AND bt.text IS NOT NULL)) AS avg_chars, "
        "  COUNT(*) FILTER (WHERE b.ce_relevant AND bt.text_tsv @@ q.tsq) AS body_hit_en, "
        "  COUNT(*) FILTER (WHERE b.ce_relevant "
        "     AND to_tsvector('english', concat_ws(' ', b.title, b.ai_summary)) @@ q.tsq) AS meta_hit_en "
        "FROM bills b CROSS JOIN q "
        "LEFT JOIN bill_texts bt ON b.id = bt.bill_id "
        "GROUP BY b.region ORDER BY relevant DESC"
    )

    async with Session() as db:
        rows = (await db.execute(sql, {"probe": PROBE})).all()

    hdr = (f"{'region':<8}{'lang':<7}{'relevant':>9}{'has_text':>9}{'tsv':>7}"
           f"{'avgchr':>8}{'body_en':>9}{'meta_en':>9}{'reach%':>8}")
    print(hdr)
    print("-" * len(hdr))
    t_rel = t_body_en = t_body_en_fx = t_rel_fx = 0
    for r in rows:
        region = r.region or "?"
        lang = "en" if region in ENGLISH else "native"
        reach = (r.body_hit_en / r.relevant * 100) if r.relevant else 0.0
        print(f"{region:<8}{lang:<7}{r.relevant:>9}{r.has_text:>9}{r.nonempty_tsv:>7}"
              f"{(r.avg_chars or 0):>8}{r.body_hit_en:>9}{r.meta_hit_en:>9}{reach:>7.0f}%")
        t_rel += r.relevant
        t_body_en += r.body_hit_en
        if region not in ENGLISH:
            t_rel_fx += r.relevant
            t_body_en_fx += r.body_hit_en
    print("-" * len(hdr))
    print(f"ALL relevant={t_rel}  body-reachable-in-english={t_body_en} "
          f"({(t_body_en / t_rel * 100) if t_rel else 0:.0f}%)")
    print(f"NON-ENGLISH regions: relevant={t_rel_fx}  body-reachable-in-english={t_body_en_fx} "
          f"({(t_body_en_fx / t_rel_fx * 100) if t_rel_fx else 0:.1f}%)  "
          f"<- if this % is tiny, foreign body text is stored but unrankable in English (the reframe).")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
