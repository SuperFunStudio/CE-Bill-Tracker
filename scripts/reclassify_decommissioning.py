"""Rescue durable-good / infrastructure END-OF-LIFE & DECOMMISSIONING bills that the classifier
previously dropped as out-of-scope.

Context: PA SB-349 (Act 44 of 2026), a solar-facility decommissioning + financial-assurance law,
was ingested but classified ce_relevant=false — the Haiku prompt didn't treat end-of-life /
decommissioning of durable products & infrastructure assets as a circular-economy angle. The prompt
now names that lens explicitly (see app/classification/haiku_classifier.py), with the material axis
as the noise gate (a bill is in only if a physical product / material stream is retired) and the
financial-assurance mechanism folded into "incentives".

This re-runs the classifier over the ce_relevant=false bills whose title/description smell like
end-of-life / decommissioning / take-back / stewardship, plus the SB-349 anchor, and reports which
now flip to relevant — with the material + instrument the material axis / prompt assign. The
biological/technical WING is derived, not stored (app.classification.cycles), so it's shown for
eyeballing but never written.

ADDITIVE: only ever promotes ce_relevant false->true and fills material/instrument on those rows;
never clears an existing relevant bill. Idempotent. Defaults to DRY RUN.

Run:
    python scripts/reclassify_decommissioning.py                 # dry run (local)
    python scripts/reclassify_decommissioning.py --commit
    python scripts/reclassify_decommissioning.py --dsn "postgresql://...@127.0.0.1:5462/signalscout"   # prod via proxy
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.cycles import wing_of  # noqa: E402
from app.classification.haiku_classifier import HaikuClassifier  # noqa: E402
from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402

CONCURRENCY = 8
ANCHOR_IDS = (104330,)  # PA SB-349 / Act 44 of 2026 — always re-examine even if it misses the net

# Candidate net: end-of-life / decommissioning / retirement of durable products & assets. Broad on
# purpose — the material axis (below) is the real gate. Human/medical "end-of-life options" and
# real-property abandonment fall out because they map to no canonical material.
_NET = (
    "%decommission%", "%end-of-life%", "%end of life%", "%take-back%", "%take back%",
    "%stewardship%", "%site restoration%", "%abandon%", "%retirement of%", "%dismantl%",
)


async def _classify(sem, haiku, row) -> dict:
    async with sem:
        try:
            hr = await haiku.classify(
                state=row.state or "", bill_number=row.bill_number or "",
                title=row.title or "", description=row.description or "",
                region=row.region or "US",
            )
            return {
                "id": row.id, "state": row.state, "bill_number": row.bill_number,
                "title": row.title or "", "status": row.status,
                "relevant": bool(hr.is_ce_relevant), "conf": hr.confidence,
                "materials": hr.material_categories or [], "instruments": hr.instrument_types or [],
                "stance": hr.stance, "urgency": hr.urgency, "reasoning": hr.reasoning,
            }
        except Exception as e:  # noqa: BLE001
            return {"id": row.id, "state": row.state, "bill_number": row.bill_number,
                    "title": row.title or "", "relevant": None, "error": str(e)}


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    like_clause = " OR ".join(f"lower(coalesce(title,'')) LIKE '{p}'" for p in _NET)
    sql = (
        "SELECT id, state, region, bill_number, title, description, status "
        "FROM bills WHERE ce_relevant = false "
        f"AND ((%s) OR id = ANY(:anchors)) " % like_clause
        + "ORDER BY (status='enacted') DESC, state, bill_number"
        + (" LIMIT :lim" if args.limit else "")
    )
    params: dict = {"anchors": list(ANCHOR_IDS)}
    if args.limit:
        params["lim"] = args.limit
    async with Session() as db:
        rows = list((await db.execute(text(sql), params)).all())
    print(f"{len(rows)} ce_relevant=false end-of-life/decommissioning candidates to re-examine.\n")

    sem = asyncio.Semaphore(CONCURRENCY)
    haiku = HaikuClassifier()
    results = await asyncio.gather(*(_classify(sem, haiku, r) for r in rows))

    promote = [r for r in results if r.get("relevant") is True]
    still_out = [r for r in results if r.get("relevant") is False]
    errors = [r for r in results if r.get("relevant") is None]
    promote.sort(key=lambda r: (r.get("status") != "enacted", r["state"] or "", r["bill_number"] or ""))

    print(f"=> {len(promote)} flip to RELEVANT ; {len(still_out)} stay out ; {len(errors)} errors\n")
    for r in promote:
        wing = wing_of(r["materials"], r["instruments"])
        flag = " <== SB-349 ANCHOR" if r["id"] in ANCHOR_IDS else ""
        print(f"  [{r.get('status','?'):12}] {r['state'] or '??':3} {(r['bill_number'] or ''):12} "
              f"conf={r['conf']:.2f} wing={wing:12} {r['instruments']} {r['materials']}{flag}")
        print(f"        {r['title'][:96]}")
        print(f"        -> {r['reasoning'][:110]}")

    if errors:
        print(f"\n  {len(errors)} errors:")
        for r in errors:
            print(f"    {r['state']} {r['bill_number']}: {r.get('error','')[:80]}")

    if not args.commit:
        print("\n(dry run — re-run with --commit to write. Only the RELEVANT flips above are written.)")
        await engine.dispose()
        return

    written = 0
    async with Session() as db:
        for r in promote:
            await db.execute(text(
                "UPDATE bills SET ce_relevant=true, confidence_score=:conf, "
                "material_categories=CAST(:mc AS jsonb), instrument_type=:it, "
                "instrument_types=CAST(:its AS jsonb), urgency=:urg, "
                "needs_review=true, updated_at=now() "
                "WHERE id=:id AND ce_relevant=false"),
                {"id": r["id"], "conf": r["conf"], "mc": json.dumps(r["materials"]),
                 "it": (r["instruments"] or ["other"])[0], "its": json.dumps(r["instruments"] or ["other"]),
                 "urg": r["urgency"]})
            written += 1
        await db.commit()
    print(f"\nUPDATED {written} bills -> ce_relevant=true (needs_review=true for a human spot-check).")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
