"""Exercise the router's illustration-vs-filter lever on purpose-built questions.

The lever never fires on real dogfood traffic (shadow report: 0/10) — not because it's broken, but
because nobody has asked an "X like Y" question yet. This probe feeds it the shape it's built for and
shows, per question: (1) the router's role split (which slugs are FILTERS vs ILLUSTRATIONS), (2) what
the deterministic resolver extracts (everything as a filter), and (3) the retrieval totals both ways.

The lever's job: in "EPR bills on electronics like phones", `phones` is an EXAMPLE of the electronics
filter, not a second AND-filter. Deterministic treats phones as a hard filter → over-narrows. The
router demotes it to illustration → to_facets() drops it → retrieval stays on the broad electronics
set. So on these, we expect router_total >= det_total (the opposite of the region questions).

    DATABASE_URL=postgresql+asyncpg://signalscout:PW@127.0.0.1:5434/signalscout \
    ANTHROPIC_API_KEY=... \
    venv/Scripts/python.exe scripts/illustration_probe.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal  # noqa: E402
from app.api.research import _relevant_bills, _PAGE_SIZE  # noqa: E402
from app.api.research_facets import resolve_facets  # noqa: E402
from app.api.research_router import QueryRouter  # noqa: E402

# Each pair: an illustration-shaped question, and (where useful) its filter-shaped discriminator twin.
QUESTIONS = [
    "EPR bills on electronics like phones and laptops",
    "which bills cover laptops?",                                  # discriminator: laptops = FILTER
    "packaging deposit-return laws, for example bottles and cans",
    "textile take-back rules such as clothing and footwear",
    "recycled content mandates including for plastic bottles",
    "right to repair bills for electronics, e.g. smartphones",
]


def _slugs(f):
    return {"materials": f.material_slugs, "instruments": f.instrument_slugs,
            "products": f.product_slugs, "places": f.place_labels}


async def main():
    router = QueryRouter()
    async with AsyncSessionLocal() as db:
        for q in QUESTIONS:
            det = await resolve_facets(db, q)
            rf = await router.route(db, q)
            rfacets = rf.to_facets()

            _, det_total, det_strat = await _relevant_bills(db, q, page=1, page_size=_PAGE_SIZE)
            _, r_total, r_strat = await _relevant_bills(db, q, page=1, page_size=_PAGE_SIZE, facets=rfacets)

            illus = {"materials": rf.material_illustrations, "instruments": rf.instrument_illustrations,
                     "products": rf.product_illustrations}
            illus = {k: v for k, v in illus.items() if v}

            print("=" * 92)
            print(f"Q: {q}")
            print(f"   intent          : {rf.intent}")
            print(f"   DET   filters   : {_slugs(det)}")
            print(f"   ROUTER filters  : {_slugs(rfacets)}")
            print(f"   ROUTER illustr. : {illus or '(none — lever did not fire)'}")
            print(f"   retrieval        det={det_total:<5} [{det_strat}]")
            print(f"                    router={r_total:<5} [{r_strat}]")
            verdict = ("LEVER FIRED — examples demoted, filter stayed broad"
                       if illus else "no illustration detected")
            print(f"   >>> {verdict}   (Δtotal {r_total - det_total:+d})")
    print(f"\nrouter cache: {router.hits} hits / {router.misses} misses")


if __name__ == "__main__":
    asyncio.run(main())
