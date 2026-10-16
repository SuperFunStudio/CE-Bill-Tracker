"""Curated reclassification for building deconstruction / C&D scope (2026-10-15 audit).

A prod sweep for deconstruction language (selective demolition, pre-demolition audit, PEMD diagnostic,
分別解体, Rückbau, ...) found in-scope provisions the classifier missed. The FR laws are omnibus
climate/energy acts: Haiku judged them off one unrelated article (vehicle CO2, building energy), so a
re-run of Haiku would likely repeat the miss. These values are hand-set at needs_review=true, with a
classification_changes row per bill so the change is diffable.

  - FR Loi Climat et Résilience (2021-1104): rewrites CCH L.126-34, the legal basis of the PEMD
    diagnostic (pre-demolition/renovation inventory of products/materials, reuse first).
  - FR LTECV (2015-992): 70% material recovery of construction-sector waste by 2020, biowaste source
    separation, landfill reduction targets.
  - NE LB-217 / LB-607: tire-grant bills that also fund deconstruction of abandoned buildings for
    material recovery -> add the `construction` material (relevance unchanged).

Dry run by default; --commit writes. --dsn points at the target DB (prod via the Cloud SQL proxy).
"""
import argparse
import asyncio
import json

import asyncpg

RUN_ID = "reclassify_deconstruction_2026-10-15"

FLIPS = {
    107782: dict(
        conf=0.85, materials=["construction"], instruments=["other", "labeling"], urgency="medium",
        summary="Omnibus climate law; it rewrites CCH L.126-34, requiring building owners to "
                "carry out a products/materials/waste diagnostic (PEMD) before demolition or major "
                "renovation, prioritising reuse of components - the legal basis for France's "
                "deconstruction-over-demolition regime (implemented by Décrets 2021-821/822)."),
    107783: dict(
        conf=0.8, materials=["construction", "organics", "plastic_packaging"],
        instruments=["other", "organics_diversion"], urgency="low",
        summary="Energy-transition law whose waste title sets national circular-economy targets: 70% "
                "material recovery of construction and public-works waste by 2020, generalised source "
                "separation of biowaste, landfill reduction of 30%/50% by 2020/2025, and the "
                "single-use plastic bag ban."),
}
ADD_CONSTRUCTION = [83413, 81674]


def _snap(r) -> dict:
    return {
        "ce_relevant": r["ce_relevant"], "confidence_score": r["confidence_score"],
        "instrument_type": r["instrument_type"],
        "instrument_types": json.loads(r["instrument_types"]) if r["instrument_types"] else None,
        "material_categories": json.loads(r["material_categories"]) if r["material_categories"] else None,
        "needs_review": bool(r["needs_review"]),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    c = await asyncpg.connect(args.dsn, ssl=False)
    ids = list(FLIPS) + ADD_CONSTRUCTION
    rows = {r["id"]: r for r in await c.fetch(
        "SELECT id, state, bill_number, ce_relevant, confidence_score, instrument_type, instrument_types,"
        " material_categories, needs_review FROM bills WHERE id = ANY($1::int[])", ids)}

    plan = []
    for bid, f in FLIPS.items():
        r = rows[bid]
        new = {"ce_relevant": True, "confidence_score": f["conf"], "instrument_type": f["instruments"][0],
               "instrument_types": f["instruments"], "material_categories": f["materials"], "needs_review": True}
        plan.append((bid, r, new, f))
    for bid in ADD_CONSTRUCTION:
        r = rows[bid]
        old = _snap(r)
        mats = old["material_categories"] or []
        if "construction" in mats:
            continue
        new = {**old, "material_categories": mats + ["construction"], "needs_review": True}
        plan.append((bid, r, new, None))

    for bid, r, new, _ in plan:
        print(f"{r['state']} {r['bill_number']} ({bid})\n   old {_snap(r)}\n   new {new}")
    if not args.commit:
        print("\n(dry run - re-run with --commit to write)")
        return

    async with c.transaction():
        for bid, r, new, f in plan:
            await c.execute(
                "UPDATE bills SET ce_relevant=$2, confidence_score=$3, instrument_type=$4,"
                " instrument_types=$5::jsonb, material_categories=$6::jsonb, needs_review=true,"
                " urgency=COALESCE($7, urgency), ai_summary=COALESCE($8, ai_summary),"
                " policy_stance=CASE WHEN $8::text IS NULL THEN policy_stance ELSE 'advances' END,"
                " updated_at=now() WHERE id=$1",
                bid, new["ce_relevant"], new["confidence_score"], new["instrument_type"],
                json.dumps(new["instrument_types"]), json.dumps(new["material_categories"]),
                f["urgency"] if f else None, f["summary"] if f else None)
            await c.execute(
                "INSERT INTO classification_changes (bill_id, run_id, old_value, new_value)"
                " VALUES ($1, $2, $3::jsonb, $4::jsonb)",
                bid, RUN_ID, json.dumps(_snap(r)), json.dumps(new))
    print(f"\nUPDATED {len(plan)} bills (run_id={RUN_ID}).")


if __name__ == "__main__":
    asyncio.run(main())
