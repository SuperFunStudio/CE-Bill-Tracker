"""Digest the shadow-mode router-vs-deterministic comparisons captured on every /research/ask.

Each ask persists `research_turns.facets->'shadow_router'` = {intent, router facets, diff (facet-level),
results (bill-set delta vs what the user got), has_illustrations}. This reads those and prints (1)
aggregate rates and (2) the biggest divergences — the evidence base for deciding whether to flip
retrieval from the deterministic resolver to the router.

    # prod (via the Cloud SQL proxy on 5434):
    venv/Scripts/python.exe scripts/shadow_router_report.py \
        --dsn postgresql://signalscout:PW@127.0.0.1:5434/signalscout [--limit 40]

Two levels of "difference":
  - facet diff   : the router disagreed with the deterministic resolver on a hard filter (interpretation)
  - results diff : the retrieved bill set would actually differ (total changed, or the top page changed)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg  # noqa: E402


def _pg(dsn: str) -> str:
    return re.sub(r"^postgres(ql)?(\+asyncpg)?://", "postgresql://", dsn)


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--limit", type=int, default=30, help="how many top divergences to list")
    args = ap.parse_args()

    conn = await asyncpg.connect(_pg(args.dsn))
    rows = await conn.fetch(
        "SELECT question, created_at, facets->'shadow_router' AS sr "
        "FROM research_turns WHERE facets ? 'shadow_router' ORDER BY created_at DESC")
    await conn.close()

    turns = []
    for r in rows:
        sr = r["sr"]
        sr = json.loads(sr) if isinstance(sr, str) else sr
        if sr:
            turns.append((r["question"], sr))

    n = len(turns)
    if not n:
        print("No shadow-router data yet. Deploy, run some asks, then re-run this.")
        return

    facet_diff = [t for t in turns if t[1].get("diff")]
    def _results_changed(sr):
        res = sr.get("results") or {}
        return (res.get("det_total") != res.get("router_total")
                or res.get("top_only_deterministic") or res.get("top_only_router"))
    results_diff = [t for t in turns if _results_changed(t[1])]
    illus = [t for t in turns if t[1].get("has_illustrations")]

    intents = Counter(t[1].get("intent") for t in turns)
    facet_by_type = Counter()
    for _, sr in facet_diff:
        for k in (sr.get("diff") or {}):
            facet_by_type[k] += 1

    print("=" * 88)
    print(f"SHADOW ROUTER REPORT — {n} asks with shadow data")
    print("=" * 88)
    print(f"facet interpretation diff : {len(facet_diff):>4}/{n}  ({len(facet_diff)/n*100:.0f}%)  "
          f"— router disagreed on a hard filter")
    if facet_by_type:
        print("    by facet: " + ", ".join(f"{k}={v}" for k, v in facet_by_type.most_common()))
    print(f"RESULTS diff (bill set)   : {len(results_diff):>4}/{n}  ({len(results_diff)/n*100:.0f}%)  "
          f"— the retrieved set would actually change")
    print(f"illustrations detected    : {len(illus):>4}/{n}  ({len(illus)/n*100:.0f}%)  "
          f"— the 'electronics like phones' signal (deterministic can't)")
    print(f"intent distribution       : " + ", ".join(f"{k}={v}" for k, v in intents.most_common()))

    # rank divergences by how much the result set moved (top-page symmetric difference + |Δtotal|)
    def _impact(sr):
        res = sr.get("results") or {}
        moved = len(res.get("top_only_deterministic") or []) + len(res.get("top_only_router") or [])
        dt = abs((res.get("det_total") or 0) - (res.get("router_total") or 0))
        return (moved, dt)
    ranked = sorted(results_diff, key=lambda t: _impact(t[1]), reverse=True)[:args.limit]

    print(f"\nTOP {len(ranked)} DIVERGENCES (biggest result-set change first):")
    print("-" * 88)
    for q, sr in ranked:
        res = sr.get("results") or {}
        rt = sr.get("router") or {}
        print(f"\nQ: {q[:96]}")
        print(f"   det total={res.get('det_total')}   router total={res.get('router_total')} "
              f"[{res.get('router_strategy')}]   intent={sr.get('intent')}")
        print(f"   top-page: overlap={res.get('top_overlap')} "
              f"only_det={len(res.get('top_only_deterministic') or [])} "
              f"only_router={len(res.get('top_only_router') or [])}")
        if sr.get("diff"):
            print(f"   facet diff: {json.dumps(sr['diff'])}")
        illus_bits = []
        for kind in ("material_illustrations", "product_illustrations", "instrument_illustrations"):
            if rt.get(kind):
                illus_bits.append(f"{kind.split('_')[0]}={rt[kind]}")
        if illus_bits:
            print(f"   router illustrations (demoted from filters): {', '.join(illus_bits)}")

    print("\nRead: high RESULTS-diff % with sensible per-query changes = the router is ready to drive")
    print("retrieval. Spot-check the top divergences for wins (France scoped, illustrations demoted)")
    print("vs regressions before flipping /ask to router facets.")


if __name__ == "__main__":
    asyncio.run(main())
