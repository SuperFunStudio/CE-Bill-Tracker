"""Run the /research/ask synthesis pipeline for one comparative question, once per region.

Motivation: the founder asked "what can the rest of the regions learn from the <X> bills?" live for
China, Japan, France, US. The shadow-router report shows the deterministic resolver scopes each of
those to ONLY that region's bills (China 40, Japan 113, France 122) — so the answer describes what is
IN that region, and never actually contrasts it against the others. This harness fires the SAME
question for every meaningful region so we can (a) read how the answers differ and (b) see the
scope/total each one retrieves — the evidence for whether "learn from X" needs a comparative
retrieval mode rather than a single-region filter.

Runs the real internals (resolve_facets → _relevant_bills → _passages_for → _deep_answer), no HTTP /
auth. Point DATABASE_URL at prod (via the Cloud SQL proxy) and set anthropic_api_key.

    DATABASE_URL=postgresql+asyncpg://signalscout:PW@127.0.0.1:5434/signalscout \
    ANTHROPIC_API_KEY=... \
    venv/Scripts/python.exe scripts/region_perspective_sweep.py --out sweep.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal  # noqa: E402
from app.api.research import (  # noqa: E402
    resolve_facets, _relevant_bills, _passages_for, _pack_material,
    _aggregates, _deep_answer, _scope_extra, _DEEP_READ, _PAGE_SIZE,
)

REGIONS = ["US", "EU", "FR", "JP", "UK", "CA", "CN"]
TEMPLATE = "what can the rest of the regions learn from the {name} bills?"
NAMES = {"US": "US", "EU": "EU", "FR": "French", "JP": "Japanese",
         "UK": "UK", "CA": "Canadian", "CN": "Chinese"}


async def one(region: str) -> dict:
    question = TEMPLATE.format(name=NAMES[region])
    async with AsyncSessionLocal() as db:
        facets = await resolve_facets(db, question)
        geo_extra = _scope_extra(facets)
        page_rows, total, strategy = await _relevant_bills(db, question, page=1, page_size=_PAGE_SIZE)
        read_rows, _, _ = await _relevant_bills(db, question, page=1, page_size=_DEEP_READ)
        terms = facets.meaningful_terms()
        passages = await _passages_for(db, [r.Bill.id for r in read_rows], terms)
        packed = _pack_material(read_rows, passages)
        agg_scoped = await _aggregates(db, geo_extra)
        agg_corpus = await _aggregates(db) if geo_extra else None
        scope = {"total": total, "strategy": strategy, "read": len(packed),
                 "jurisdiction": facets.place_labels, "reference": facets.reference_labels}
    answer = await _deep_answer(question, scope, agg_scoped, agg_corpus, packed)
    regions_read = sorted({r.Bill.region for r in read_rows})
    return {"region": region, "question": question, "total": total, "strategy": strategy,
            "places": facets.place_labels, "reference": facets.reference_labels,
            "regions_in_read_set": regions_read, "answer": answer}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="region_sweep.json")
    ap.add_argument("--regions", nargs="*", default=REGIONS)
    args = ap.parse_args()

    results = []
    for reg in args.regions:
        print(f"→ {reg} ...", flush=True)
        try:
            res = await one(reg)
            print(f"   total={res['total']} strategy={res['strategy']} "
                  f"places={res['places']} read_regions={res['regions_in_read_set']}")
            results.append(res)
        except Exception as e:  # noqa: BLE001
            print(f"   FAILED: {e}")
            results.append({"region": reg, "error": str(e)})

    Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {args.out} ({len([r for r in results if 'answer' in r])} answers)")


if __name__ == "__main__":
    asyncio.run(main())
