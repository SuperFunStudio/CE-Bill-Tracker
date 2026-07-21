"""Pure-function guards for the RULE 1 -> RULE 2 (dimension) escalation decision.

Regression coverage for the remanufacturing divergence follow-up: a thin full-text match is escalated
to a compliance dimension's curated set ONLY for a bare "what does the corpus have on <topic>" ask —
never for a specific query that merely contains a dimension keyword (which would otherwise get swallowed
into the whole dimension, e.g. "civil penalty of $10,000 per day" -> all 639 penalty bills). The DB-bound
escalation lives in _relevant_bills; this covers the deterministic gate that governs it.
"""
from app.api.research import _dim_is_dominant


def test_bare_topic_is_dominant():
    # Only the dimension topic survives → escalation is the right, phrasing-independent answer.
    assert _dim_is_dominant(["remanufacturing"], "remanufactur") is True
    # A synonym trigger phrase whose tokens are the only terms is still bare.
    assert _dim_is_dominant(["industrial", "symbiosis"], "industrial symbiosis") is True


def test_specific_query_is_not_dominant():
    # Extra narrowing terms present → keep the precise text match; do NOT swallow into the dimension.
    assert _dim_is_dominant(["mention", "civil", "penalty", "000", "per", "day"], "penalt") is False
    assert _dim_is_dominant(["recycled", "content", "minimum", "percent"], "recycled content") is False


def test_no_trigger_is_not_dominant():
    assert _dim_is_dominant(["remanufacturing"], None) is False
    assert _dim_is_dominant([], "penalt") is True  # nothing left is trivially bare (n==0 guard fires upstream)
