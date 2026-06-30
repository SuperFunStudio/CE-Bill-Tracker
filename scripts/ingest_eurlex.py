"""Ingest EU-central circular-economy law from EUR-Lex/CELLAR into the bills table.

Two modes (both reuse app.ingestion.eurlex.sync_eurlex — the same path the weekly scheduler uses):
  - default: just the curated SEED_ACTS (8 core instruments) — the quick spike.
  - --bulk:  SPARQL-discover the full in-force circular-economy slice (~hundreds of acts) by EuroVoc
             concept, then fetch + classify all. The EU analog of the US bulk backfill.

Each act becomes a region='EU', state='EU' bill keyed on celex_id, with full text in bill_texts, then
the region-aware ClassificationPipeline judges relevance (Haiku) + extracts compliance detail (Sonnet).

Run against the DEV database (do NOT point at prod during the spike):

    # with the Cloud SQL Auth Proxy on 127.0.0.1:5434 ->
    venv/Scripts/python scripts/ingest_eurlex.py --bulk \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout_dev"

    venv/Scripts/python scripts/ingest_eurlex.py            # seed only, local DB
    venv/Scripts/python scripts/ingest_eurlex.py --bulk --all   # incl. repealed/historical
    venv/Scripts/python scripts/ingest_eurlex.py --bulk --only-new   # weekly-refresh behavior

--dsn defaults to the app's DATABASE_URL. Classification needs ANTHROPIC_API_KEY (from .env).
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def _run(bulk: bool, in_force_only: bool, only_new: bool, classify: bool, max_acts: int | None) -> None:
    # Imports happen AFTER --dsn is applied to the environment so the engine binds to the right DB.
    from app.ingestion.eurlex import sync_eurlex

    # Seed-only mode = no SPARQL discovery (just the curated list). Bulk mode discovers the full slice.
    if not bulk:
        # Seed only: discovery off. include_seed=True with discovery skipped -> just SEED_ACTS.
        from app.ingestion.eurlex import SEED_ACTS, EurLexClient
        from app.classification.pipeline import ClassificationPipeline
        from app.database import AsyncSessionLocal
        from app.models import Bill, BillText
        from sqlalchemy import select

        async with EurLexClient() as client, AsyncSessionLocal() as db:
            ids = []
            for a in SEED_ACTS:
                act = await client.fetch_act(a["celex"], fallback_name=a["name"])
                if not act:
                    print(f"  -- {a['celex']} skipped")
                    continue
                bill = (await db.execute(select(Bill).where(Bill.celex_id == act.celex))).scalar_one_or_none()
                if bill is None:
                    bill = Bill(celex_id=act.celex, region="EU", state="EU")
                    db.add(bill)
                bill.region, bill.state = "EU", "EU"
                bill.bill_number, bill.title, bill.description = act.bill_number, act.title, act.summary
                bill.status, bill.source_url = act.status, act.source_url
                await db.flush()
                bt = (await db.execute(select(BillText).where(BillText.bill_id == bill.id))).scalar_one_or_none()
                if bt is None:
                    bt = BillText(bill_id=bill.id); db.add(bt)
                bt.text, bt.char_len = act.full_text, len(act.full_text)
                ids.append(bill.id)
                print(f"  ok {act.celex} | {act.title[:70]}")
            await db.commit()
        if classify and ids:
            async with AsyncSessionLocal() as db:
                bills = list((await db.execute(select(Bill).where(Bill.id.in_(ids)))).scalars().all())
                res = await ClassificationPipeline().run(db, bills, skip_keyword_filter=True)
            print(f"Classified haiku={res.classified_haiku} sonnet={res.extracted_sonnet}")
        print(f"Seed ingest done: {len(ids)} acts.")
        return

    print(f"Bulk EU ingest (in_force_only={in_force_only}, only_new={only_new})...")
    summary = await sync_eurlex(
        in_force_only=in_force_only, classify=classify, only_new=only_new, max_acts=max_acts
    )
    print(
        f"Done. discovered={summary['discovered']} fetched={summary['fetched']} "
        f"skipped={summary['skipped']} ingested={summary['ingested']} "
        f"classified={summary['classified']} EU-relevant-total={summary['relevant']}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DB DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--bulk", action="store_true", help="SPARQL-discover the full in-force slice (not just seed).")
    ap.add_argument("--all", action="store_true", help="Include repealed/historical acts (default: in-force only).")
    ap.add_argument("--only-new", action="store_true", help="Skip CELEX already in the DB (weekly-refresh mode).")
    ap.add_argument("--no-classify", action="store_true", help="Ingest only; skip LLM classification.")
    ap.add_argument("--max", type=int, default=None, help="Cap acts processed this run.")
    args = ap.parse_args()

    if args.dsn:
        os.environ["DATABASE_URL"] = args.dsn
    if not args.no_classify:
        os.environ["ENABLE_LLM_CLASSIFICATION"] = "true"
        os.environ["ENABLE_SONNET_EXTRACTION"] = "true"

    asyncio.run(
        _run(
            bulk=args.bulk,
            in_force_only=not args.all,
            only_new=args.only_new,
            classify=not args.no_classify,
            max_acts=args.max,
        )
    )


if __name__ == "__main__":
    main()
