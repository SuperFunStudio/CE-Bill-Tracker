"""Butterfly step placement: the 2026-10-23 methodology decisions, pinned."""
from app.classification.butterfly import butterfly_steps, remanufacturing_evidence


def _bill(**kw):
    base = {"title": "", "ai_summary": "", "instrument_types": [], "material_categories": [],
            "adjacency": None, "compliance_details": None}
    return {**base, **kw}


def test_instruments_place_directly():
    steps = butterfly_steps(_bill(instrument_types=["epr", "right_to_repair"]))
    assert steps == {"collect": "instrument", "maintain": "instrument"}


def test_recycling_target_goes_to_recycle_not_content():
    details = {"collection_targets": {"status": "present", "source_excerpt": "65% of packaging waste shall be recycled",
                                      "targets": [{"material": "all packaging", "percent": 65}]}}
    steps = butterfly_steps(_bill(compliance_details=details))
    assert steps.get("recycle") == "extraction"
    assert "content" not in steps


def test_pure_collection_rate_is_not_recycling():
    details = {"collection_targets": {"status": "present", "source_excerpt": "a collection rate of 45% by weight",
                                      "targets": [{"material": "portable batteries", "percent": 45, "basis": "weight"}]}}
    assert "recycle" not in butterfly_steps(_bill(compliance_details=details))


def test_content_minimum_goes_to_content():
    details = {"recycled_content": {"status": "present", "minimums": [{"material": "PET bottles", "percent": 25}]}}
    assert butterfly_steps(_bill(compliance_details=details)).get("content") == "extraction"


def test_secondary_material_targets_split_by_what_they_govern():
    recovery = {"remanufacturing": {"status": "present", "source_excerpt": "Wiederverwendung und Verwertung",
                                    "secondary_material_targets": [{"material": "ELV components reuse and recovery", "percent": 85}]}}
    content = {"remanufacturing": {"status": "present", "source_excerpt": "",
                                   "secondary_material_targets": [{"material": "EPA-designated items (recovered materials content)"}]}}
    assert butterfly_steps(_bill(compliance_details=recovery)).get("recycle") == "extraction"
    assert butterfly_steps(_bill(compliance_details=content)).get("content") == "extraction"


def test_remanufacturing_needs_a_quote_that_names_it():
    named = {"remanufacturing": {"status": "present", "source_excerpt": "pièces issues de l'économie circulaire"}}
    targets_only = {"remanufacturing": {"status": "present", "source_excerpt": "Art. 32 Abs. 2 Buchstabe g",
                                        "secondary_material_targets": []}}
    assert remanufacturing_evidence(named)
    assert remanufacturing_evidence(targets_only) is None


def test_farm_equipment_repair_is_not_farming():
    steps = butterfly_steps(_bill(title="Right to Repair Farm Equipment", instrument_types=["right_to_repair"]))
    assert "farm" not in steps and steps["maintain"] == "instrument"
    assert "farm" not in butterfly_steps(_bill(title="Solar farm decommissioning"))
    assert butterfly_steps(_bill(material_categories=["agriculture"]))["farm"] == "material"


def test_by_products_land_on_cascades():
    assert butterfly_steps(_bill(adjacency="by_products"))["cascade"] == "by_products"
    assert butterfly_steps(_bill(title="Tax credit for food donation"))["cascade"] == "keyword"
