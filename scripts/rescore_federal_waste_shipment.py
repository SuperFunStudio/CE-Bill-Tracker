"""Rescore federal_actions that the pre-waste_shipment prompt rejected.

Why this is separate from backfill_federal_actions.py: that script only (re)classifies rows
where instrument_type IS NULL, i.e. rows predating the 3-axis schema. Prod already has full
3-axis coverage, so it will classify ONLY newly-inserted rows and will silently leave behind
every action the old prompt rejected under its "trade determinations / tariff actions are noise"
rule — which is exactly the population the waste_shipment scope fix was written to rescue.

This targets that population directly: rows currently ce_relevant=False whose title or abstract
carries waste-shipment vocabulary. Small and cheap (tens of rows, not the whole table), so it
runs well inside a normal Haiku budget.

Run against prod via the Cloud SQL Auth Proxy:
    DATABASE_URL="postgresql://signalscout:PW@127.0.0.1:5436/signalscout" \
        python scripts/rescore_federal_waste_shipment.py [--dry-run] [--limit N]
"""
import argparse
import asyncio
import re

import structlog
from sqlalchemy import select

from app.classification.federal_classifier import FederalClassifier
from app.database import AsyncSessionLocal
from app.models import FederalAction

log = structlog.get_logger()

# Vocabulary of the axis the old prompt was blind to. Prefix-y and deliberately over-inclusive —
# the classifier is the precision layer, this only decides who gets a second look.
WASTE_SHIPMENT_VOCAB = re.compile(
    r"\b(black mass|waste and scrap|scrap metal|scrap tire|secondary material|"
    r"e-scrap|e-waste|electronic waste|used electronics|recovered (?:material|fiber|paper|plastic)|"
    r"transboundary|basel convention|export control|allocation order|defense production act|"
    r"section 232|section 301|recyclable material)s?\b",
    re.IGNORECASE,
)


def _matches(action: FederalAction) -> bool:
    abstract = (action.raw_data or {}).get("abstract", "") or "" if action.raw_data else ""
    return bool(WASTE_SHIPMENT_VOCAB.search(f"{action.title or ''} {abstract}"))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="list candidates, spend no Haiku calls")
    ap.add_argument("--limit", type=int, default=None, help="cap rows rescored")
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(select(FederalAction).where(FederalAction.ce_relevant.is_(False)))
        ).scalars().all()
        targets = [a for a in rows if _matches(a)]
        if args.limit:
            targets = targets[: args.limit]
        print(f"{len(rows)} ce_relevant=False rows; {len(targets)} match waste-shipment vocab.")
        if args.dry_run:
            for a in targets:
                print(f"  {a.published_date} {a.federal_register_document_number} {(a.title or '')[:80]}")
            return

        clf = FederalClassifier()
        sem = asyncio.Semaphore(8)

        async def run(action):
            async with sem:
                abstract = (action.raw_data or {}).get("abstract", "") if action.raw_data else ""
                try:
                    return action, await clf.classify(
                        title=action.title or "", agency=action.agency or "",
                        action_type=action.action_type or "", abstract=abstract or "",
                    )
                except Exception as e:
                    log.error("rescore_failed",
                              doc=action.federal_register_document_number, error=str(e))
                    return None

        promoted = []
        for r in await asyncio.gather(*[run(a) for a in targets]):
            if not r:
                continue
            action, fr = r
            if not fr.in_scope:
                continue  # leave the row as-is; the old verdict stands
            action.ce_relevant = True
            action.preemption_risk = fr.preemption_risk
            action.friction_type = fr.friction_type
            action.instrument_type = fr.instrument_type
            action.ai_summary = fr.summary
            action.material_categories = fr.material_categories
            promoted.append(action)
        await db.commit()

    print(f"\nRescored {len(targets)}; promoted {len(promoted)} to ce_relevant=True:")
    for a in promoted:
        print(f"  {a.published_date} {a.federal_register_document_number} "
              f"[{a.instrument_type}/{a.preemption_risk}] {(a.title or '')[:70]}")


if __name__ == "__main__":
    asyncio.run(main())
