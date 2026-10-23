"""Backfill the `bills.adjacency` tag — energy_recovery candidate pass (waste-to-energy).

Waste-to-energy / incineration-for-power law is outside the circular-economy focus but a sizable share
of the climate-emissions challenge. Decision (2026-10-23): tag it so it can be switched on per client,
and keep it OUT of scope. See docs/SCOPE_FACET_AND_MATERIAL_NAVIGATION.md §4 (the term spec this
script implements).

A DETERMINISTIC keyword net (no LLM, one DB scan), so the run is diffable and reproducible:
  1. Candidates are `ce_relevant = false` rows with no adjacency yet. A row in scope on its own merits
     (an EPR law that mentions incineration) is never touched.
  2. Match when the title/description carries a STRONG waste-to-energy term (multilingual), or it's a
     renewable-portfolio bill that names solid waste / incineration. (--include-weak also matches stored
     full text that repeats energy recovery / co-incineration / co-processing WEAK_MIN times — noisy.)
  3. Guards drop: composting / anaerobic digestion (organics are core), biofuels / renewable fuel
     standards with no waste link, pyrolysis / gasification framed as chemical recycling — unless a
     strong term is in the title — and, always, nuclear, PFAS (the toxics pass owns it) and (first
     pass) medical / hazardous-waste incineration.
  4. --commit sets `adjacency = 'energy_recovery'`, `reviewed = true` (so refreshes never re-classify
     them) and leaves `ce_relevant = false`. Every change is logged to `classification_changes` under
     run_id `adjacency-energy-recovery-<date>`. Switching the bucket on later is one UPDATE on the tag.

Idempotent (tagged rows are no longer candidates). DEFAULTS TO DRY RUN.

Run:
    python scripts/backfill_energy_recovery.py                       # dry run (local DB)
    python scripts/backfill_energy_recovery.py --dsn "postgresql://...@127.0.0.1:5471/signalscout"
    python scripts/backfill_energy_recovery.py --commit --dsn "..."
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402

ADJACENCY = "energy_recovery"
WEAK_MIN = 3  # full-text mentions needed for a weak signal alone to count

# --- Strong terms: enough on their own in the title/description. Keyed by a short label so the dry
# run can report which term fired. -------------------------------------------------------------------
_STRONG_TERMS = {
    "waste-to-energy": r"waste[-\s]+to[-\s]+energy",
    "energy from waste": r"energy[-\s]+from[-\s]+waste",
    "refuse-derived fuel": r"refuse[-\s]+derived\s+fuel",
    "solid recovered fuel": r"solid\s+recovered\s+fuel",
    "waste incineration": r"(?:waste|refuse|garbage|trash)\s+incinerat|incinerat\w*\s+(?:of\s+)?(?:\w+\s+)?(?:waste|refuse)",
    "incinerator": r"\bincinerators?\b",
    "mass burn": r"\bmass[-\s]+burn",
    "landfill gas": r"landfill\s+gas",
    "valorización/valorização energética": r"valoriza[cç][ií][oó]n\s+energ[eé]tica|valoriza[cç][aã]o\s+energ[eé]tica",
    "incineración/incineração de residuos": r"incinera(?:ci[oó]n|[cç][aã]o)\s+de\s+res[ií]duos",
    "coprocesamiento": r"coprocesamiento|co-procesamiento",
    "combustible derivado de residuos": r"combustibles?\s+derivados?\s+de\s+res[ií]duos",
    "valorisation énergétique": r"valorisation\s+[ée]nerg[ée]tique",
    "incinération des déchets": r"incin[ée]ration\s+des\s+d[ée]chets",
    "combustibles solides de récupération": r"combustibles?\s+solides?\s+de\s+r[ée]cup[ée]ration",
    "energetische/thermische Verwertung": r"(?:energetische|thermische)n?\s+verwertung",
    "Müllverbrennung": r"m[üu]e?llverbrennung|abfallverbrennung",
    "Ersatzbrennstoff": r"ersatzbrennstoff",
    "termovalorizzatore": r"termovalorizza",
    "afvalverbranding": r"afvalverbranding",
    "sampah menjadi energi": r"sampah\s+menjadi\s+energi",
    "PLTSa": r"\bPLTSa\b|pembangkit\s+listrik\s+tenaga\s+sampah",
    "ごみ発電": r"ごみ発電",
    "熱回収": r"熱回収",
    "垃圾焚烧(发电)": r"垃圾焚烧",
}
_STRONG = {k: re.compile(v, re.IGNORECASE) for k, v in _STRONG_TERMS.items()}

# --- Weak signals: count in the stored full text; alone they need WEAK_MIN mentions. ---------------
_WEAK = re.compile(r"energy\s+recovery|co-?incinerat|co-?processing", re.IGNORECASE)

# Renewable-portfolio bills that make MSW / incineration an eligible resource (US state RPS bills).
_RPS = re.compile(r"renewable\s+(?:portfolio|energy\s+(?:standard|credit|resource))", re.IGNORECASE)
_RPS_WASTE = re.compile(r"municipal\s+solid\s+waste|solid\s+waste|incinerat|waste[-\s]+to[-\s]+energy",
                        re.IGNORECASE)

# --- Guards. Absolute ones always drop the row; the rest yield when a strong term sits in the TITLE
# (the law is squarely WtE, e.g. "Waste-to-Energy Act" that also mentions composting).
_ABSOLUTE_GUARDS = {"nuclear", "medical/hazardous incineration", "toxics (PFAS)"}
_GUARDS = {
    "organics (compost/AD)": re.compile(r"compost|anaerobic\s+digest", re.IGNORECASE),
    "biofuels/fuel standard": re.compile(r"biofuel|bio-?diesel|ethanol|renewable\s+fuel\s+standard"
                                         r"|sustainable\s+aviation\s+fuel|low\s+carbon\s+fuel", re.IGNORECASE),
    "nuclear": re.compile(r"nuclear|radioactive|spent\s+fuel", re.IGNORECASE),
    "chemical recycling": re.compile(r"advanced\s+recycling|chemical\s+recycling|recycling\s+technolog"
                                     r"|pyrolysis|gasification", re.IGNORECASE),
    # PFAS-incineration bans are a toxics measure — they belong to the deferred toxics pass.
    "toxics (PFAS)": re.compile(r"perfluoro|polyfluoro|\bpfas\b|forever\s+chemical", re.IGNORECASE),
    "medical/hazardous incineration": re.compile(r"medical\s+waste|biomedical|hazardous\s+waste",
                                                 re.IGNORECASE),
}


def classify(title: str, description: str, full_text: str, use_weak: bool = False) -> tuple[str | None, str]:
    """Return (matched_term_label, reason) or (None, why_skipped). The weak full-text signal is off by
    default: on prod (2026-10-23) all 6 of its matches were noise — waste-statistics formats, an IED
    forum decision, animal by-product cremation, a tourism BEMP — laws that list incineration in passing."""
    head = f"{title or ''}\n{description or ''}"
    title_strong = next((k for k, rx in _STRONG.items() if rx.search(title or "")), None)
    term = title_strong or next((k for k, rx in _STRONG.items() if rx.search(head)), None)
    if not term:
        if _RPS.search(head) and _RPS_WASTE.search(head):
            term = "renewable-portfolio + solid waste"
        elif use_weak and len(_WEAK.findall(full_text or "")) >= WEAK_MIN:
            term = f"weak x{len(_WEAK.findall(full_text or ''))} (energy recovery / co-incineration)"
    if not term:
        return None, "no term"
    for name, rx in _GUARDS.items():
        if (name in _ABSOLUTE_GUARDS or not title_strong) and rx.search(head):
            return None, f"guard: {name}"
    return term, "match"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=None, help="Postgres DSN; defaults to app settings (local).")
    ap.add_argument("--commit", action="store_true", help="Write changes (default is dry run).")
    ap.add_argument("--list", action="store_true", help="Print every matched row, not just the counts.")
    ap.add_argument("--include-weak", action="store_true",
                    help="Also match on repeated full-text mentions (noisy; off by default).")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    run_id = f"adjacency-energy-recovery-{date.today().isoformat()}"

    # One scan: out-of-scope, untagged rows, with their stored text when there is one (LEFT JOIN — many
    # out-of-scope US bills carry no text and are judged on title/description alone).
    sql = (
        "SELECT b.id, b.region, b.state, b.bill_number, b.title, b.description, b.ce_relevant, "
        "       b.confidence_score, b.instrument_type, b.instrument_types, b.needs_review, b.adjacency, "
        "       bt.text AS full_text "
        "FROM bills b LEFT JOIN bill_texts bt ON bt.bill_id = b.id "
        "WHERE b.ce_relevant = false AND b.adjacency IS NULL"
    )
    async with Session() as db:
        rows = list((await db.execute(text(sql))).mappings().all())

    matched, skipped = [], collections.Counter()
    for r in rows:
        term, why = classify(r["title"], r["description"], r["full_text"], use_weak=args.include_weak)
        if term:
            matched.append((r, term))
        elif why != "no term":
            skipped[why] += 1

    print(f"Scanned {len(rows)} out-of-scope, untagged rows; {len(matched)} match the energy_recovery net.\n")
    by_region = collections.Counter(r["region"] for r, _ in matched)
    by_term = collections.Counter(t if not t.startswith("weak") else "weak signal (full text)" for _, t in matched)
    print("By region:", ", ".join(f"{k} {v}" for k, v in by_region.most_common()))
    print("By term:  ", ", ".join(f"{k} {v}" for k, v in by_term.most_common()))
    print("Guarded out (had a term, dropped by a guard):", dict(skipped) or "none")
    if args.list or not args.commit:
        print()
        for r, t in sorted(matched, key=lambda m: (m[0]["region"] or "", m[0]["bill_number"] or "")):
            print(f"  {(r['region'] or ''):3} {(r['state'] or ''):6} {(r['bill_number'] or '')[:16]:16} "
                  f"[{t[:34]}] {(r['title'] or '')[:70]}")

    if not args.commit:
        print(f"\n(dry run — {len(matched)} rows would get adjacency='{ADJACENCY}', reviewed=true, and stay "
              f"ce_relevant=false. Re-run with --commit to write. run_id={run_id})")
        await engine.dispose()
        return

    now = datetime.now(timezone.utc)
    async with Session() as db:
        for r, term in matched:
            old = {k: r[k] for k in ("ce_relevant", "confidence_score", "instrument_type",
                                     "instrument_types", "needs_review", "adjacency")}
            new = {**old, "needs_review": False, "adjacency": ADJACENCY, "matched_term": term}
            await db.execute(text(
                "UPDATE bills SET adjacency = :adj, reviewed = true, needs_review = false, "
                "updated_at = now() WHERE id = :id"), {"adj": ADJACENCY, "id": r["id"]})
            await db.execute(text(
                "INSERT INTO classification_changes (bill_id, run_id, old_value, new_value, created_at) "
                "VALUES (:bid, :rid, CAST(:old AS jsonb), CAST(:new AS jsonb), :ts)"),
                {"bid": r["id"], "rid": run_id, "old": json.dumps(old, default=str),
                 "new": json.dumps(new, default=str), "ts": now})
        await db.commit()
    print(f"\nTAGGED {len(matched)} rows adjacency='{ADJACENCY}' (still out of scope). Audit run_id={run_id}.")
    print("Undo: restore old_value per bill from classification_changes for this run_id.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
