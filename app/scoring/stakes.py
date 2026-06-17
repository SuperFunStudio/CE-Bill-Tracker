"""Financial-stakes computation for a (company, enacted-law) pair.

This produces the "what's at stake" breakdown the Portfolio Exposure page leads with.
It is deliberately layered by data quality, and leads with the number that is grounded
in statute rather than estimated:

  1. PENALTY EXPOSURE  — civil penalty $/day from the bill's enforcement text. This is a
     real figure written into law, not a model output, so it anchors "what's at stake if
     you do nothing." (e.g. CA SB 54: $50,000/day per violation for large producers.)
  2. ANNUAL PROGRAM FEE — material tonnage × per-tonne rate. GROUNDED where a published
     schedule exists (CA SB 54 2027, Oregon CAA midpoint, PaintCare/MRC); otherwise a
     benchmark range flagged as an estimate. See app/scoring/ca_sb54_fees.py.
  3. PRO MEMBERSHIP    — one-time/annual registration fee to join the producer responsibility
     organization (from the bill's fee block).
  4. ECO-MODULATION LEVER — the annual $ swing between the cheapest and most-expensive
     published format for the company's materials. This is the design value prop made
     numeric: redesigning toward recyclable / mono-material formats moves the fee down.

Pure functions — no DB, no async. Caller supplies the company's matched materials with
tonnage. Every dollar figure carries a `grounded` flag and a citation so the UI never
renders an estimate as if it were a published number.
"""
from __future__ import annotations

import re

from app.scoring.ca_sb54_fees import (
    SCHEDULE_CITATION as CA_CITATION,
    category_rate_per_tonne,
)

# Confidence floor for benchmark (non-published) fee ranges.
_BENCHMARK_CONFIDENCE = 0.3
_GROUNDED_CONFIDENCE = 0.6  # published schedule, but state-apportioned proxy tonnage

# A producer only pays a state's EPR fees on material sold IN that state, but our company
# tonnage is a national revenue proxy. For CPG/packaging, sales track population closely
# enough to apportion by state population share — a crude but defensible scaler that keeps
# the fee from being the (wildly overstated) "national volume × one state's rate". Share of
# US population, 2024 Census estimates. States without an entry fall back to the mean (~2%).
_STATE_POPULATION_SHARE: dict[str, float] = {
    "CA": 0.117, "TX": 0.090, "FL": 0.068, "NY": 0.058, "PA": 0.039, "IL": 0.038,
    "OH": 0.035, "GA": 0.033, "NC": 0.033, "MI": 0.030, "NJ": 0.028, "VA": 0.026,
    "WA": 0.023, "AZ": 0.022, "TN": 0.021, "MA": 0.021, "IN": 0.020, "MO": 0.018,
    "MD": 0.018, "WI": 0.018, "CO": 0.017, "MN": 0.017, "SC": 0.016, "AL": 0.015,
    "LA": 0.014, "KY": 0.013, "OR": 0.013, "OK": 0.012, "CT": 0.011, "UT": 0.010,
    "NV": 0.009, "IA": 0.009, "AR": 0.009, "MS": 0.009, "KS": 0.009, "NM": 0.006,
    "NE": 0.006, "ID": 0.006, "WV": 0.005, "HI": 0.004, "NH": 0.004, "ME": 0.004,
    "RI": 0.003, "MT": 0.003, "DE": 0.003, "SD": 0.003, "ND": 0.002, "AK": 0.002,
    "VT": 0.002, "WY": 0.002, "DC": 0.002,
}
_DEFAULT_STATE_SHARE = 0.02

# Matches "$50,000/day", "$10,000 per day", "$1,000 per violation", etc.
_PENALTY_RE = re.compile(
    r"\$\s*([\d,]+)\s*(?:/|per\s+)(day|violation)", re.IGNORECASE
)

# Matches CA SB 54 specifically ("SB 54", "SB-54", "SB54") — the \b after 54 prevents
# false matches on bills that merely contain "54" (e.g. AB-1548, SB 543).
_CA_SB54_RE = re.compile(r"\bSB[\s-]?54\b", re.IGNORECASE)


def parse_penalty(penalties_text: str | None) -> dict | None:
    """Extract a structured $/day (or per-violation) figure from enforcement text.

    Returns {"amount_usd": float, "unit": "day"|"violation", "raw": str} or None.
    Prefers a per-day figure when both are present (it's the scarier, recurring one).
    """
    if not penalties_text:
        return None
    matches = _PENALTY_RE.findall(penalties_text)
    if not matches:
        return None
    # Prefer per-day over per-violation
    day = next((m for m in matches if m[1].lower() == "day"), None)
    chosen = day or matches[0]
    amount = float(chosen[0].replace(",", ""))
    return {"amount_usd": amount, "unit": chosen[1].lower(), "raw": penalties_text.strip()}


def _ca_fee_range(materials: list[dict]) -> dict | None:
    """Annual CA SB 54 fee range + eco-modulation lever for the matched materials.

    `materials` is a list of {"category": str, "tonnes": float|None}. Categories with
    no tonnage or not in the CA schedule are skipped.
    """
    low = high = 0.0
    best = worst = 0.0
    covered = False
    lever_notes: list[str] = []
    for m in materials:
        tonnes = m.get("tonnes")
        if not tonnes:
            continue
        rate = category_rate_per_tonne(m["category"])
        if rate is None:
            continue
        covered = True
        low += tonnes * rate["representative_per_tonne"]
        high += tonnes * rate["representative_high_per_tonne"]
        best += tonnes * rate["best_per_tonne"]
        worst += tonnes * rate["worst_per_tonne"]
        if rate["worst_per_tonne"] > rate["best_per_tonne"]:
            lever_notes.append(
                f"{m['category'].replace('_', ' ')}: "
                f"${rate['best_per_tonne']:,}/t ({rate['best_format']}) → "
                f"${rate['worst_per_tonne']:,}/t ({rate['worst_format']})"
            )
    if not covered:
        return None
    return {
        "annual_fee_low_usd": round(low),
        "annual_fee_high_usd": round(high),
        "annual_fee_grounded": True,
        "fee_basis": "CA SB 54 — published 2027 base fee schedule",
        "eco_modulation_swing_usd": round(worst - best),
        "eco_modulation_floor_usd": round(best),
        "eco_modulation_notes": lever_notes,
        "citation": CA_CITATION,
        "confidence": _GROUNDED_CONFIDENCE,
    }


def _generic_fee_range(compliance_details: dict, materials: list[dict]) -> dict | None:
    """Annual fee range from a bill's own fee block (non-CA).

    Grounded when the bill's fee_structure_source is a published schedule (e.g. Oregon's
    published_range_midpoint); otherwise an estimate band flagged as such.
    """
    fees = (compliance_details or {}).get("fees") or {}
    fee_per_ton = fees.get("fee_per_ton")
    source = fees.get("fee_structure_source") or "unknown"
    total_tonnes = sum(m["tonnes"] for m in materials if m.get("tonnes"))
    if not fee_per_ton or not total_tonnes:
        return None
    grounded = source in {"published_range_midpoint", "calrecycle_published",
                          "paintcare_published", "mrc_published"}
    mid = total_tonnes * float(fee_per_ton)
    # Published midpoints get a tight ±20% band; benchmarks get a wide ±50% to signal noise.
    spread = 0.20 if grounded else 0.50
    return {
        "annual_fee_low_usd": round(mid * (1 - spread)),
        "annual_fee_high_usd": round(mid * (1 + spread)),
        "annual_fee_grounded": grounded,
        "fee_basis": (
            "Published program rate" if grounded
            else "Benchmark estimate (no published schedule yet)"
        ),
        "eco_modulation_swing_usd": None,
        "eco_modulation_floor_usd": None,
        "eco_modulation_notes": [],
        "citation": fees.get("fee_notes"),
        "confidence": _GROUNDED_CONFIDENCE if grounded else _BENCHMARK_CONFIDENCE,
    }


def compute_stakes(
    bill_state: str,
    compliance_details: dict | None,
    matched_materials: list[dict],
    bill_number: str | None = None,
) -> dict:
    """Full financial-stakes breakdown for one (company, bill) pair.

    Args:
        bill_state: two-letter state code of the bill.
        compliance_details: the bill's compliance_details JSONB (fees, enforcement, …).
        matched_materials: [{"category": str, "tonnes": float|None}] — the company's
            materials that fall under this bill, with tonnage where known.
        bill_number: the bill's number, used to attach the CA SB 54 per-material schedule
            to the SB 54 program specifically (not every CA packaging-related law).

    Returns a dict with penalty / annual-fee / PRO / eco-modulation layers. Any layer may
    be None when the underlying data is absent — the UI hides empty layers.
    """
    cd = compliance_details or {}
    fees = cd.get("fees") or {}
    enforcement = cd.get("enforcement") or {}

    penalty = parse_penalty(enforcement.get("penalties"))

    # Apportion national proxy tonnage to this state before applying the state's rates.
    share = _STATE_POPULATION_SHARE.get(bill_state, _DEFAULT_STATE_SHARE)
    apportioned = [
        {"category": m["category"],
         "tonnes": (m["tonnes"] * share) if m.get("tonnes") else None}
        for m in matched_materials
    ]

    # Fee range: the CA SB 54 published per-material schedule attaches ONLY to SB 54 — the
    # one CA program that charges per-tonne packaging fees. Applying it to every CA bill that
    # merely lists a packaging material (recycled-content, labeling, etc.) would charge the
    # same physical packaging fee several times over. Every other bill uses its own fee block.
    is_ca_sb54 = bill_state == "CA" and bool(bill_number) and bool(_CA_SB54_RE.search(bill_number))
    fee = _ca_fee_range(apportioned) if is_ca_sb54 else None
    if fee is None:
        fee = _generic_fee_range(cd, apportioned)
    if fee is not None:
        # Make the apportionment explicit so the range never reads as exact.
        fee["fee_basis"] = (
            f"{fee['fee_basis']} · volume apportioned to {bill_state} "
            f"(~{round(share * 100)}% of US, population-weighted)"
        )

    pro_membership = fees.get("registration_fee_usd")
    pro_membership = float(pro_membership) if pro_membership else None

    return {
        "penalty": penalty,
        "fee": fee,
        "pro_membership_usd": pro_membership,
        "has_any": bool(penalty or fee or pro_membership),
    }
