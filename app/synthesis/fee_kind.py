"""Derive a `fee_kind` from a raw `fee_amounts.rates[]` entry — a deterministic, pure classifier.

The `fee_amounts` envelope (app/classification/sonnet_extractor.py) captures every monetary amount a
measure states, and the `rates[]` array deliberately mixes KINDS: a genuine per-tonne producer fee sits
next to a registration cap, a consumer deposit/incentive, a de-minimis threshold, an administrative-cost
floor, and outright fines. `basis` alone can't separate them (a "flat" amount is a registration fee, a
fine, or a funding floor depending on the clause). This maps each entry to one label so the API's
`?fee_kind` filter can narrow to what a caller actually means.

Rules are ordered — first match wins — and keyword-driven off the free-text `material` descriptor, with
`basis` as the fallback signal. Tuned against the prod corpus (see docs/FEE_DATA_API_SPEC.md §4).
Precision over recall: an ambiguous entry lands in `unspecified` rather than being force-fit.
"""
from __future__ import annotations

import re

FEE_KINDS = (
    "producer_fee",   # a fee a covered producer pays to comply (per-ton, per-unit, %-revenue, eco-modulated)
    "registration",   # a flat fee to register / renew / join a scheme
    "incentive",      # money flowing TO a consumer/technician/collector — deposit, refund, bounty, rebate
    "penalty",        # a fine / surcharge for non-compliance or a violation
    "threshold",      # a de-minimis floor (below which a producer is exempt / no fee is due)
    "admin_cost",     # aggregate program / agency / oversight cost recovery — not a per-producer fee
    "unspecified",    # none of the above with confidence
)

# Ordered, most-specific first. Each pattern is matched (case-insensitive) against the `material` text.
_PENALTY = re.compile(
    r"\b(fine|penalt\w*|forfeit\w*|violation|non-?compli\w*|infringement|sanction)\b", re.I
)
_THRESHOLD = re.compile(
    r"(de-?minimis|minimum threshold|threshold below which|below which no|"
    r"floor below which|exempt(?:ion)? threshold|small quantit|turnover (?:floor|below))",
    re.I,
)
_INCENTIVE = re.compile(
    r"\b(incentive|bounty|refund|rebate|deposit|reward|social impact payment|"
    r"paid to (?:the )?(?:consumer|customer|technician|collector|retailer)|"
    r"returned to (?:the )?(?:consumer|customer))\b",
    re.I,
)
_REGISTRATION = re.compile(
    r"\b(registration|renewal|membership|enrol(?:l|lment)?|joining fee|sign-?up fee|"
    r"per producer per year|annual (?:producer )?fee)\b",
    re.I,
)
_ADMIN = re.compile(
    r"\b(oversight|administrative cost|admin(?:istration)? cost|program(?:me)? cost|"
    r"cost recovery|operating cost|agency cost|regulatory cost)\b",
    re.I,
)

# `basis` values that, absent a more specific descriptor signal, mean a producer-borne compliance fee.
_PRODUCER_BASES = frozenset({"per_ton", "per_unit", "percent_revenue", "eco_modulated"})


def classify_fee_kind(basis: str | None, material: str | None) -> str:
    """Classify one rate entry. Pure; safe on None inputs.

    Order matters: penalty > threshold > incentive > registration > admin_cost > producer_fee(by basis)
    > unspecified. The descriptor carries the intent; `basis` only decides the residual producer-fee case.
    """
    text = material or ""
    if _PENALTY.search(text):
        return "penalty"
    if _THRESHOLD.search(text):
        return "threshold"
    if _INCENTIVE.search(text):
        return "incentive"
    if _REGISTRATION.search(text):
        return "registration"
    if _ADMIN.search(text):
        return "admin_cost"
    if (basis or "").strip().lower() in _PRODUCER_BASES:
        return "producer_fee"
    return "unspecified"
