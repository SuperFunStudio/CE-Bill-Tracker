"""Tests for producer attribution — app/scoring/producer_attribution.py + its endpoint.

Pure in-code reference data, no DB, so the router is mounted on a minimal FastAPI app.

These tests are deliberately weighted toward the DIRECTION of the answer rather than its
prose, because the direction is what a wrong model gets wrong: Oregon must not attribute
food serviceware to the brand owner, the franchisor states must not attribute it to the
individual outlet, and an unknown jurisdiction must not come back looking like an exemption.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.compliance import router
from app.scoring.producer_attribution import (
    ATTRIBUTION,
    coverage,
    jurisdictions_for_regime,
    resolve_attribution,
)

app = FastAPI()
app.include_router(router)
client = TestClient(app)


# --- The rule that inverts ---------------------------------------------------------

def test_oregon_food_serviceware_is_not_the_brand_owner():
    """ORS 459A.866(3) puts the obligation on the first seller. A chain buying branded cups
    from a distributor is not the producer — the single most consequential entry here."""
    v = resolve_attribution("US-OR", franchised=True)
    assert v is not None
    assert v["rule"] == "first_seller"
    assert v["liable_party"] == "supplier"
    assert v["confidence"] == "statutory"
    assert "459A.866(3)" in v["citation"]
    assert "first sells the food serviceware" in (v["quote"] or "")
    # Being franchised must NOT flip Oregon to the franchisor.
    assert "NOT the producer" in v["because"]


def test_oregon_records_orphaning():
    """Where the first seller is itself a small producer, nobody pays. A model that invents a
    liability which legally does not exist is as wrong as one that misses a real one."""
    v = resolve_attribution("US-OR")
    assert "orphaned" in v["notes"]["orphaning"]


def test_franchisor_states_attribute_to_the_brand():
    """CO/ME/MN/MD/WA name the franchisor; CA reaches it through the regulations."""
    for code in ("US-CO", "US-ME", "US-MN", "US-MD", "US-WA", "US-CA"):
        v = resolve_attribution(code, franchised=True)
        assert v is not None, code
        assert v["rule"] == "franchisor", code
        assert v["liable_party"] == "franchisor", code


def test_california_attribution_is_regulatory_not_statutory():
    """CA reaches the franchisor via 14 CCR, not the statute — a regulation is amended far
    more easily, and the UI should weight it accordingly."""
    v = resolve_attribution("US-CA")
    assert v["confidence"] == "regulatory"
    assert "18980.2" in v["citation"]


# --- Sourcing sensitivity ----------------------------------------------------------

def test_italy_answer_depends_on_sourcing_route():
    """Buying domestically discharges the CAC upstream; importing does not. Same law,
    opposite filing obligation."""
    domestic = resolve_attribution("IT", sourcing="domestic_supplier")
    imported = resolve_attribution("IT", sourcing="self_import")
    assert domestic["because"] != imported["because"]
    assert "files nothing" in domestic["because"]
    assert "modulo 6.1" in imported["because"]


def test_sourcing_sensitive_flag_is_set_where_it_matters():
    for code in ("IT", "ES", "DE", "FR", "NL", "IE"):
        assert resolve_attribution(code)["sourcing_sensitive"] is True, code
    # US franchisor states turn on entity structure, not sourcing.
    for code in ("US-CO", "US-MN", "US-WA"):
        assert resolve_attribution(code)["sourcing_sensitive"] is False, code


# --- Regimes are separate ----------------------------------------------------------

def test_regime_changes_the_answer_within_one_jurisdiction():
    """UK pEPR attaches to the brand owner; UK Plastic Packaging Tax attaches to the
    importer/manufacturer at a 10t threshold with no turnover test. Cumulative, not
    alternative — so they cannot share a single verdict."""
    epr = resolve_attribution("UK", "packaging_epr")
    ppt = resolve_attribution("UK", "plastic_tax")
    assert epr["rule"] == "brand_owner"
    assert ppt["rule"] == "importer"
    assert ppt["thresholds"]["tests"][0]["amount"] == 10


def test_unknown_pair_returns_none_not_an_exemption():
    """Silence means we hold no cited rule. It must never be renderable as 'not obligated'."""
    assert resolve_attribution("US-TX") is None
    assert resolve_attribution("UK", "drs") is None


# --- Threshold models --------------------------------------------------------------

def test_us_states_exempt_below_any_limb_but_ireland_needs_both():
    """Polarity differs and it is not cosmetic: Ireland obligates only when BOTH >10t and
    >€1m are met, while a US state exempts you for falling below EITHER limb."""
    assert resolve_attribution("US-WA")["thresholds"]["model"] == "exempt_below_any"
    ie = resolve_attribution("IE")["thresholds"]
    assert ie["model"] == "obligated_above_all"
    assert "on-site" in ie["note"]


def test_uk_is_tiered_with_network_level_aggregation():
    t = resolve_attribution("UK", franchised=True)["thresholds"]
    assert t["model"] == "tiered"
    assert [x["tier"] for x in t["tiers"]] == ["large", "small", "none"]
    assert "NETWORK-level" in t["aggregation"]


def test_california_has_no_tonnage_de_minimis():
    """CA is the only US state here with a revenue test and no tonnage floor, and its revenue
    test is in-jurisdiction rather than global."""
    t = resolve_attribution("US-CA")["thresholds"]
    assert t["no_tonnage_de_minimis"] is True
    assert t["tests"][0]["basis"] == "in_jurisdiction"


def test_threshold_summary_renders_for_every_entry():
    for (code, regime) in ATTRIBUTION:
        v = resolve_attribution(code, regime)
        if v["thresholds"] and (v["thresholds"].get("tests") or v["thresholds"].get("tiers")):
            assert v["threshold_summary"], f"{code}/{regime}"


# --- Exemptions that do not apply to chains ----------------------------------------

def test_restaurant_carve_outs_do_not_rescue_a_chain():
    """Every restaurant/single-store exemption in the table is flagged as not applying to a
    chain — being franchised is itself disqualifying in Oregon and Maryland."""
    for code in ("US-OR", "US-CO", "US-MD"):
        ex = resolve_attribution(code)["exemptions"]
        restaurant = [e for e in ex if e["kind"] in ("restaurant", "single_store")]
        assert restaurant, code
        assert all(e["applies_to_chain"] is False for e in restaurant), code


def test_maine_perishable_exemption_does_apply():
    """Not every exemption is a trap — Maine's first 15 tons of perishable-food packaging is
    genuinely available, and the table must not flatten that distinction."""
    ex = resolve_attribution("US-ME")["exemptions"]
    assert any(e["kind"] == "perishable_food_packaging" and e["applies_to_chain"] for e in ex)


# --- Authorised representative -----------------------------------------------------

def test_authorised_representative_is_a_four_way_split():
    for code in ("FR", "DE", "ES"):
        assert resolve_attribution(code)["authorised_representative"]["required"] is True, code
    for code in ("IT", "NL"):
        assert resolve_attribution(code)["authorised_representative"]["required"] is False, code


def test_spain_records_the_subsidiary_liability_fallback():
    """If no representative is appointed, the first Spanish distributor becomes subsidiarily
    liable — the clause a chain's suppliers will eventually invoke."""
    ar = resolve_attribution("ES")["authorised_representative"]
    assert "subsidiarily liable" in ar["note"]


def test_germany_ar_requirement_is_flagged_as_volatile():
    """The Commission proposed suspending PPWR Art. 45 in Dec 2025. It must be a flag, not a
    constant, or the tool hard-codes an obligation that may vanish."""
    ar = resolve_attribution("DE")["authorised_representative"]
    assert "volatility" in ar and "SUSPENDING" in ar["volatility"]


# --- Honesty about gaps ------------------------------------------------------------

def test_every_entry_carries_an_article_level_citation():
    for (code, regime), entry in ATTRIBUTION.items():
        assert entry.get("citation"), f"{code}/{regime}"
        assert entry["confidence"] in ("statutory", "regulatory", "guidance", "unresolved")


def test_quotes_are_verbatim_or_absent_never_paraphrased():
    """`quote` is either primary-source text or None. This asserts the field is at least
    typed that way; the discipline itself is enforced at curation time."""
    for entry in ATTRIBUTION.values():
        q = entry.get("quote")
        assert q is None or (isinstance(q, str) and len(q) > 20)


def test_uk_records_the_decisive_open_question():
    """Whether a franchisor PAYS on swept-up franchisee tonnage or only REPORTS it decides
    whether an entire franchised estate lands on the franchisor's P&L. It is unresolved and
    must stay visibly unresolved."""
    v = resolve_attribution("UK", franchised=True)
    assert any("PAYS" in q or "P&L" in q for q in v["open_questions"])


def test_coverage_reports_its_own_gaps():
    c = coverage()
    assert c["entries"] == len(ATTRIBUTION)
    assert c["unresolved_questions"] > 0, "a table claiming zero open questions is not credible"
    assert set(c["by_confidence"]) == {"statutory", "regulatory", "guidance", "unresolved"}


# --- Endpoint ----------------------------------------------------------------------

def test_endpoint_returns_all_epr_jurisdictions_by_default():
    resp = client.get("/compliance/producer-attribution")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == len(jurisdictions_for_regime("packaging_epr"))
    assert {r["jurisdiction"] for r in data["rows"]} >= {"US-OR", "US-CA", "UK", "FR", "DE"}


def test_endpoint_filters_by_jurisdiction_and_passes_through_franchised():
    resp = client.get(
        "/compliance/producer-attribution",
        params={"jurisdiction": "US-CO", "franchised": True},
    )
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["rule"] == "franchisor"
    assert "franchisor" in rows[0]["because"]


def test_endpoint_regime_filter_returns_only_that_regime():
    resp = client.get("/compliance/producer-attribution", params={"regime": "plastic_tax"})
    assert resp.status_code == 200
    data = resp.json()
    assert [r["jurisdiction"] for r in data["rows"]] == ["UK"]
    assert data["rows"][0]["rule"] == "importer"


def test_endpoint_unknown_jurisdiction_returns_empty_not_404():
    """An empty result is 'we hold no cited rule', which the caller renders as unknown. A 404
    would invite treating absence as an answer."""
    resp = client.get("/compliance/producer-attribution", params={"jurisdiction": "US-TX"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
