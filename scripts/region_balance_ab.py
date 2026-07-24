"""Read-only A/B for the relevance-gated region-balanced deep read (_balance_read_set).

For each corpus-wide question, run _relevant_bills twice against PROD — arm A (balance OFF, today's
behaviour) and arm B (balance ON) — and compare the COUNTRY composition of the top-_DEEP_READ read set
(the bills the LLM would read). No LLM, no persistence, no writes: pure SELECTs, safe against prod.

Measures both things that matter:
  1. Does B put more genuinely-relevant non-US/EU law in front of the model? (composition shift)
  2. Does the relevance floor keep junk out? (every promoted bill is listed with its title + rank so a
     human can eyeball whether it's on-topic — the overcompensation check).

Run against PROD via the Cloud SQL proxy (127.0.0.1:5436):

    PW=$(gcloud secrets versions access latest --secret=SIGNALSCOUT_DB_PASSWORD --project=ce-bill-tracker)
    DATABASE_URL="postgresql://signalscout:$PW@127.0.0.1:5436/signalscout" \
        venv/Scripts/python.exe scripts/region_balance_ab.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal  # noqa: E402
from app.api.research import (  # noqa: E402
    resolve_facets, _relevant_bills, _DEEP_READ,
    _BALANCE_FLOOR_RATIO, _BALANCE_BUDGET,
)

OUT = Path(__file__).parent.parent / "data" / "exports" / "region_balance_ab.jsonl"

# Corpus-wide, topical, NOT place-scoped — so retrieval takes the RULE 1/3 text path where balancing
# engages. (A place-scoped question already IS the geography; balancing is intentionally skipped there.)
QUESTIONS = [
    "extended producer responsibility obligations for packaging",
    "recycled content requirements for plastic products",
    "electronics and e-waste take-back and collection obligations",
    "battery recycling collection and producer responsibility",
    "deposit return schemes for beverage containers",
    "eco-modulation of producer fees based on recyclability",
    "restrictions and bans on single-use plastics",
    "textile and clothing extended producer responsibility",
    "penalties and enforcement mechanisms in EPR laws",
    "compostable and biodegradable packaging standards",
    "right to repair and repairability requirements",
    "reuse and refill system mandates",
]

# EU bloc = the supranational 'eu' node plus member-state ISO segments, so "US + EU-bloc" is measured as
# one Western share and the question — are JP/CN/KR/IN/etc. represented? — is what stands out.
_EU_MEMBERS = {"eu", "fr", "de", "es", "it", "nl", "be", "se", "pl", "at", "dk", "fi", "ie",
               "pt", "gr", "cz", "hu", "ro", "sk", "si", "hr", "bg", "lt", "lv", "ee", "lu", "cy", "mt"}


def _country(r) -> str:
    c = getattr(r, "balance_country", None)
    if c:
        return c.lower()
    return (getattr(r.Bill, "region", None) or "??").lower()


def _bucket(c: str) -> str:
    if c in ("us", "usa"):
        return "US"
    if c in _EU_MEMBERS:
        return "EU-bloc"
    return "OTHER"


def _compose(rows) -> dict:
    countries = Counter(_country(r) for r in rows)
    buckets = Counter(_bucket(c) for c in (_country(r) for r in rows))
    return {"n": len(rows), "buckets": dict(buckets),
            "countries": dict(countries.most_common()),
            "non_us_eu": buckets["OTHER"], "distinct_countries": len(countries)}


async def ask_ab(db, q: str) -> dict:
    facets = await resolve_facets(db, q)
    geo = bool(facets.place_ids)
    a_rows, total, strat = await _relevant_bills(db, q, page=1, page_size=_DEEP_READ, facets=facets,
                                                 balance_regions=False)
    b_rows, _, _ = await _relevant_bills(db, q, page=1, page_size=_DEEP_READ, facets=facets,
                                         balance_regions=True)
    a_ids = {r.Bill.id for r in a_rows}
    promoted = [r for r in b_rows if r.Bill.id not in a_ids]
    dropped = [r for r in a_rows if r.Bill.id not in {r.Bill.id for r in b_rows}]
    prom = [{"region": (r.Bill.region or "?"), "country": _country(r),
             "ref": f"{r.Bill.state or ''} {r.Bill.bill_number or '?'}".strip(),
             "title": (r.Bill.title or "")[:70], "rank": round(getattr(r, "balance_rank", 0.0) or 0.0, 4)}
            for r in promoted]
    engaged = strat.startswith("text") and not geo
    return {"q": q, "strategy": strat, "geo_scoped": geo, "engaged": engaged, "total": total,
            "A": _compose(a_rows), "B": _compose(b_rows),
            "promoted_n": len(promoted), "dropped_n": len(dropped), "promoted": prom}


async def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    results = []
    async with AsyncSessionLocal() as db:
        for q in QUESTIONS:
            rec = await ask_ab(db, q)
            results.append(rec)
            b = rec["B"]["buckets"]
            a = rec["A"]["buckets"]
            print(f"[{'ENGAGED' if rec['engaged'] else 'skipped'}] {q[:52]:52} | "
                  f"A other={rec['A']['non_us_eu']:2d} B other={rec['B']['non_us_eu']:2d} "
                  f"(+{rec['promoted_n']}) | A={a} B={b}", flush=True)
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in results), encoding="utf-8")

    eng = [r for r in results if r["engaged"]]
    tot_a = sum(r["A"]["non_us_eu"] for r in eng)
    tot_b = sum(r["B"]["non_us_eu"] for r in eng)
    tot_read = sum(r["A"]["n"] for r in eng)
    tot_prom = sum(r["promoted_n"] for r in eng)
    print("\n==== SUMMARY (engaged questions only) ====")
    print(f"engaged questions      : {len(eng)}/{len(results)}")
    print(f"floor ratio / budget   : {_BALANCE_FLOOR_RATIO} / {_BALANCE_BUDGET}")
    print(f"non-US/EU read slots   : A={tot_a}  ->  B={tot_b}  (+{tot_b - tot_a})")
    if tot_read:
        print(f"non-US/EU share of read: A={tot_a / tot_read:.1%}  ->  B={tot_b / tot_read:.1%}")
    print(f"total bills promoted   : {tot_prom}")
    # Promotion country spread (what regions did the floor actually let in?)
    spread = Counter()
    for r in eng:
        for p in r["promoted"]:
            spread[p["country"]] += 1
    print(f"promotions by country  : {dict(spread.most_common())}")


if __name__ == "__main__":
    asyncio.run(main())
