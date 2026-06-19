"""Backfill / reclassify federal_actions on the three classifier axes.

Why this exists separately from coordinator.run_federal_cycle:
  - run_federal_cycle only classifies NEWLY-inserted rows and is capped at
    settings.max_haiku_calls_per_run (30). It cannot re-score the rows already in the table,
    which is exactly what we need after (a) fixing the Federal Register search to quote phrases
    and (b) adding the friction_type / instrument_type axes + the confidence floor.

What it does (idempotent):
  1. Pull docs from the Federal Register using the calibrated QUOTED term list
     (app/ingestion/federal_register.py), back to --since, and insert any not already stored.
  2. Re-classify every row missing instrument_type (i.e. not yet scored on the 3-axis schema),
     writing ce_relevant (via the confidence floor), preemption_risk, friction_type,
     instrument_type, ai_summary, material_categories.

Run against prod via the Cloud SQL Auth Proxy:
    DATABASE_URL="postgresql://signalscout:PW@127.0.0.1:5439/signalscout" \
        python scripts/backfill_federal_actions.py --since 2021-01-01 [--limit-classify N]

Honors ANTHROPIC_API_KEY from the environment / .env (same as the app).
"""
import argparse
import asyncio
from datetime import date, datetime

import structlog
from sqlalchemy import select

from app.classification.federal_classifier import FederalClassifier
from app.database import AsyncSessionLocal
from app.ingestion.federal_register import FederalRegisterClient
from app.models import FederalAction

log = structlog.get_logger()


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


async def pull_and_upsert(db, since: date) -> int:
    async with FederalRegisterClient() as fr:
        docs = await fr.search_all_epr_terms(published_since=since)
    existing = set(
        (await db.execute(select(FederalAction.federal_register_document_number))).scalars().all()
    )
    inserted = 0
    for doc in docs:
        doc_num = doc.get("document_number")
        if not doc_num or doc_num in existing:
            continue
        agencies = doc.get("agencies", [])
        action = FederalAction(
            federal_register_document_number=doc_num,
            agency=(agencies[0].get("name", "") if agencies else ""),
            title=doc.get("title"),
            action_type=(doc.get("type", "") or "").lower().replace(" ", "_"),
            published_date=_parse_date(doc.get("publication_date")),
            comment_deadline=_parse_date(doc.get("comments_close_on")),
            effective_date=_parse_date(doc.get("effective_on")),
            document_url=doc.get("html_url"),
            raw_data=doc,
        )
        db.add(action)
        existing.add(doc_num)
        inserted += 1
    await db.commit()
    print(f"Pulled {len(docs)} docs from FR; inserted {inserted} new rows.")
    return inserted


async def reclassify(db, limit_classify: int | None) -> dict:
    # Every row lacking instrument_type predates the 3-axis schema → (re)classify it.
    q = select(FederalAction).where(FederalAction.instrument_type.is_(None))
    if limit_classify:
        q = q.limit(limit_classify)
    targets = (await db.execute(q)).scalars().all()
    print(f"Rows to classify (instrument_type IS NULL): {len(targets)}")
    if not targets:
        return {"classified": 0, "relevant": 0}

    clf = FederalClassifier()
    sem = asyncio.Semaphore(8)
    done = {"n": 0}

    async def run(action):
        async with sem:
            abstract = (action.raw_data or {}).get("abstract", "") if action.raw_data else ""
            try:
                fr = await clf.classify(
                    title=action.title or "", agency=action.agency or "",
                    action_type=action.action_type or "", abstract=abstract,
                )
            except Exception as e:
                log.error("classify_failed", doc=action.federal_register_document_number, error=str(e))
                return None
            done["n"] += 1
            if done["n"] % 25 == 0:
                print(f"  classified {done['n']}/{len(targets)}...")
            return (action, fr)

    results = [r for r in await asyncio.gather(*[run(a) for a in targets]) if r]
    relevant = 0
    for action, fr in results:
        action.ce_relevant = fr.in_scope
        action.preemption_risk = fr.preemption_risk
        action.friction_type = fr.friction_type
        action.instrument_type = fr.instrument_type
        action.ai_summary = fr.summary
        action.material_categories = fr.material_categories
        relevant += int(fr.in_scope)
    await db.commit()
    return {"classified": len(results), "relevant": relevant}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2021-01-01", help="publication_date >= (YYYY-MM-DD)")
    ap.add_argument("--limit-classify", type=int, default=None, help="cap rows classified (testing)")
    ap.add_argument("--skip-pull", action="store_true", help="reclassify only, don't hit FR API")
    args = ap.parse_args()
    since = datetime.strptime(args.since, "%Y-%m-%d").date()

    async with AsyncSessionLocal() as db:
        if not args.skip_pull:
            await pull_and_upsert(db, since)
        stats = await reclassify(db, args.limit_classify)
        total = (await db.execute(select(FederalAction))).scalars().all()
        relevant_total = sum(1 for a in total if a.ce_relevant)
    print(f"\nDone. classified={stats['classified']} newly-relevant={stats['relevant']}")
    print(f"Table now: {len(total)} rows, {relevant_total} ce_relevant=True")


if __name__ == "__main__":
    asyncio.run(main())
