"""Promote a hand-reviewed set of out-of-scope bills into the corpus (2026-10-23 review).

Came out of the butterfly coverage review: the diagram's hatched steps (cascades, organics) showed that
some law that belongs there was sitting at `ce_relevant = false`. Each row below was read and chosen by
hand; this is NOT a keyword net, so the list is explicit and keyed on (region, state, bill_number) to
stay portable across databases.

Two groups, two audit run_ids:

  * by_products — law on animal by-products and food/by-product recovery (the butterfly's cascade loop).
    Kenny's call: by-products are in scope. Tagged `adjacency = 'by_products'` for provenance, like the
    transboundary pass (scripts/backfill_adjacency.py). Deliberately left OUT of this group: the four
    EU translation-correction notices for Regulation 142/2011 (no content of their own), the
    meat-and-bone-meal-as-fuel export rules (energy recovery, see the energy_recovery bucket), state-aid
    decisions and pet-food contaminant limits.
  * manual — plain classifier misses, promoted as core (`adjacency` stays NULL):
      - CA AB-70 (2025, enacted): the enacted successor of AB-2514, which is in scope with the same
        digest. Text-starved, so it was judged on the description alone. It defines pyrolysis (excluded
        from the biomass-conversion credit) and adds pipeline biomethane from organic waste to the
        SB 1383 recovered-organic-product procurement targets.
      - NJ School Plastics Upcycling Grant Program (6 session/house copies): funding for collection and
        upcycling, an enabler under the "enablers of the circular economy" rule.
      - NJ A-776: relaxes the paper-bag ban for delivery orders and requires retailers to repurpose
        cardboard boxes. Text-starved (confidence 0.0, an abstention, not a judgment). Upcycling and
        repurposing are in scope (Kenny, 2026-10-23); a sweep of the out-of-scope pool for both found
        no other real candidates.

Every row: `ce_relevant = true, reviewed = true, needs_review = false`, plus the per-row field changes
below. Full old/new snapshot logged to `classification_changes` (one-query undo). Foreign rows that land
undated get a derived status_date, and is_amending is recomputed where the title changes or is unset.

DEFAULTS TO DRY RUN. Idempotent: rows already in scope are skipped.

    python scripts/promote_reviewed_scope_2026_10_23.py --dsn "postgresql://...@127.0.0.1:5462/signalscout"
    python scripts/promote_reviewed_scope_2026_10_23.py --dsn ... --commit
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.act_role import is_amending  # noqa: E402
from app.ingestion.law_dates import derive_status_date  # noqa: E402
from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402

RUN_IDS = {
    "by_products": "scope-by-products-2026-10-23",
    "manual": "manual-review-flip-2026-10-23",
}

# The parent implementing regulation came in with a junk EUR-Lex page title.
_R142_TITLE = ("COMMISSION REGULATION (EU) No 142/2011 of 25 February 2011 implementing Regulation (EC) "
               "No 1069/2009 of the European Parliament and of the Council laying down health rules as "
               "regards animal by-products and derived products not intended for human consumption")

# (region, state, bill_number) -> changes. `instrument` is prepended as the primary instrument;
# `materials` is applied only when the row has none.
PROMOTIONS: list[dict] = [
    # --- by-products ---------------------------------------------------------------------------------
    {"key": ("EU", "EU", "32011R0142"), "group": "by_products", "materials": ["organics"], "title": _R142_TITLE},
    {"key": ("EU", "EU", "32015R0009"), "group": "by_products", "materials": ["organics"]},
    {"key": ("EU", "EU", "32017R0786"), "group": "by_products", "materials": ["organics"]},
    {"key": ("EU", "EU", "32019R1177"), "group": "by_products", "materials": ["organics"]},
    {"key": ("EU", "EU", "32021R1891"), "group": "by_products", "materials": ["organics"]},
    {"key": ("EU", "EU", "32022R0384"), "group": "by_products", "materials": ["organics"]},
    {"key": ("EU", "EU", "32025R1377"), "group": "by_products", "materials": ["organics"]},
    {"key": ("PL", "PL", "DU/2018/1564"), "group": "by_products"},
    {"key": ("US", "DE", "HB-226"), "group": "by_products", "materials": ["organics"]},
    {"key": ("US", "DE", "HB-52"), "group": "by_products", "materials": ["organics"]},
    # --- manual classifier misses --------------------------------------------------------------------
    {"key": ("US", "CA", "AB-70"), "group": "manual", "instrument": "organics_diversion",
     "materials": ["organics", "biobased"], "replace_instruments": True},
    *({"key": ("US", "NJ", bn), "group": "manual", "instrument": "incentives"}
      for bn in ("A-3633", "A-4853", "A-5697", "S-1441", "S-1782", "S-4010")),
    {"key": ("US", "NJ", "A-776"), "group": "manual", "materials": ["paper_packaging"]},
]


def _as_list(v) -> list | None:
    return json.loads(v) if isinstance(v, str) else v


def _instruments(existing: list | None, primary: str | None, replace: bool) -> list | None:
    existing = _as_list(existing)
    if not primary:
        return existing
    out = [primary]
    if not replace:
        out += [i for i in existing or [] if isinstance(i, str) and i and i not in out]
    return out


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=None, help="Postgres DSN; defaults to app settings (local).")
    ap.add_argument("--commit", action="store_true", help="Write changes (default is dry run).")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Polish/EU titles on a cp1252 console

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    plan = []
    async with Session() as db:
        for p in PROMOTIONS:
            region, state, bn = p["key"]
            rows = (await db.execute(text(
                "SELECT id, region, state, bill_number, title, status, status_date, ce_relevant, confidence_score, "
                "       instrument_type, instrument_types, material_categories, needs_review, reviewed, adjacency, "
                "       is_amending "
                "FROM bills WHERE region = :r AND state = :s AND bill_number = :bn ORDER BY id"),
                {"r": region, "s": state, "bn": bn})).mappings().all()
            # A bill number can repeat across sessions (CA AB-2514 has a 2022 highway bill too). Only
            # the out-of-scope row(s) are candidates, and an ambiguous key is refused, not guessed.
            cands = [r for r in rows if not r["ce_relevant"]]
            if not rows:
                print(f"  MISSING  {region} {state} {bn}")
                continue
            if not cands:
                print(f"  skip     {region} {state} {bn} (already in scope)")
                continue
            if len(cands) > 1:
                print(f"  AMBIGUOUS {region} {state} {bn}: ids {[r['id'] for r in cands]} — refusing")
                continue
            plan.append((p, cands[0]))

    print(f"\n{len(plan)} rows to promote:")
    for p, r in plan:
        print(f"  [{p['group']:11}] {r['id']:>6} {r['region']:3} {r['state']:3} {r['bill_number']:14} "
              f"[{r['status']}] {(p.get('title') or r['title'] or '')[:72]}")

    if not plan or not args.commit:
        if plan:
            print(f"\n(dry run — re-run with --commit to write. run_ids={RUN_IDS})")
        await engine.dispose()
        return

    now = datetime.now(timezone.utc)
    async with Session() as db:
        for p, r in plan:
            title = p.get("title") or r["title"]
            instruments = _instruments(r["instrument_types"], p.get("instrument"), p.get("replace_instruments", False))
            materials = _as_list(r["material_categories"]) or p.get("materials", _as_list(r["material_categories"]))
            amending = is_amending(title, region=r["region"], state=r["state"]) \
                if (p.get("title") or r["is_amending"] is None) else r["is_amending"]
            adjacency = "by_products" if p["group"] == "by_products" else r["adjacency"]
            fields = ("ce_relevant", "title", "instrument_type", "instrument_types", "material_categories",
                      "needs_review", "reviewed", "adjacency", "is_amending")
            old = {k: r[k] for k in fields}
            new = {"ce_relevant": True, "title": title,
                   "instrument_type": (instruments or [r["instrument_type"]])[0], "instrument_types": instruments,
                   "material_categories": materials, "needs_review": False, "reviewed": True,
                   "adjacency": adjacency, "is_amending": amending}
            await db.execute(text(
                "UPDATE bills SET ce_relevant = true, title = :title, instrument_type = :it, "
                "instrument_types = CAST(:its AS jsonb), material_categories = CAST(:mats AS jsonb), "
                "needs_review = false, reviewed = true, adjacency = :adj, is_amending = :am, updated_at = now() "
                "WHERE id = :id"),
                {"title": title, "it": new["instrument_type"], "its": json.dumps(instruments),
                 "mats": json.dumps(materials), "adj": adjacency, "am": amending, "id": r["id"]})
            if r["region"] != "US" and r["status_date"] is None:
                d = derive_status_date(r["bill_number"], title)
                if d is not None:
                    await db.execute(text("UPDATE bills SET status_date = :d WHERE id = :id"), {"d": d, "id": r["id"]})
                    new["status_date"] = str(d)
            await db.execute(text(
                "INSERT INTO classification_changes (bill_id, run_id, old_value, new_value, created_at) "
                "VALUES (:bid, :rid, CAST(:old AS jsonb), CAST(:new AS jsonb), :ts)"),
                {"bid": r["id"], "rid": RUN_IDS[p["group"]], "old": json.dumps(old, default=str),
                 "new": json.dumps(new, default=str), "ts": now})
        await db.commit()

    print(f"\nPROMOTED {len(plan)} rows. Audit run_ids={RUN_IDS}.")
    print("Undo: restore old_value per bill from classification_changes for these run_ids, then delete those rows.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
