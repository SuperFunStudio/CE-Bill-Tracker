"""Mine the in-scope `other` bucket: fix mislabels, and size up new-instrument candidates.

The `other` instrument_type is the catch-all for in-scope circular-economy bills whose mechanism
maps to no named instrument. Over time it accumulates two kinds of bill worth acting on:

  1. MISLABELS — bills that actually belong to an existing named instrument (epr, deposit_return,
     right_to_repair, recycled_content, incentives, labeling, preemption). This script re-runs the
     Haiku classifier and promotes those. ADDITIVE ONLY: it only ever rewrites instrument_type to a
     concrete named instrument; it never clears relevance or touches any other field. Never demotes
     into the un-tracked buckets (other/budget/chemical_restriction).

  2. EMERGENT CLUSTERS — patterns big enough to graduate into their own instrument_type (the path
     `incentives` took; see scripts/reclassify_incentives.py). This script does NOT invent new
     instruments — that's a taxonomy change touching the classifier enum + the frontend filter
     lists. Instead it keyword-clusters whatever stays `other` and prints counts, so the decision
     about which clusters to graduate is made on real data.

Classifies on title+description (enough to spot the lever) — no bill-text fetch. Idempotent.
Defaults to DRY RUN.

Run:
    python scripts/reclassify_other.py                 # dry run (local): mislabel preview + cluster report
    python scripts/reclassify_other.py --commit
    python scripts/reclassify_other.py --commit --dsn "postgresql://...@127.0.0.1:55432/signalscout"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.haiku_classifier import HaikuClassifier  # noqa: E402
from app.classification.keywords import KEYWORDS_PATH  # noqa: E402
from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402

CONCURRENCY = 8

# Promote only into instruments the product actually tracks + surfaces in the filters
# (see INSTRUMENT_TYPES in dashboard-next/.../BillFilters.tsx). Never write the un-tracked
# buckets — keeping a bill as `other` is strictly better than burying it in budget/chemical.
PROMOTABLE = {"epr", "deposit_return", "right_to_repair", "recycled_content",
              "incentives", "labeling", "preemption"}

# Ceremonial bills (resolutions, designations) carry no mechanism — leave them as `other`.
_RESO_PREFIX = ("HR", "SR", "HJR", "SJR", "HCR", "SCR", "HJM", "SJM", "HJ", "SJ", "HM", "SM")
_CEREMONIAL = re.compile(r"\b(commending|honoring|recognizing|designat\w*|awareness)\b|\bweek\b", re.I)

# Disposal/landfill bans have no dedicated keyword group yet — match them locally so the cluster
# report can size the candidate. (reuse/refill, organics, resale, remanufacturing reuse the
# existing keyword groups loaded below.)
_DISPOSAL_BAN = re.compile(
    r"\b(landfill ban|disposal ban|may not (be )?dispos|prohibit\w* .{0,30}disposal|"
    r"ban\w* .{0,30}(landfill|disposal)|organics? (ban|disposal ban)|"
    r"waste reduction|source reduction|single[- ]use (ban|prohibit))\b", re.I)


def _is_ceremonial(r: dict) -> bool:
    bn = (r.get("bill_number") or "").upper().replace(" ", "-")
    if bn.split("-")[0] in _RESO_PREFIX:
        return True
    return bool(_CEREMONIAL.search(r.get("title") or ""))


def _load_cluster_patterns() -> dict[str, list[re.Pattern]]:
    """Keyword groups (plus the local disposal-ban set) used to bucket residual `other` bills."""
    kw = json.loads(KEYWORDS_PATH.read_text())

    def compile_group(*keys: str) -> list[re.Pattern]:
        return [re.compile(r"\b" + re.escape(t) + r"\b", re.I)
                for k in keys for t in kw.get(k, [])]

    return {
        "reuse_refill": compile_group("reuse_and_refill_keywords"),
        "resale_secondhand": compile_group("resale_and_secondhand_keywords"),
        "organics_food_waste": compile_group("organics_and_food_waste_keywords"),
        "remanufacturing": compile_group("remanufacturing_keywords"),
        "repairability_durability": compile_group("repairability_and_durability_keywords"),
        "digital_product_passport": compile_group("digital_product_passport_keywords"),
        "disposal_ban": [_DISPOSAL_BAN],
    }


def _cluster(row, patterns: dict[str, list[re.Pattern]]) -> list[str]:
    corpus = f"{row.title or ''} {row.description or ''}"
    return [name for name, pats in patterns.items() if any(p.search(corpus) for p in pats)]


async def _classify(sem, haiku, row) -> dict:
    async with sem:
        try:
            hr = await haiku.classify(state=row.state, bill_number=row.bill_number or "",
                                      title=row.title or "", description=row.description or "")
            return {"id": row.id, "state": row.state, "bill_number": row.bill_number,
                    "title": row.title or "", "old": row.instrument_type,
                    "new": hr.instrument_type, "conf": hr.confidence}
        except Exception as e:  # noqa: BLE001
            return {"id": row.id, "state": row.state, "bill_number": row.bill_number,
                    "title": row.title or "", "old": row.instrument_type, "new": None,
                    "error": str(e)}


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-conf", type=float, default=0.0,
                    help="Only promote mislabels at or above this classifier confidence.")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    sql = ("SELECT id, state, bill_number, title, description, instrument_type FROM bills "
           "WHERE ce_relevant = true AND instrument_type = 'other' "
           "ORDER BY state, bill_number" + (" LIMIT :lim" if args.limit else ""))
    async with Session() as db:
        rows = list((await db.execute(text(sql), {"lim": args.limit} if args.limit else {})).all())
    print(f"{len(rows)} in-scope `other` bills to re-examine.\n")

    sem = asyncio.Semaphore(CONCURRENCY)
    haiku = HaikuClassifier()
    results = await asyncio.gather(*(_classify(sem, haiku, r) for r in rows))
    by_id = {r.id: r for r in rows}

    errors = [r for r in results if r.get("new") is None]
    promote = [r for r in results
               if r.get("new") in PROMOTABLE and not _is_ceremonial(r)
               and (r.get("conf") or 0) >= args.min_conf]
    promote.sort(key=lambda r: (r["new"], r["state"] or "", r["bill_number"] or ""))

    # --- 1. Mislabel fixes ---------------------------------------------------
    print(f"=== MISLABELS: {len(promote)} `other` bills now map to a named instrument "
          f"({len(errors)} classify errors) ===")
    for new_type, cnt in Counter(r["new"] for r in promote).most_common():
        print(f"  other -> {new_type}: {cnt}")
    print()
    for r in promote:
        print(f"  {r['state']:3} {(r['bill_number'] or ''):10} "
              f"[other->{r['new']} conf={r.get('conf')}]  {r['title'][:48]}")

    # --- 2. Residual cluster report (new-instrument candidates) ---------------
    promoted_ids = {r["id"] for r in promote}
    residual = [by_id[r["id"]] for r in results
                if r["id"] not in promoted_ids and r.get("new") is not None]
    patterns = _load_cluster_patterns()
    cluster_counts: Counter = Counter()
    unclustered = 0
    for row in residual:
        names = _cluster(row, patterns)
        if names:
            cluster_counts.update(names)
        else:
            unclustered += 1
    print(f"\n=== RESIDUAL `other`: {len(residual)} bills — candidate new-instrument clusters "
          f"(bills can match more than one) ===")
    for name, cnt in cluster_counts.most_common():
        print(f"  {name:26} {cnt}")
    print(f"  {'(no cluster matched)':26} {unclustered}")
    print("\nClusters large enough to graduate become their own instrument_type the way "
          "`incentives` did:\n  classifier enum + prompt, INSTRUMENT_DISPLAY (utils.ts), "
          "INSTRUMENT_TYPES (BillFilters.tsx + Insights options).")

    if not args.commit:
        print("\n(dry run — re-run with --commit to write the mislabel fixes.)")
        await engine.dispose()
        return

    async with Session() as db:
        for r in promote:
            await db.execute(
                text("UPDATE bills SET instrument_type=:t, updated_at=now() WHERE id=:id"),
                {"t": r["new"], "id": r["id"]})
        await db.commit()
    print(f"\nUPDATED {len(promote)} bills out of `other` into a named instrument.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
