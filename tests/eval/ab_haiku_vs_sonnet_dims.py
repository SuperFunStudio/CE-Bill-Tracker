"""A/B: Haiku vs Sonnet on dimension extraction, measured against the bills that already have a
Sonnet extraction (the v2 ground truth). Answers "how much quality do we lose with Haiku?" on the exact
task, so the model choice (and the Haiku-triage hybrid) is decided from numbers, not priors.

Method: for each bill with a stored `extraction_version` AND local full text, re-run extraction with
Haiku and compare its 8 dimension envelopes to the stored Sonnet ones. Sonnet is treated as reference.

  venv/Scripts/python.exe tests/eval/ab_haiku_vs_sonnet_dims.py \
      --dsn postgresql://postgres:dev@localhost:5432/signalscout [--limit 44] [--concurrency 6]

Metrics:
  - status agreement   — Haiku envelope status == Sonnet status (present/absent/not_applicable/missing)
  - present precision/recall (Sonnet = truth) — catches Haiku's "operative vs merely mentioned" over-trigger
  - grounding-fail rate — Haiku marks present with a source_excerpt that is NOT a verbatim substring of the
    bill text (the gate that would silently drop the extraction); compared to Sonnet's own rate
  - parse failures     — Haiku returned unparseable/empty JSON (truncation etc.)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import asyncpg  # noqa: E402

ENVELOPES = ("eco_modulation", "recycled_content", "penalties", "collection_targets",
             "pro_structure", "bans_restrictions", "fee_amounts", "labeling")
HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _status(env) -> str:
    return env.get("status", "missing") if isinstance(env, dict) else "missing"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _grounded(env, text_norm: str) -> bool:
    """A present envelope is grounded iff its source_excerpt is a verbatim substring of the bill text."""
    if not isinstance(env, dict):
        return False
    exc = _norm(env.get("source_excerpt", ""))
    return bool(exc) and exc in text_norm


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default="postgresql://postgres:dev@localhost:5432/signalscout")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()

    from app.classification.sonnet_extractor import SonnetExtractor
    haiku = SonnetExtractor(model=HAIKU_MODEL)

    conn = await asyncpg.connect(args.dsn)
    bills = await conn.fetch(
        """SELECT b.id, b.region, b.state, b.bill_number, b.title, b.compliance_details, bt.text AS full_text
           FROM bills b JOIN bill_texts bt ON bt.bill_id = b.id
           WHERE b.compliance_details ? 'extraction_version' AND bt.text IS NOT NULL
           ORDER BY b.region, b.id LIMIT $1""", args.limit)
    await conn.close()
    print(f"{len(bills)} ground-truth bills (regions: "
          f"{', '.join(f'{k}={v}' for k, v in Counter(b['region'] for b in bills).items())})\n")

    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.time()

    async def run(b):
        cd = b["compliance_details"]
        sonnet = json.loads(cd) if isinstance(cd, str) else cd
        async with sem:
            try:
                hr = await haiku.extract(state=b["state"], bill_number=b["bill_number"] or "",
                                         title=b["title"] or "", full_text=b["full_text"], region=b["region"])
                haiku_env = {e: getattr(hr, e) or {} for e in ENVELOPES}
                ok = bool(hr.raw_json)
            except Exception as e:  # noqa: BLE001
                print(f"  [fail] {b['region']}/{b['state']} {b['bill_number']}: {type(e).__name__}: {e}")
                return None
        return {"sonnet": sonnet, "haiku": haiku_env, "ok": ok, "text": _norm(b["full_text"]),
                "region": b["region"]}

    results = [r for r in await asyncio.gather(*(run(b) for b in bills)) if r]
    dt = time.time() - t0

    # ---- aggregate ----
    parse_fail = sum(1 for r in results if not r["ok"])
    per_env = {e: Counter() for e in ENVELOPES}          # (sonnet_status, haiku_status) -> n
    tp = fp = fn = 0                                       # present detection, Sonnet=truth
    haiku_ground_fail = haiku_present = son_ground_fail = son_present = 0
    recall_by_region = defaultdict(lambda: [0, 0])        # region -> [haiku_present∩son_present, son_present]

    for r in results:
        for e in ENVELOPES:
            ss, hs = _status(r["sonnet"].get(e)), _status(r["haiku"][e])
            per_env[e][(ss, hs)] += 1
            s_pres, h_pres = ss == "present", hs == "present"
            tp += s_pres and h_pres
            fp += h_pres and not s_pres
            fn += s_pres and not h_pres
            if s_pres:
                recall_by_region[r["region"]][1] += 1
                recall_by_region[r["region"]][0] += h_pres
            if h_pres:
                haiku_present += 1
                haiku_ground_fail += not _grounded(r["haiku"][e], r["text"])
            if s_pres:
                son_present += 1
                son_ground_fail += not _grounded(r["sonnet"].get(e), r["text"])

    total_cells = len(results) * len(ENVELOPES)
    agree = sum(n for e in ENVELOPES for (ss, hs), n in per_env[e].items() if ss == hs)

    print("=" * 84)
    print(f"HAIKU vs SONNET (ground truth) — {len(results)} bills, {dt:.0f}s, parse-fail={parse_fail}")
    print("=" * 84)
    print(f"{'dimension':<22}{'S-present':>10}{'H-present':>10}{'agree%':>9}{'false+':>8}{'false-':>8}")
    print("-" * 84)
    for e in ENVELOPES:
        c = per_env[e]
        sp = sum(n for (ss, _), n in c.items() if ss == "present")
        hp = sum(n for (_, hs), n in c.items() if hs == "present")
        ag = sum(n for (ss, hs), n in c.items() if ss == hs)
        falsep = sum(n for (ss, hs), n in c.items() if hs == "present" and ss != "present")
        falsen = sum(n for (ss, hs), n in c.items() if ss == "present" and hs != "present")
        print(f"{e:<22}{sp:>10}{hp:>10}{ag/len(results)*100:>8.0f}%{falsep:>8}{falsen:>8}")

    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    print("-" * 84)
    print(f"Overall status agreement: {agree}/{total_cells} ({agree/total_cells*100:.0f}%)")
    print(f"Present-detection vs Sonnet: precision={prec*100:.0f}%  recall={rec*100:.0f}%  "
          f"(tp={tp} fp={fp} fn={fn})")
    print(f"Grounding-fail (present w/ non-verbatim excerpt): "
          f"Haiku {haiku_ground_fail}/{haiku_present} ({haiku_ground_fail/max(haiku_present,1)*100:.0f}%)  "
          f"vs Sonnet {son_ground_fail}/{son_present} ({son_ground_fail/max(son_present,1)*100:.0f}%)")
    print("Present-recall by region (Haiku catches Sonnet's present-envelopes):")
    for reg, (hit, tot) in sorted(recall_by_region.items()):
        print(f"  {reg:<6} {hit}/{tot} ({hit/max(tot,1)*100:.0f}%)")
    print("\nRead: high false+ and low present-precision = Haiku over-triggers (mentioned != operative).")
    print("High grounding-fail = excerpts that would be dropped by the gate -> real recall lost.")


if __name__ == "__main__":
    asyncio.run(main())
