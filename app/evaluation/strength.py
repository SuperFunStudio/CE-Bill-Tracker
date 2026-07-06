"""Bill-strength evaluation — score a draft measure by whether it carries the mechanisms its target
material's economics actually require, not by a flat count of dimensions.

The load-bearing idea (see the product-design conversation): strength is *conditional on the material*.
A lead-acid battery bill can be lean and still strong — high core value plus an established reverse
channel mean legislation only has to internalize the externality so the durable product isn't undercut
by the disposable one. The SAME lean structure applied to textiles is WEAK: low value + high dispersion
+ no channel mean the collection unit-economics never cross the valley without deliberately engineered
critical mass — mandated collection + PRO-pooled financing of the "decomposer" layer + design
intervention, all at once.

So we (1) POSITION the target material into a regime, then (2) SCORE the extracted eight-dimension
envelopes against the baseline that regime demands. Positioning and scoring are deterministic, explainable
rules here (reproducible, no hidden model judgment); the only LLM step is the shared SonnetExtractor that
produced the envelopes in the first place. The result is a *fit* score, not an absolute one: a lean
battery bill and a heavy textiles bill can both score high because each matches its own regime's playbook.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.classification.sonnet_extractor import SonnetResult
from app.evaluation.baselines import baseline_for
from app.schemas import (
    BillRegime,
    EvaluateResponse,
    RegimeAxes,
    RequirementResult,
    StrengthScore,
)

# --- Regimes -----------------------------------------------------------------------------------------
INCREMENTAL = "incremental_viable"
CRITICAL = "critical_mass"

_REGIME_LABEL = {
    INCREMENTAL: "Incremental-viable",
    CRITICAL: "Critical-mass-required",
}
_REGIME_RATIONALE = {
    INCREMENTAL: (
        "High material value plus an established reverse channel mean the unit economics already work. "
        "Legislation's only job is to stop penalizing the first mover — internalize the disposal "
        "externality so the durable product isn't undercut by the disposable one. A lean bill can be "
        "strong here; heavy collection machinery isn't required."
    ),
    CRITICAL: (
        "Low material value, high dispersion, and no established channel mean the collection "
        "unit-economics never work below near-total coverage — there is no rational first mover. The "
        "bill has to engineer critical mass deliberately: mandated collection, PRO-pooled financing of "
        "the decomposer layer, and design intervention, all at once. A lean bill here predicts an "
        "implementation and operational gap."
    ),
}

# --- Material positioning ----------------------------------------------------------------------------
# Ordered specific -> general; first keyword hit on (covered_products + title) wins.
#
# value_usd_per_tonne is the RECOVERABLE secondary-material value of the stream — order-of-magnitude
# anchors from US mid-2026 scrap/commodity reporting (the model only needs the right decade, not spot
# precision). It is normalized to the 0..1 value_density axis on a LOG scale, because these streams span
# ~2.5 decades — a PCB stream (~$12k/t) to mixed textiles/plastics (~$40/t) — so a linear 0..1 would
# crush everything below aluminium into the floor. Sources (2026 unless noted):
#   precious-metal / PCB e-scrap ~$10-15k/t recoverable (recyclingtoday, ledoux) → anchor 12000
#   Li-ion black mass NCM ~$6.4k/t (mysteel/Fastmarkets)                          → 4000 (LFP much less)
#   mixed electronics / WEEE, blended device scrap                               → 2500
#   aluminium scrap ~$1.5-2.5k/t (iScrap, S&P)                                    → 1800
#   lead-acid whole-battery scrap ~$400-500/t (£300-600, iScrap $0.20/lb)         → 450
#   crumb rubber / scrap tire ~$200-300/t (recyclingtoday)                        → 250
#   recovered paper / OCC ~$85/t domestic (Davis Index / Fastmarkets)             → 85
#   mattress / carpet / packaging blended, mostly low or negative after sort      → 60
#   mixed recycling-grade textiles (post-consumer, non-rewearable)                → 50 (reuse-grade higher)
#   glass cullet ~$0-100/t, often near zero (scrapmonster/EPA)                    → 50
#   flexible film / single-use, post-consumer mixed near zero                     → 30
#   paint / pharma — hazardous, negative material value, floored                  → 20
# dispersion (high = spread thin across many holders at end of life) is a Sonnet estimate calibrated
# across the whole set in one pass — see scripts/estimate_dispersion.py (re-run to refresh). channel_maturity
# is a seed prior blended at request time with corpus-derived enacted-law breadth (see channel.py). regime
# is assigned explicitly (a 3-factor judgment: value AND dispersion AND channel), NOT derived from value
# alone — which is why paper and lead-acid are incremental despite modest material value: an established,
# ubiquitous channel substitutes for unit value.
_VALUE_FLOOR, _VALUE_CEIL = 20.0, 12000.0  # $/tonne clamp for the log normalization


def _value_density(usd_per_tonne: float) -> float:
    """Log-normalize a $/tonne recoverable value onto the 0..1 value_density axis."""
    v = min(max(usd_per_tonne, _VALUE_FLOOR), _VALUE_CEIL)
    lo, hi = math.log10(_VALUE_FLOOR), math.log10(_VALUE_CEIL)
    return round((math.log10(v) - lo) / (hi - lo), 2)


@dataclass(frozen=True)
class MaterialProfile:
    keywords: tuple[str, ...]
    label: str
    value_usd_per_tonne: float
    dispersion: float
    channel_maturity: float
    regime: str

    def axes(self) -> RegimeAxes:
        return RegimeAxes(
            value_density=_value_density(self.value_usd_per_tonne),
            dispersion=self.dispersion, channel_maturity=self.channel_maturity,
        )


# Columns: value_usd_per_tonne (grounded), dispersion (Sonnet, scripts/estimate_dispersion.py), channel
# seed prior (blended with corpus at request time), regime.
MATERIAL_PROFILES: list[MaterialProfile] = [
    MaterialProfile(("lead-acid", "lead acid", "car batter", "automotive batter", "sla battery"),
                    "Lead-acid batteries", 450, 0.10, 0.90, INCREMENTAL),
    MaterialProfile(("aluminum can", "aluminium can", "beverage can", "aluminum", "aluminium"),
                    "Aluminum", 1800, 0.35, 0.85, INCREMENTAL),
    MaterialProfile(("precious metal", "catalytic convert", "platinum", "palladium", "gold recovery"),
                    "Precious metals", 12000, 0.55, 0.80, INCREMENTAL),
    MaterialProfile(("tire", "tyre"), "Tires", 250, 0.15, 0.70, INCREMENTAL),
    MaterialProfile(("paper", "cardboard", "fiber", "fibre", "corrugated"),
                    "Paper & fiber", 85, 0.60, 0.70, INCREMENTAL),
    MaterialProfile(("lithium", "li-ion", "lithium-ion", "rechargeable batter", "battery", "batteries", "cell"),
                    "Batteries (Li-ion / other)", 4000, 0.65, 0.50, CRITICAL),
    MaterialProfile(("electronic", "e-waste", "ewaste", "weee", "appliance", "device", "covered device"),
                    "Electronics / WEEE", 2500, 0.60, 0.55, CRITICAL),
    MaterialProfile(("textile", "apparel", "clothing", "garment", "fabric"),
                    "Textiles & apparel", 50, 0.85, 0.10, CRITICAL),
    MaterialProfile(("footwear", "shoe", "sneaker", "boot"), "Footwear", 40, 0.82, 0.05, CRITICAL),
    MaterialProfile(("mattress",), "Mattresses", 60, 0.50, 0.30, CRITICAL),
    MaterialProfile(("carpet", "flooring", "carpet tile"), "Carpet & flooring", 60, 0.45, 0.40, CRITICAL),
    MaterialProfile(("paint", "coating", "architectural paint"), "Paint", 20, 0.60, 0.50, CRITICAL),
    MaterialProfile(("pharmaceutical", "drug take", "medicine", "sharps", "medication"),
                    "Pharmaceuticals & sharps", 20, 0.65, 0.30, CRITICAL),
    MaterialProfile(("flexible film", "plastic film", "flexible plastic", "single-use plastic", "single use plastic"),
                    "Flexible plastics / single-use", 30, 0.90, 0.20, CRITICAL),
    MaterialProfile(("glass",), "Glass", 50, 0.50, 0.65, CRITICAL),
    MaterialProfile(("packaging", "container", "bottle", "carton", "wrapper"),
                    "Packaging (mixed)", 60, 0.75, 0.50, CRITICAL),
]
# Conservative fallback: assume the harder regime so an unknown material can't earn a high score on a
# lean bill it hasn't been shown to deserve. Flagged low-confidence so the UI can say "positioning uncertain".
_FALLBACK = MaterialProfile((), "the measure's covered products", 300, 0.60, 0.45, CRITICAL)


@dataclass
class Positioning:
    """A material's placement on the map + its regime. Produced deterministically by _position for known
    materials, or by the LLM axis-estimator (app/evaluation/axis_estimator.py) for novel ones."""
    regime: str
    material: str
    confidence: str  # high (seed table) | low (fixed fallback) | estimated (LLM)
    axes: RegimeAxes
    rationale: str


def value_density_from_usd(usd_per_tonne: float) -> float:
    """Public alias for the $/tonne → 0..1 log normalization (used by the LLM axis-estimator)."""
    return _value_density(usd_per_tonne)


def regime_for_axes(value_density: float, dispersion: float, channel_maturity: float) -> str:
    """The regime an estimated material falls into: incremental-viable only when material value AND an
    established channel are both reasonably high (either one alone — like paper's channel or Li-ion's
    value — isn't enough); otherwise critical-mass. Mirrors the seed table's editorial calls."""
    return INCREMENTAL if (value_density >= 0.45 and channel_maturity >= 0.5 and dispersion <= 0.6) else CRITICAL


def match_material_label(text: str | None) -> str | None:
    """The material label whose keywords first hit in `text`, or None — used to bucket corpus bills by
    material (see app/evaluation/channel.py) with the same table that positions a draft."""
    t = (text or "").lower()
    for p in MATERIAL_PROFILES:
        if any(k in t for k in p.keywords):
            return p.label
    return None


def _position(result: SonnetResult, title: str | None) -> tuple[str, str, str, RegimeAxes, str]:
    """Return (regime_key, material_label, confidence, axes, rationale) for the extracted measure.
    Positions on the extracted covered products plus the measure's title (both name the material)."""
    haystack = " ".join([*(result.covered_products or []), title or ""]).lower()
    for p in MATERIAL_PROFILES:
        if any(k in haystack for k in p.keywords):
            return p.regime, p.label, "high", p.axes(), _REGIME_RATIONALE[p.regime]
    return _FALLBACK.regime, _FALLBACK.label, "low", _FALLBACK.axes(), _REGIME_RATIONALE[_FALLBACK.regime]


# --- Envelope helpers --------------------------------------------------------------------------------
def _env(result: SonnetResult, key: str) -> dict:
    val = getattr(result, key, None)
    return val if isinstance(val, dict) else {}


def _present(e: dict) -> bool:
    return e.get("status") == "present"


def _targets(result: SonnetResult) -> list[dict]:
    t = _env(result, "collection_targets").get("targets")
    return [x for x in t if isinstance(x, dict)] if isinstance(t, list) else []


def _has_numeric_target(result: SonnetResult) -> bool:
    return any(isinstance(t.get("percent"), (int, float)) and t.get("percent") for t in _targets(result))


def _bases(result: SonnetResult) -> set[str]:
    return {str(t.get("basis") or "").lower() for t in _targets(result)}


# A status is a fraction: met=1.0, partial=0.5, missing=0.0.
_STATUS_SCORE = {"met": 1.0, "partial": 0.5, "missing": 0.0}


def _req(key, label, importance, weight, status, your_value, baseline, note=None) -> RequirementResult:
    return RequirementResult(
        key=key, label=label, importance=importance, weight=weight, status=status,
        your_value=your_value, baseline=baseline, note=note,
    )


# --- Regime rubrics ----------------------------------------------------------------------------------
def _critical_requirements(result: SonnetResult) -> tuple[list[RequirementResult], list[str]]:
    reqs: list[RequirementResult] = []
    flags: list[str] = []

    # 1. Mandated collection targets — the hard "minimum viable circulation" threshold.
    ct = _env(result, "collection_targets")
    if _present(ct) and _has_numeric_target(result):
        status, your = "met", "Numeric collection target(s) set"
    elif _present(ct):
        status, your = "partial", "Collection referenced but no numeric/ramped target"
    else:
        status, your = "missing", "No collection targets"
    reqs.append(_req(
        "collection", "Mandated collection targets", "load_bearing", 3, status, your,
        "Mandated collection ramped toward near-total coverage — the minimum-viable-circulation threshold, "
        "not a voluntary gradient.",
    ))

    # 2. PRO with pooled financing — funds the decomposer layer no single firm will build.
    pro = _env(result, "pro_structure")
    model = pro.get("model")
    if _present(pro) and model in ("single_pro", "competitive_pros"):
        status, your = "met", f"PRO structure: {model.replace('_', ' ')}"
    elif _present(pro):
        status, your = "partial", f"PRO present ({model or 'unspecified'}) — no pooled financing"
    else:
        status, your = "missing", "No PRO / stewardship organization"
    reqs.append(_req(
        "pro_financing", "PRO-pooled financing", "load_bearing", 3, status, your,
        "A PRO with pooled producer financing to stand up the reverse-logistics / sortation layer that no "
        "single firm will fund alone.",
    ))

    # 3. Design intervention / sortation taxonomy — makes the dispersed stream sortable.
    bans = _env(result, "bans_restrictions")
    has_design_ban = _present(bans) and any(
        isinstance(i, dict) and i.get("type") in ("design_ban", "material_restriction")
        for i in (bans.get("items") or [])
    )
    has_label_id = _present(_env(result, "labeling")) and any(
        isinstance(r, dict) and r.get("type") in ("material_id", "recyclability", "disposal_instructions")
        for r in (_env(result, "labeling").get("requirements") or [])
    )
    levers = sum([_present(_env(result, "eco_modulation")), has_design_ban, has_label_id])
    status = "met" if levers >= 2 else "partial" if levers == 1 else "missing"
    reqs.append(_req(
        "design", "Design intervention (sortability)", "load_bearing", 2, status,
        f"{levers} of 3 design levers present (eco-modulation, design ban, material-ID labeling)",
        "Design levers — eco-modulation, design bans, material-ID labeling — that engineer a sortable, "
        "recoverable stream instead of leaving it mixed.",
    ))

    # 4. Reverse-logistics funding via producer fees.
    fa = _env(result, "fee_amounts")
    has_rate = _present(fa) and any(isinstance(r, dict) and r.get("amount") for r in (fa.get("rates") or []))
    if has_rate:
        status, your = "met", "Producer fee rate(s) specified"
    elif _present(fa):
        status, your = "partial", "Fees referenced but no rate"
    else:
        status, your = "missing", "No producer fees"
    reqs.append(_req(
        "fees", "Reverse-logistics funding", "supporting", 2, status, your,
        "Producer fees scaled to actually pay for collection and reverse logistics below break-even route "
        "density.",
    ))

    # Predicted implementation gap — the exact failure mode the framework warns about.
    load_bearing = {r.key: r.status for r in reqs if r.importance == "load_bearing"}
    if load_bearing.get("collection") != "met" and load_bearing.get("pro_financing") != "met":
        flags.append(
            "Implementation-gap risk: this is a network-gated material, but the bill relies on incrementalism "
            "(no mandated collection + pooled-financed PRO). Below break-even collection density there is no "
            "rational first mover — expect an implementation and operational gap unless critical mass is "
            "engineered deliberately."
        )
    return reqs, flags


def _incremental_requirements(result: SonnetResult) -> tuple[list[RequirementResult], list[str]]:
    reqs: list[RequirementResult] = []

    # 1. Internalize the externality — the whole job of legislation in this regime.
    fa, eco = _env(result, "fee_amounts"), _env(result, "eco_modulation")
    fees_struct = (result.fees or {}).get("structure")
    if _present(fa) or _present(eco) or fees_struct in ("per_unit", "per_ton", "eco_modulated"):
        status, your = "met", "Fee / EPR obligation internalizes disposal cost"
    else:
        status, your = "missing", "No fee obligation — first mover stays undercut"
    reqs.append(_req(
        "internalize", "Externality internalized", "load_bearing", 3, status, your,
        "A fee or EPR obligation that internalizes the disposal externality so the durable, repairable "
        "product isn't undercut by the disposable one. This is the whole job here.",
    ))

    # 2. A recovery floor — light, because the channel and economics already exist.
    ct, rc = _env(result, "collection_targets"), _env(result, "recycled_content")
    if _present(ct) or _present(rc):
        status, your = "met", "Collection target or recycled-content floor set"
    else:
        status, your = "partial", "No explicit recovery floor (often fine in this regime)"
    reqs.append(_req(
        "floor", "Recovery floor", "supporting", 2, status, your,
        "A collection target or recycled-content minimum as a floor — light-touch, since the reverse "
        "channel and unit economics already carry the volume.",
    ))

    # 3. Design signal — a bonus that pushes durability/repairability upstream.
    eco_present = _present(eco)
    reqs.append(_req(
        "design_signal", "Design signal", "bonus", 1, "met" if eco_present else "missing",
        "Eco-modulation present" if eco_present else "No eco-modulation",
        "Eco-modulated fees that reward durability, repairability, and recycled content — captured "
        "unilaterally by the first mover.",
    ))
    return reqs, []


def _value_basis_flag(result: SonnetResult) -> list[str]:
    """Value-vs-weight is the 'how it's modeled' axis: weight-based targets are gameable (reward tonnage
    and downcycling); value_recovered / material_specific reward actual value retention."""
    bases = _bases(result)
    if not bases or bases == {""}:
        return []
    if bases & {"value_recovered", "material_specific"}:
        return ["Targets are value-aligned (measured on value recovered / material-specific), not just "
                "weight — this rewards actual value retention over tonnage."]
    if "weight" in bases:
        return ["Weight-based targets: measuring recovery by tonnage is gameable — it rewards heavy, "
                "low-value material and downcycling. Consider value-recovered or material-specific targets."]
    return []


def requirements_for(result: SonnetResult, regime_key: str) -> tuple[list[RequirementResult], list[str]]:
    """Score a measure's mechanisms against the given regime's rubric. Exposed so the corpus
    cross-check (app/evaluation/corpus.py) can score enacted analogs on the SAME axes as the draft."""
    return _critical_requirements(result) if regime_key == CRITICAL else _incremental_requirements(result)


# The eight envelope keys mirrored between a SonnetResult and a stored compliance_details dict.
_ENVELOPE_KEYS = (
    "eco_modulation", "recycled_content", "penalties", "collection_targets",
    "pro_structure", "bans_restrictions", "fee_amounts", "labeling",
)


def result_from_compliance_details(cd: dict | None) -> SonnetResult:
    """Adapt a stored compliance_details JSONB back into a SonnetResult so corpus analogs run through
    the exact same positioning/scoring code as a freshly-extracted draft (only the fields the rubric
    reads are populated; the rest default)."""
    cd = cd or {}
    envelopes = {k: (cd.get(k) if isinstance(cd.get(k), dict) else {}) for k in _ENVELOPE_KEYS}
    return SonnetResult(
        covered_products=cd.get("covered_products") or [], producer_definition="", producer_obligations=[],
        deadlines=[], fees=cd.get("fees") or {}, exemptions=[], pro_requirements="", enforcement={},
        effective_date=None, reporting_requirements="", preemption_risk="Low", preemption_notes="",
        related_bills=[], implementation_phases=[], extraction_version=0, raw_json=cd, **envelopes,
    )


def position(result: SonnetResult, title: str | None) -> tuple[str, str, str, RegimeAxes, str]:
    """Public wrapper over the material positioner — reused by the corpus cross-check to bucket analogs."""
    return _position(result, title)


def evaluate_strength(
    result: SonnetResult, title: str | None, jurisdiction: str | None,
    positioning: Positioning | None = None,
) -> EvaluateResponse:
    if positioning is not None:
        regime_key, material, confidence, axes, rationale = (
            positioning.regime, positioning.material, positioning.confidence,
            positioning.axes, positioning.rationale,
        )
    else:
        regime_key, material, confidence, axes, rationale = _position(result, title)
    reqs, flags = requirements_for(result, regime_key)
    flags = _value_basis_flag(result) + flags

    # Fit score: weighted fraction of the non-bonus requirements met (met=1, partial=0.5, missing=0).
    scored = [r for r in reqs if r.importance != "bonus"]
    denom = sum(r.weight for r in scored) or 1
    value = round(100 * sum(_STATUS_SCORE[r.status] * r.weight for r in scored) / denom)
    band = "strong" if value >= 70 else "moderate" if value >= 40 else "weak"
    met = sum(1 for r in scored if r.status == "met")
    summary = (
        f"Scored against the {_REGIME_LABEL[regime_key].lower()} playbook this material demands: "
        f"{met}/{len(scored)} core mechanisms fully in place."
    )

    # Extracted envelopes, shaped like compliance_details so the frontend renders them with dimensions.ts.
    compliance_details = {
        "covered_products": result.covered_products,
        "eco_modulation": result.eco_modulation, "recycled_content": result.recycled_content,
        "fee_amounts": result.fee_amounts, "penalties": result.penalties,
        "collection_targets": result.collection_targets, "pro_structure": result.pro_structure,
        "bans_restrictions": result.bans_restrictions, "labeling": result.labeling,
    }
    return EvaluateResponse(
        regime=BillRegime(
            key=regime_key, label=_REGIME_LABEL[regime_key], material=material,
            confidence=confidence, rationale=rationale, axes=axes,
        ),
        score=StrengthScore(value=value, band=band, summary=summary),
        requirements=reqs,
        flags=flags,
        compliance_details=compliance_details,
        # The strong model bill for this regime — an envelope-to-envelope diff target (see baselines.py).
        baseline_details=baseline_for(regime_key, material),
        title=title,
        jurisdiction=jurisdiction,
    )


def material_map() -> list[dict]:
    """Every known material as a point on the value×dispersion×channel map, with its regime — the
    reference data behind the material-position viz (GET /evaluate/material-map). value_density is the
    log-normalized recoverable $/tonne (see MaterialProfile); the raw $/tonne rides along for tooltips."""
    out = []
    for p in MATERIAL_PROFILES:
        ax = p.axes()
        out.append({
            "material": p.label, "value_density": ax.value_density, "dispersion": ax.dispersion,
            "channel_maturity": ax.channel_maturity, "regime": p.regime,
            "value_usd_per_tonne": p.value_usd_per_tonne,
        })
    return out
