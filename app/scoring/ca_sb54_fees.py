"""California SB 54 (2027) published producer fee schedule — grounded anchor data.

Source: Circular Action Alliance (CAA) California EPR Program Plan, Chapter 9
"Fee-Setting", Table 5 "2027 EPR Base Fee Schedule: Ranges from Low to High"
(submitted to CalRecycle June 2026; final rates to be published October 2026).
https://circularactionalliance.org/

This is the most economically significant EPR fee schedule in the US — California is
the largest market and the only program with per-material-category rates published in
enough detail to ground a real producer cost. Every other US packaging program either
defers fees to post-enactment rulemaking or publishes only an aggregate target, so we
treat CA SB 54 as the flagship anchor and express other states relative to it.

WHAT WE ENCODE
--------------
The published table is per Covered Material Category (CMC) in ¢/lb, with a Low and High
scenario, plus separate Reuse Investment and Plastic Pollution Mitigation Fund (PPMF)
adders that apply ONLY to plastic CMCs. We collapse the ~60 CMCs into the five coarse
material categories the company model uses, and convert ¢/lb → $/tonne:

    $/tonne = (¢/lb) / 100 * 2204.62        # 1 tonne = 2204.62 lb

For plastics the rate INCLUDES the published Reuse (4¢/lb low) and PPMF weight
(17¢/lb low) adders, because a producer pays the total — that is the honest "what's at
stake" number. We keep a `base_only` figure too, for transparency.

ECO-MODULATION (the design lever)
---------------------------------
Within each category the published rates span an enormous range driven by recyclability
— e.g. glass bottles at 1¢/lb ($22/t) vs. pigmented PET at 69¢/lb, PP bottles at 98¢/lb.
SB 54 Ch.10 adds active maluses up to +100% (doubling the base fee) for non-recyclable
formats / carbon-black / problematic features, and PCR + source-reduction bonuses that
cut fees. So `best_format` / `worst_format` below are the real published low/high formats
in each category — the spread IS the redesign opportunity, quantified.

All values are $/tonne, rounded. These are draft published ranges; the final 2027
schedule lands October 2026. Confidence is capped accordingly in the estimator.
"""
from __future__ import annotations

from app.scoring.materials import canonical_material_category

LB_PER_TONNE = 2204.62


def _cents_lb_to_per_tonne(cents_per_lb: float) -> float:
    """Convert a published ¢/lb rate to $/tonne."""
    return round(cents_per_lb / 100.0 * LB_PER_TONNE)


# Plastic adders that apply to every plastic CMC (low scenario), ¢/lb.
_PLASTIC_REUSE_ADDER = 4.0
_PLASTIC_PPMF_ADDER = 17.0
_PLASTIC_ADDER_CENTS = _PLASTIC_REUSE_ADDER + _PLASTIC_PPMF_ADDER  # 21¢/lb


# Per coarse category: representative base ¢/lb (low scenario) + the cheapest
# ("best") and most-expensive ("worst") published format in that category, used to
# show the eco-modulation design lever. Plastic categories carry the PPMF + reuse adder.
# Format example rates are base ¢/lb from Table 5 (low scenario).
CA_SB54_2027_SCHEDULE: dict[str, dict] = {
    "plastic_packaging": {
        "representative_base_cents_lb": 33.0,   # blended rigid (PET/HDPE/PP/PS/PVC)
        "plastic_adder_cents_lb": _PLASTIC_ADDER_CENTS,
        "best_format": {"name": "Recyclable PET/HDPE bottle (clear/natural)", "base_cents_lb": 29.0},
        "worst_format": {"name": "PP bottle / PS foam (low-value, hard to recycle)", "base_cents_lb": 98.0},
        "note": "Plastics also pay the PPMF ($500M/yr, allocated by plastic-weight share) and Reuse Investment fees; PCR content and source reduction earn bonuses that lower the rate.",
    },
    "plastic_film": {
        "representative_base_cents_lb": 30.0,   # blended film/flexible
        "plastic_adder_cents_lb": _PLASTIC_ADDER_CENTS,
        "best_format": {"name": "Mono-material pouch / recyclable PE film", "base_cents_lb": 13.0},
        "worst_format": {"name": "PET film / multi-material laminate", "base_cents_lb": 49.0},
        "note": "Flexible film and multi-material laminates are among the hardest to recycle; mono-material redesign moves toward the low end.",
    },
    "paper_packaging": {
        "representative_base_cents_lb": 5.0,    # paperboard
        "plastic_adder_cents_lb": 0.0,
        "best_format": {"name": "Corrugated cardboard (uncoated)", "base_cents_lb": 2.0},
        "worst_format": {"name": "Plastic-coated / multi-material laminate carton", "base_cents_lb": 27.0},
        "note": "Clean fiber is among the cheapest materials; plastic coatings and laminates push fiber up ~13x.",
    },
    "glass_packaging": {
        "representative_base_cents_lb": 1.0,    # bottles & jars
        "plastic_adder_cents_lb": 0.0,
        "best_format": {"name": "Glass bottles & jars", "base_cents_lb": 1.0},
        "worst_format": {"name": "Glass — other / small (<2in) forms", "base_cents_lb": 23.0},
        "note": "Glass bottles & jars are the lowest-fee covered material in the schedule — the design anchor to move toward.",
    },
    "aluminum_packaging": {
        "representative_base_cents_lb": 11.0,   # aluminum non-aerosol container
        "plastic_adder_cents_lb": 0.0,
        "best_format": {"name": "Steel/tin or other-ferrous container", "base_cents_lb": 5.0},
        "worst_format": {"name": "Aluminum foil / aerosol can", "base_cents_lb": 14.0},
        "note": "Metals carry mid-range fees; high recycling rates earn passive bonuses.",
    },
}

# High-scenario multiplier observed across Table 5 (published high ≈ 2.5x low for plastics).
# Used to express the upper bound of the program's own published range.
HIGH_SCENARIO_MULTIPLIER = 2.5

SCHEDULE_CITATION = (
    "Circular Action Alliance — California SB 54 EPR Program Plan, Ch. 9 Table 5, "
    "2027 EPR Base Fee Schedule (draft; final October 2026)."
)
SCHEDULE_SOURCE_URL = "https://circularactionalliance.org/"


def category_rate_per_tonne(category: str) -> dict | None:
    """Grounded CA SB 54 $/tonne figures for one coarse material category.

    Returns a dict with representative / best / worst $/tonne (total fee incl. plastic
    adders) and the high-scenario upper bound, or None if the category is not covered.
    The category is normalized via the shared canonical vocabulary first, so both bill
    ("glass") and company ("glass_packaging") tokens resolve.
    """
    category = canonical_material_category(category)
    spec = CA_SB54_2027_SCHEDULE.get(category)
    if spec is None:
        return None

    adder = spec["plastic_adder_cents_lb"]
    rep = _cents_lb_to_per_tonne(spec["representative_base_cents_lb"] + adder)
    best = _cents_lb_to_per_tonne(spec["best_format"]["base_cents_lb"] + adder)
    worst = _cents_lb_to_per_tonne(spec["worst_format"]["base_cents_lb"] + adder)
    return {
        "category": category,
        "representative_per_tonne": rep,
        "representative_high_per_tonne": round(rep * HIGH_SCENARIO_MULTIPLIER),
        "best_per_tonne": best,
        "best_format": spec["best_format"]["name"],
        "worst_per_tonne": worst,
        "worst_format": spec["worst_format"]["name"],
        "includes_plastic_adders": adder > 0,
        "note": spec["note"],
        "citation": SCHEDULE_CITATION,
        "source_url": SCHEDULE_SOURCE_URL,
    }
