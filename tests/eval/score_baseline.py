"""Score a query-understanding resolver against tests/eval/router_golden.json.

Three modes, all graded the same way (slug F1 + per-facet role + intent + free_text), so baseline and
router are directly comparable:

  OFFLINE (no DB)   -- deterministic pure matchers; places unscored (need the jurisdiction table).
      venv/Scripts/python.exe tests/eval/score_baseline.py

  --dsn <DSN>       -- the real deterministic resolve_facets against a DB (scores places + reference).
      venv/Scripts/python.exe tests/eval/score_baseline.py --dsn postgresql://postgres:dev@localhost:5432/signalscout

  --router --dsn    -- the LLM router (app/api/research_router.py): scores illustration-vs-filter,
                       intent, and exclude/reference roles the deterministic resolver can't do.
      venv/Scripts/python.exe tests/eval/score_baseline.py --router --dsn <DSN>

The deterministic resolver has no intent field and no illustration role -> those columns are 0/"filter"
by construction. That gap is exactly what --router is measured on. category=follow-up cases need
prior-turn context and are excluded.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from app.api.research_facets import _match_materials, _match_instruments, _match_products  # noqa: E402

try:
    from app.api.research import _map_dimension, _trigger_is_illustrative  # noqa: E402
    HAVE_DIM = True
except Exception as e:
    _map_dimension, _trigger_is_illustrative, HAVE_DIM, _DIM_IMPORT_ERR = None, None, False, repr(e)

SLUG_FACETS = ("materials", "instruments", "products")


# ---------- normalized `got` shape: {facet: {slug: role}}, places {label: role}, dimensions set ----------
def _dim(q):
    """The dimension the deterministic RETRIEVAL would actually filter by — i.e. _map_dimension's hit
    minus the illustrative-aside guard RULE 2 applies, so the eval mirrors _relevant_bills (a dimension
    word that only appears inside a '...like X' example never becomes a filter)."""
    if not HAVE_DIM:
        return set()
    dim, trig = _map_dimension(q)
    if dim and _trigger_is_illustrative(q, trig):
        return set()
    return {dim} - {None}


def resolve_offline(q: str) -> dict:
    mats, _, s1 = _match_materials(q, q)
    insts, _, s2 = _match_instruments(q, s1)
    prods, _, s3 = _match_products(q, s2)
    return {"materials": {s: "filter" for s in mats}, "instruments": {s: "filter" for s in insts},
            "products": {s: "filter" for s in prods}, "dimensions": _dim(q),
            "places": {}, "free_text": s3.lower(), "intent": None, "have_places": False}


def resolve_from_facets(fac, q: str) -> dict:
    places = {lbl: "filter" for lbl in fac.place_labels}
    places.update({lbl: "reference" for lbl in fac.reference_labels})
    return {"materials": {s: "filter" for s in fac.material_slugs},
            "instruments": {s: "filter" for s in fac.instrument_slugs},
            "products": {s: "filter" for s in fac.product_slugs}, "dimensions": _dim(q),
            "places": places, "free_text": fac.free_text.lower(), "intent": None, "have_places": True}


def resolve_from_routed(rf, q: str) -> dict:
    def roles(filt, illus):
        d = {s: "filter" for s in filt}
        d.update({s: "illustration" for s in illus})
        return d
    places = {lbl: "filter" for lbl in rf.place_labels}
    places.update({lbl: "reference" for lbl in rf.reference_labels})
    places.update({lbl: "exclude" for lbl in rf.exclude_place_labels})
    return {"materials": roles(rf.material_slugs, rf.material_illustrations),
            "instruments": roles(rf.instrument_slugs, rf.instrument_illustrations),
            "products": roles(rf.product_slugs, rf.product_illustrations),
            "dimensions": set(rf.dimensions), "places": places,
            "free_text": rf.free_text.lower(), "intent": rf.intent, "have_places": True}


async def resolve_all_db(dsn: str, questions, use_router: bool) -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from app.api.research_facets import resolve_facets
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(dsn)
    out = {}
    try:
        if use_router:
            from app.api.research_router import QueryRouter
            router = QueryRouter()
            sem = asyncio.Semaphore(8)

            async def one(q):
                async with sem, AsyncSession(engine) as db:
                    return q, resolve_from_routed(await router.route(db, q), q)
            for q, r in await asyncio.gather(*(one(q) for q in questions)):
                out[q] = r
        else:
            async with AsyncSession(engine) as db:
                for q in questions:
                    out[q] = resolve_from_facets(await resolve_facets(db, q), q)
    finally:
        await engine.dispose()
    return out


# ---------- scoring ----------
def prf(expected: set, got: set) -> float:
    if not expected and not got:
        return 1.0
    tp = len(expected & got)
    p = tp / len(got) if got else (1.0 if not expected else 0.0)
    r = tp / len(expected) if expected else 1.0
    return 2 * p * r / (p + r) if (p + r) else 0.0


def score(cases, resolved):
    by_cat_f1 = defaultdict(list)
    by_cat_role = defaultdict(lambda: [0, 0])
    ft_ok = ft_total = intent_ok = intent_total = 0
    rows = []
    have_places = any(r["have_places"] for r in resolved.values())
    score_intent = any(r["intent"] is not None for r in resolved.values())

    for c in cases:
        if c.get("category") == "follow-up":
            continue
        exp, got = c["expect"], resolved[c["question"]]

        f1s = []
        for facet in SLUG_FACETS:
            f1s.append(prf({f["slug"] for f in exp.get(facet, [])}, set(got[facet])))
        if HAVE_DIM:
            f1s.append(prf(set(exp.get("dimensions", [])), got["dimensions"]))
        if have_places:
            f1s.append(prf({p["label"] for p in exp.get("places", [])}, set(got["places"])))
        case_f1 = sum(f1s) / len(f1s)
        by_cat_f1[c["category"]].append(case_f1)

        rc = rt = 0
        for facet in SLUG_FACETS:
            for f in exp.get(facet, []):
                rt += 1
                rc += int(got[facet].get(f["slug"]) == f["role"])
        if have_places:
            for p in exp.get("places", []):
                rt += 1
                rc += int(got["places"].get(p["label"]) == p["role"])
        by_cat_role[c["category"]][0] += rc
        by_cat_role[c["category"]][1] += rt

        inc = [t for t in exp.get("free_text_includes", []) if t.lower() not in got["free_text"]]
        exc = [t for t in exp.get("free_text_excludes", []) if t.lower() in got["free_text"]]
        if have_places or not exp.get("places"):
            ft_total += 1
            ft_ok += int(not inc and not exc)
        ft_note = "" if (not inc and not exc) else f"missing={inc} leaked={exc}"

        i_note = ""
        if score_intent:
            intent_total += 1
            hit = got["intent"] == exp["intent"]
            intent_ok += int(hit)
            i_note = f"intent={got['intent']}{'' if hit else '≠'+exp['intent']}"
        rows.append((c["id"], c["category"], case_f1, f"{rc}/{rt}", (ft_note + " " + i_note).strip()))

    return dict(by_cat_f1=by_cat_f1, by_cat_role=by_cat_role, ft=(ft_ok, ft_total),
                intent=(intent_ok, intent_total), rows=rows, have_places=have_places,
                score_intent=score_intent)


def report(mode, s):
    print("=" * 92)
    print(f"EVAL: {mode}  vs golden set")
    print("=" * 92)
    if not HAVE_DIM:
        print(f"[warn] dimension scoring OFF ({_DIM_IMPORT_ERR})")
    if not s["have_places"]:
        print("[note] places OFF (offline; pass --dsn)")
    if not s["score_intent"]:
        print("[note] intent OFF (deterministic resolver has no intent field)")
    print()
    print(f"{'case':<44}{'cat':<22}{'slugF1':>7}{'role':>7}  notes")
    print("-" * 92)
    for cid, cat, f1, role, note in s["rows"]:
        print(f"{cid:<44}{cat:<22}{f1:>7.2f}{role:>7}  {note}")

    print("\nPer-category  (slug-extraction F1 | role-accuracy):")
    print("-" * 92)
    for cat in sorted(s["by_cat_f1"]):
        f1_avg = sum(s["by_cat_f1"][cat]) / len(s["by_cat_f1"][cat])
        rcc, rtt = s["by_cat_role"][cat]
        rs = f"{rcc}/{rtt} ({rcc/rtt*100:.0f}%)" if rtt else "n/a"
        print(f"  {cat:<24} slugF1={f1_avg:>5.2f}   role={rs}")

    all_f1 = [f for lst in s["by_cat_f1"].values() for f in lst]
    arc = sum(v[0] for v in s["by_cat_role"].values())
    art = sum(v[1] for v in s["by_cat_role"].values())
    fo, ftt = s["ft"]
    io, it = s["intent"]
    ip = f"{io}/{it} ({io/it*100:.0f}%)" if it else "n/a (off)"
    print("-" * 92)
    print(f"  {'OVERALL':<24} slugF1={sum(all_f1)/len(all_f1):>5.2f}   "
          f"role={arc}/{art} ({arc/art*100:.0f}%)   free_text={fo}/{ftt}   intent={ip}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="DB DSN (via proxy) to score places too.")
    ap.add_argument("--router", action="store_true", help="Use the LLM router (implies --dsn).")
    args = ap.parse_args()
    if args.router and not args.dsn:
        ap.error("--router needs --dsn (the router resolves places against the DB)")

    with open(os.path.join(HERE, "router_golden.json"), encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]
    questions = [c["question"] for c in cases if c.get("category") != "follow-up"]

    if args.dsn:
        resolved = asyncio.run(resolve_all_db(args.dsn, questions, args.router))
        mode = "LLM router" if args.router else ("deterministic " + ("(local)" if ":5432" in args.dsn else "(dev proxy)"))
    else:
        resolved = {q: resolve_offline(q) for q in questions}
        mode = "deterministic (offline)"

    report(mode, score(cases, resolved))


if __name__ == "__main__":
    main()
