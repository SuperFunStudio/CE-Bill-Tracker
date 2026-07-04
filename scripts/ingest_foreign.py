"""Ingest foreign national circular-economy / EPR law into the bills table (pluggable per region).

Generalizes scripts/ingest_eurlex.py to non-EU jurisdictions via app.ingestion.foreign. Each region has
an adapter registered in FOREIGN_CLIENTS (JP/FR/UK/DE/…/CN/CA/AU — see the dict for keys; subnational
jurisdictions share a country region, e.g. CA_BC/CA_ON write region="CA"). Every law becomes a
region=<XX>, state=<XX> bill keyed on foreign_id, with full text in bill_texts, then the region-aware
ClassificationPipeline judges relevance (Haiku) + extracts compliance detail (Sonnet).

Run against the DEV database (do NOT point at prod during the spike):

    # with the Cloud SQL Auth Proxy on 127.0.0.1:5434 ->
    venv/Scripts/python scripts/ingest_foreign.py --region JP \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout_dev"

    venv/Scripts/python scripts/ingest_foreign.py --region JP                 # local DB, full slice
    venv/Scripts/python scripts/ingest_foreign.py --region JP --max 12        # bounded test run
    venv/Scripts/python scripts/ingest_foreign.py --region JP --only-new      # refresh mode
    venv/Scripts/python scripts/ingest_foreign.py --region JP --no-classify   # scrape only

--dsn defaults to the app's DATABASE_URL. Classification needs ANTHROPIC_API_KEY (from .env).
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def _run(region: str, only_new: bool, classify: bool, max_laws: int | None) -> None:
    # Import AFTER --dsn is applied to the environment so the engine binds to the right DB.
    from app.ingestion.foreign import sync_foreign

    print(f"Foreign ingest region={region} (only_new={only_new}, max={max_laws})...")
    summary = await sync_foreign(
        region=region, classify=classify, only_new=only_new, max_laws=max_laws
    )
    print(
        f"Done. discovered={summary['discovered']} fetched={summary['fetched']} "
        f"skipped={summary['skipped']} ingested={summary['ingested']} "
        f"classified={summary['classified']} {region}-relevant-total={summary['relevant']}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", required=True, help="Region code with a registered adapter (e.g. JP).")
    ap.add_argument("--dsn", default=None, help="Target DB DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--only-new", action="store_true", help="Skip foreign_ids already in the DB.")
    ap.add_argument("--no-classify", action="store_true", help="Ingest only; skip LLM classification.")
    ap.add_argument("--max", type=int, default=None, help="Cap laws processed this run.")
    args = ap.parse_args()

    if args.dsn:
        os.environ["DATABASE_URL"] = args.dsn
    if not args.no_classify:
        os.environ["ENABLE_LLM_CLASSIFICATION"] = "true"
        os.environ["ENABLE_SONNET_EXTRACTION"] = "true"

    asyncio.run(
        _run(
            region=args.region.upper(),
            only_new=args.only_new,
            classify=not args.no_classify,
            max_laws=args.max,
        )
    )


if __name__ == "__main__":
    main()
