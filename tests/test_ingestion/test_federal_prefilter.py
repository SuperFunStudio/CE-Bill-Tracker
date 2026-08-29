"""The US Congress master-list prefilter.

Congress reaches the pipeline as ~18,500 bills per session, one getBill call each, against a
5,000-call budget. FEDERAL_PREFILTER is what makes that affordable: it gates on the master-list
summary (title + description) before a call is spent.

Its job is RECALL, not precision — HaikuClassifier judges everything that passes, so a false
positive costs one classification while a false negative costs a bill the corpus never learns
about. The tests are therefore asymmetric: the in-scope cases are the load-bearing ones.
"""
import pytest

from app.ingestion.coordinator import _passes_federal_prefilter


def _summary(title: str, description: str = "") -> dict:
    return {"title": title, "description": description}


@pytest.mark.parametrize("title", [
    # The bill that exposed the federal coverage gap.
    "BRACE Act Battery Recycling for America's Competitive Economy Act",
    # Real 119th Congress titles that the state-tuned KeywordFilter scores at 0.00, because its
    # vocabulary is all multi-word phrases and a federal summary is one line long.
    "Recycling Infrastructure and Accessibility Act of 2025",
    "COMPOST Act Cultivating Organic Matter through the Promotion of Sustainable Techniques",
    "CIRCLE Act Cultivating Investment in Recycling and Circular Economy",
    "Recycling and Composting Accountability Act",
    "Setting Consumer Standards for Lithium-Ion Batteries Act",
    "USA Batteries Act",
    "Secure E-Waste Export and Recycling Act",
    # Right-to-repair arrives titled as an ACT, not as the phrase the state vocabulary expects.
    "Fair Repair Act",
    "REPAIR Act Right to Equitable and Professional Auto Industry Repair Act",
    "Farm Freedom to Repair Act",
])
def test_in_scope_federal_bills_pass(title):
    assert _passes_federal_prefilter(_summary(title)) is True


@pytest.mark.parametrize("title", [
    # The word-boundary regression. Unanchored, "tire" matched reTIREd/reTIREes and these four
    # were ingested for real before the \b was added — 244 such false positives in one session.
    "Retired Pay Restoration Act",
    "Equal COLA Act",
    "Protecting American Savers and Retirees Act",
    "Disabled Veterans Tax Termination Act",
    "Retirement Fairness for Charities and Educational Institutions Act",
    # Ordinary federal business with no circular-economy signal at all.
    "National Defense Authorization Act",
    "To designate a post office in Springfield",
])
def test_out_of_scope_federal_bills_are_filtered(title):
    assert _passes_federal_prefilter(_summary(title)) is False


def test_description_is_searched_not_only_title():
    """The master-list summary carries a one-line description; an opaque acronym title only
    clears the gate because of it."""
    assert _passes_federal_prefilter(
        _summary("BRACE Act", "To support the recycling and recovery of lithium-ion batteries.")
    ) is True


def test_terms_match_as_prefixes():
    """"recycl" must catch recycling/recyclable/recycled — the net is prefix-based by design."""
    for t in ("A bill on recycling", "A bill on recyclable goods", "A bill on recycled content"):
        assert _passes_federal_prefilter(_summary(t)) is True


def test_missing_and_empty_fields_are_safe():
    assert _passes_federal_prefilter({}) is False
    assert _passes_federal_prefilter({"title": None, "description": None}) is False
