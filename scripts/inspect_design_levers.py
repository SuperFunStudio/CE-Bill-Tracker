"""Measure design-lever coverage in the already-extracted compliance_details.

Read-only. No schema change, no LLM calls. This is "step 0" before building the
design-principle synthesis pass: it answers "is the signal even there?" by scanning
the Sonnet-extracted compliance_details JSON (covered_products / producer_obligations /
exemptions / fees / reporting_requirements) for each design lever, and reports how many
EPR-relevant bills carry each one, with real example excerpts tagged to (state, bill).

The Sonnet extractions live in PROD (see scripts/push_bills_to_prod.py), so point this at
the production DB via the Cloud SQL Auth Proxy:

    cloud-sql-proxy --address 127.0.0.1 --port 5434 ce-bill-tracker:us-central1:signalscout-pg &
    python scripts/inspect_design_levers.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout"

Each lever is matched against the verbatim text we already stored, so every count is
traceable back to a bill + the exact source string (chain of custody is preserved even at
this measurement stage).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import defaultdict

import asyncpg

# ---------------------------------------------------------------------------
# Controlled lever vocabulary. Patterns are intentionally broad (this is a recall-
# oriented coverage probe, not the final extractor) but each match keeps its source
# string so a human can verify it. Keyed lever -> list of regex patterns.
# ---------------------------------------------------------------------------
LEVERS: dict[str, list[str]] = {
    "design_for_recycling": [
        r"recyclab", r"design(ed)? for recycl", r"readily recycl", r"non-?recyclable",
        r"mono-?material", r"recycle-?ready", r"compatib\w+ with .{0,20}recycl",
    ],
    "recycled_content": [
        r"recycled content", r"post-?consumer", r"\bpcr\b", r"recycled material",
        r"minimum .{0,15}recycled",
    ],
    "reuse_refill": [
        r"reusable", r"refillable", r"\brefill\b", r"\breuse\b", r"return(able)? .{0,15}retail",
        r"reusab",
    ],
    "repairability_durability": [
        r"\brepair", r"spare part", r"replacement part", r"parts pairing", r"right to repair",
        r"durabilit", r"product life", r"longevity", r"disassembl",
    ],
    "toxics_elimination": [
        r"\bpfas\b", r"per-? and polyfluoro", r"perfluoro", r"heavy metal", r"\blead\b",
        r"cadmium", r"mercury", r"bisphenol", r"phthalate", r"\btoxic", r"chemical of concern",
    ],
    "source_reduction": [
        r"source reduction", r"reduce .{0,15}packaging", r"packaging reduction",
        r"right-?siz", r"minimiz\w+ .{0,15}(packaging|material)", r"reduction target",
        r"plastic reduction",
    ],
    "labeling_marking": [
        r"label", r"chasing arrows", r"resin identification", r"disposal instruction",
        r"how2recycle", r"\bmarking\b", r"recyclability label",
    ],
    "compostability": [
        r"compostab", r"astm d ?6400", r"astm d ?6868", r"biodegrad", r"\bcompostable\b",
    ],
    "material_restriction": [
        r"\bban\b", r"\bbann?ed\b", r"prohibit", r"shall not (sell|distribute|offer)",
        r"may not (sell|distribute|offer)", r"expanded polystyrene", r"\beps\b",
        r"polystyrene", r"\bpvc\b", r"restricted material", r"phase-?out",
    ],
}

# compliance_details keys we scan, mapped to a coarse default obligation direction.
# (Refined per-match below; exemptions always read as "exempted".)
SOURCE_FIELDS = [
    "covered_products",
    "producer_obligations",
    "exemptions",
    "reporting_requirements",
    "producer_definition",
]

_COMPILED = {lever: [re.compile(p, re.IGNORECASE) for p in pats] for lever, pats in LEVERS.items()}


def _field_strings(details: dict, field: str) -> list[str]:
    """Return the field's content as a flat list of strings (it may be str or list)."""
    val = details.get(field)
    if val is None:
        return []
    if isinstance(val, str):
        return [val] if val.strip() else []
    if isinstance(val, list):
        return [str(x) for x in val if str(x).strip()]
    return [str(val)]


def _classify_obligation(text: str, source_field: str) -> str:
    low = text.lower()
    if source_field == "exemptions":
        return "exempted"
    if re.search(r"\b(ban|banned|prohibit|shall not|may not|phase-?out)\b", low):
        return "banned"
    if re.search(r"\b(minimum|at least|shall contain|must contain|required to contain)\b", low):
        return "required"
    if re.search(r"\b(bonus|malus|eco-?modulat|incentiv|reduced fee|fee reduction|discount)\b", low):
        return "rewarded"
    if re.search(r"\b(shall|must|require)\b", low):
        return "required"
    return "named"  # mentioned/covered but no clear directive in this excerpt


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True, help="Postgres DSN (prod, via the Cloud SQL proxy).")
    ap.add_argument("--examples", type=int, default=3, help="Example excerpts to show per lever.")
    args = ap.parse_args()

    conn = await asyncpg.connect(args.dsn)
    try:
        total_bills = await conn.fetchval("SELECT count(*) FROM bills")
        relevant = await conn.fetchval("SELECT count(*) FROM bills WHERE epr_relevant = true")
        analyzed = await conn.fetchval(
            "SELECT count(*) FROM bills WHERE epr_relevant = true AND compliance_details IS NOT NULL"
        )
        rows = await conn.fetch(
            "SELECT id, state, bill_number, policy_stance, compliance_details "
            "FROM bills WHERE epr_relevant = true AND compliance_details IS NOT NULL"
        )
    finally:
        await conn.close()

    # fees.structure distribution
    fee_structures: dict[str, int] = defaultdict(int)
    # lever -> set(bill ids), lever -> obligation_type -> count, lever -> [examples]
    lever_bills: dict[str, set] = defaultdict(set)
    lever_oblig: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    lever_examples: dict[str, list] = defaultdict(list)
    eco_mod_bills: set = set()

    for r in rows:
        details = r["compliance_details"]
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                continue
        if not isinstance(details, dict):
            continue

        fees = details.get("fees") or {}
        structure = (fees.get("structure") or "unspecified") if isinstance(fees, dict) else "unspecified"
        fee_structures[structure] += 1
        if structure == "eco_modulated":
            eco_mod_bills.add(r["id"])

        # Build (source_field, text) pairs, including the fee details blob.
        units: list[tuple[str, str]] = []
        for field in SOURCE_FIELDS:
            for s in _field_strings(details, field):
                units.append((field, s))
        if isinstance(fees, dict) and fees.get("details"):
            units.append(("fees", str(fees["details"])))

        for source_field, text in units:
            for lever, patterns in _COMPILED.items():
                if any(p.search(text) for p in patterns):
                    lever_bills[lever].add(r["id"])
                    oblig = _classify_obligation(text, source_field)
                    lever_oblig[lever][oblig] += 1
                    if len(lever_examples[lever]) < args.examples:
                        excerpt = text.strip()
                        if len(excerpt) > 180:
                            excerpt = excerpt[:177] + "..."
                        lever_examples[lever].append(
                            (r["state"], r["bill_number"], source_field, oblig, excerpt)
                        )

    # ---- Report -----------------------------------------------------------
    print("=" * 78)
    print("DESIGN-LEVER COVERAGE  (compliance_details scan, read-only)")
    print("=" * 78)
    print(f"  bills (total) ............ {total_bills}")
    print(f"  epr_relevant ............. {relevant}")
    print(f"  ...with compliance_details {analyzed}   <- analyzable corpus for this pass")
    if analyzed == 0:
        print("\n  No analyzable bills. Is this pointed at PROD? (local has empty compliance_details)")
        return

    print("\n  fees.structure distribution:")
    for struct, n in sorted(fee_structures.items(), key=lambda kv: -kv[1]):
        print(f"     {struct:<16} {n:>4}  ({n / analyzed:5.0%})")
    print(f"\n  bills with eco_modulated fees: {len(eco_mod_bills)}  ({len(eco_mod_bills)/analyzed:.0%})"
          "   <- the direct design-incentive signal")

    print("\n" + "-" * 78)
    print(f"  {'LEVER':<22}{'BILLS':>6}{'%':>6}   obligation split")
    print("-" * 78)
    for lever in LEVERS:
        n = len(lever_bills[lever])
        pct = n / analyzed if analyzed else 0
        oblig = ", ".join(f"{k}:{v}" for k, v in sorted(lever_oblig[lever].items(), key=lambda kv: -kv[1]))
        print(f"  {lever:<22}{n:>6}{pct:>5.0%}   {oblig}")

    print("\n" + "=" * 78)
    print("  EXAMPLE EXCERPTS (chain of custody: state · bill · field · direction)")
    print("=" * 78)
    for lever in LEVERS:
        if not lever_examples[lever]:
            continue
        print(f"\n  [{lever}]")
        for state, bill_number, field, oblig, excerpt in lever_examples[lever]:
            print(f"    {state} {bill_number or '?':<10} ({field}/{oblig})")
            print(f"        \"{excerpt}\"")


if __name__ == "__main__":
    asyncio.run(main())
