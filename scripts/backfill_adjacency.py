"""Backfill the `bills.adjacency` scope-provenance tag — transboundary pass.

Delivers the e-scrap recovery customer ask: transboundary / cross-border movement & import-export of
WASTE, SCRAP, and RECYCLABLE materials belongs in the default corpus, tagged so we can see it entered
via the transboundary net (not the core classifier). See docs/SCOPE_FACET_AND_MATERIAL_NAVIGATION.md §5.

What it does — a DETERMINISTIC, keyword-driven net (no LLM), so the run is diffable and reproducible:
  1. Find rows whose title/description match the transboundary net (see `_TRANSBOUNDARY`) AND that are
     currently `ce_relevant = false`. The net ONLY tags otherwise-excluded rows: a bill that is already
     in scope on its own merits stays untouched with `adjacency = NULL` (it's core, not adjacent).
  2. Carve-out (spec precedence: circular_override -> nuclear/tobacco/medical carve-out -> inclusion
     net): a row about nuclear / radioactive / medical waste or tobacco is SKIPPED unless it also
     carries a circular mechanism (recycling / recovery / reuse / EPR / decommissioning).
  3. For each surviving match: set `ce_relevant = true`, `adjacency = 'transboundary'`,
     `instrument_type = 'waste_shipment'` (prepended into `instrument_types`), `reviewed = true`,
     `needs_review = false`. Every change is logged to `classification_changes` (old/new full snapshot)
     under run_id `adjacency-backfill-transboundary-<date>` so the run is queryable and one-query undo.

Scope: transboundary ONLY. Toxics/PFAS (~690 rows) is a deliberately-separate later pass (it's big
enough to overshadow core circular legislation). This script is idempotent — a second run finds no
`ce_relevant = false` matches left to flip.

Requires migration 045 (the `adjacency` column). DEFAULTS TO DRY RUN.

Run:
    python scripts/backfill_adjacency.py                    # dry run (local DB)
    python scripts/backfill_adjacency.py --commit
    python scripts/backfill_adjacency.py --dsn "postgresql://...@127.0.0.1:55432/signalscout"  # prod tunnel, dry run
    python scripts/backfill_adjacency.py --commit --dsn "postgresql://...@127.0.0.1:55432/signalscout"
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.law_dates import derive_status_date  # noqa: E402
from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402

ADJACENCY = "transboundary"

# --- The transboundary net -------------------------------------------------------------------------
# A match needs a WASTE/SCRAP/RECYCLABLE token together with a MOVEMENT/TRADE token, OR one of a few
# standalone signal phrases. Requiring the waste token is what keeps ordinary import/export of goods,
# food, fuel, alcohol, or animal feed OUT — those carry "import"/"export" but no waste context, so they
# never match (e.g. "export of meat-and-bone meal as a fuel", "importation of alcoholic beverages").
_WASTE = r"(?:hazardous\s+)?(?:wastes?|scrap|recyclables?|secondary\s+materials?|e-?waste|end-of-life)"
_MOVEMENT = (r"transboundary|transfrontier|cross[-\s]?border|inter[-\s]?state|inter[-\s]?provincial"
             r"|import|export|shipment|movement|trade")

_TRANSBOUNDARY = re.compile(
    r"transboundary"
    r"|basel\s+convention"
    r"|waigani"
    r"|regulation\s+of\s+exports\s+and\s+imports"          # the AU Hazardous Waste series
    rf"|{_WASTE}\W+(?:\w+\W+){{0,4}}?(?:{_MOVEMENT})"       # waste ... movement (within a few words)
    rf"|(?:{_MOVEMENT})\W+(?:\w+\W+){{0,4}}?{_WASTE}",      # movement ... waste
    re.IGNORECASE,
)

# Toxics belong to the SEPARATE (deferred) toxics pass, not this transboundary one. A PFAS /
# microplastics bill that merely mentions "import of wastes" (e.g. VT H-650) is a chemical-restriction
# measure, not a waste-trade measure — defer it. Escape hatch: keep it if it ALSO carries a strong,
# unambiguous transboundary signal (a genuinely cross-border e-scrap bill that happens to name a
# chemical), so we don't lose a real transboundary bill to the toxics guard.
_TOXICS_DEFER = re.compile(r"perfluoro|polyfluoro|\bpfas\b|microplastic|forever\s+chemical", re.IGNORECASE)
_STRONG_TRANSBOUNDARY = re.compile(
    r"transboundary|basel|waigani|regulation\s+of\s+exports\s+and\s+imports"
    r"|(?:cross[-\s]?border|inter[-\s]?provincial|inter[-\s]?state)\s+movement"
    r"|scrap\s+(?:metal|trade)|e-?waste\s+export",
    re.IGNORECASE,
)

# Carve-out: these segments stay OUT (their own material-restriction / safety segments) ...
_CARVE_OUT = re.compile(r"nuclear|radioactive|spent\s+fuel|medical\s+waste|tobacco|cigarette|vaping",
                        re.IGNORECASE)
# ... UNLESS the measure also carries a circular mechanism, which overrides the carve-out.
_CIRCULAR_OVERRIDE = re.compile(
    r"recycl|reuse|re-use|reclaim|recover|remanufactur|refurbish|take[-\s]?back"
    r"|extended\s+producer|\bepr\b|deconstruct|decommission|circular\s+economy",
    re.IGNORECASE,
)


def _matches(title: str, description: str) -> bool:
    blob = f"{title or ''}\n{description or ''}"
    if not _TRANSBOUNDARY.search(blob):
        return False
    if _TOXICS_DEFER.search(blob) and not _STRONG_TRANSBOUNDARY.search(blob):
        return False  # chemical-restriction bill — belongs to the deferred toxics pass
    if _CARVE_OUT.search(blob) and not _CIRCULAR_OVERRIDE.search(blob):
        return False
    return True


def _new_instrument_types(existing: list | None) -> list[str]:
    """Prepend waste_shipment as the primary, preserving any other instruments the classifier found."""
    out = ["waste_shipment"]
    for it in existing or []:
        if isinstance(it, str) and it and it != "waste_shipment" and it not in out:
            out.append(it)
    return out


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=None, help="Postgres DSN; defaults to app settings (local).")
    ap.add_argument("--commit", action="store_true", help="Write changes (default is dry run).")
    ap.add_argument("--limit", type=int, default=None, help="Cap candidate rows scanned (debugging).")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    run_id = f"adjacency-backfill-transboundary-{date.today().isoformat()}"

    # Only ce_relevant=false rows: the net tags otherwise-EXCLUDED bills IN. Core bills stay adjacency
    # NULL. Pull candidates that at least mention a waste/movement-ish term to keep the scan cheap; the
    # precise net + carve-out are applied in Python so the logic lives in one auditable place.
    sql = (
        "SELECT id, region, state, bill_number, title, description, status, status_date, "
        "       ce_relevant, confidence_score, instrument_type, instrument_types, needs_review, adjacency "
        "FROM bills "
        "WHERE ce_relevant = false "
        "  AND (title ILIKE '%transbound%' OR title ILIKE '%waste%' OR title ILIKE '%scrap%' "
        "       OR title ILIKE '%export%' OR title ILIKE '%import%' OR title ILIKE '%basel%' "
        "       OR title ILIKE '%recyclable%' OR description ILIKE '%transbound%' "
        "       OR description ILIKE '%shipment of waste%' OR description ILIKE '%movement of%waste%') "
        "ORDER BY region, state, bill_number"
        + (" LIMIT :lim" if args.limit else "")
    )
    async with Session() as db:
        rows = list((await db.execute(text(sql), {"lim": args.limit} if args.limit else {})).mappings().all())

    matched = [r for r in rows if _matches(r["title"], r["description"])]
    matched.sort(key=lambda r: (r["region"] or "", r["state"] or "", r["bill_number"] or ""))

    print(f"Scanned {len(rows)} ce_relevant=false candidates; {len(matched)} match the transboundary net.\n")
    for r in matched:
        print(f"  {(r['region'] or ''):3} {(r['state'] or ''):6} {(r['bill_number'] or ''):14} "
              f"[{r['status'] or '-'}] {(r['title'] or '')[:70]}")

    if not matched:
        print("\nNothing to flip.")
        await engine.dispose()
        return

    if not args.commit:
        print(f"\n(dry run — {len(matched)} rows would be set ce_relevant=true, adjacency='{ADJACENCY}', "
              f"instrument_type='waste_shipment'. Re-run with --commit to write. run_id={run_id})")
        await engine.dispose()
        return

    now = datetime.now(timezone.utc)
    dated = 0
    async with Session() as db:
        for r in matched:
            old = {
                "ce_relevant": r["ce_relevant"],
                "confidence_score": r["confidence_score"],
                "instrument_type": r["instrument_type"],
                "instrument_types": r["instrument_types"],
                "needs_review": r["needs_review"],
                "adjacency": r["adjacency"],
            }
            new_types = _new_instrument_types(r["instrument_types"])
            new = {
                "ce_relevant": True,
                "confidence_score": r["confidence_score"],
                "instrument_type": "waste_shipment",
                "instrument_types": new_types,
                "needs_review": False,
                "adjacency": ADJACENCY,
            }
            await db.execute(
                text(
                    "UPDATE bills SET ce_relevant = true, adjacency = :adj, "
                    "instrument_type = 'waste_shipment', instrument_types = CAST(:its AS jsonb), "
                    "reviewed = true, needs_review = false, updated_at = now() WHERE id = :id"
                ),
                {"adj": ADJACENCY, "its": _dump(new_types), "id": r["id"]},
            )
            # Promotion pulls foreign rows into scope that the (already-run) date backfill never saw,
            # so they land permanently undated and show up as "N bills carry no date" in the /research
            # year aggregate. This run is exactly how 19 EU/CELEX rows did. Date them on the way in.
            if r["region"] != "US" and r["status_date"] is None:
                derived = derive_status_date(r["bill_number"], r["title"])
                if derived is not None:
                    await db.execute(
                        text("UPDATE bills SET status_date = :d WHERE id = :id"),
                        {"d": derived, "id": r["id"]},
                    )
                    dated += 1
            await db.execute(
                text(
                    "INSERT INTO classification_changes (bill_id, run_id, old_value, new_value, created_at) "
                    "VALUES (:bid, :rid, CAST(:old AS jsonb), CAST(:new AS jsonb), :ts)"
                ),
                {"bid": r["id"], "rid": run_id, "old": _dump(old), "new": _dump(new), "ts": now},
            )
        await db.commit()

    print(f"\nUPDATED {len(matched)} bills -> ce_relevant=true, adjacency='{ADJACENCY}', "
          f"instrument_type='waste_shipment'. Audit run_id={run_id}.")
    print("Undo: DELETE the classification_changes rows for this run_id and restore old_value per bill.")
    await engine.dispose()


def _dump(obj) -> str:
    import json
    return json.dumps(obj)


if __name__ == "__main__":
    asyncio.run(main())
