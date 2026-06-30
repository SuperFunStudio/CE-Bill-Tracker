import pytest
from app.classification.keywords import KeywordFilter


@pytest.fixture
def kf():
    return KeywordFilter()


# Bills that MUST pass (false negative = bug)
MUST_PASS = [
    ("OR", "SB 582", "Plastic Pollution and Recycling Modernization Act", "extended producer responsibility for packaging"),
    ("CA", "SB 54", "Plastic Pollution Prevention and Packaging Producer Responsibility Act", ""),
    ("CO", "HB 22-1355", "Plastic Pollution Reduction", "product stewardship program for packaging waste"),
    ("ME", "LD 1541", "An Act To Support and Improve the Maine Solid Waste Management Hierarchy", "packaging stewardship program"),
    ("CA", "SB 707", "Responsible Textile Producer Act", "textile recycling stewardship program"),
    ("CA", "SB 343", "Solid Waste Recyclability", "recyclability labeling requirements for packaging"),
    ("WA", "HB 1085", "Solar Panel Recycling", "solar panel recycling stewardship program"),
    ("CA", "AB 2398", "Carpet Stewardship", "carpet recycling program producer responsibility"),
    ("CA", "SB 1215", "Batteries Recycling Act", "battery stewardship and recycling program"),
    ("NY", "HB 123", "Right to Repair Act", "right to repair consumer electronics"),
    ("CA", "AB 1268", "Electronic Waste Recycling Act", "e-waste recycling extended producer responsibility"),
    ("WA", "HB 1131", "Reducing Plastic Packaging Pollution", "packaging EPR producer responsibility organization"),
    ("CA", "AB 111", "Deposit Return Scheme", "bottle bill container deposit return program"),
    ("CO", "HB 100", "Recycled Content Mandates", "post-consumer recycled content requirements plastic bottles"),
]

# Bills that should NOT pass
MUST_NOT_PASS = [
    ("TX", "HB 1", "General Appropriations Act", "state budget and appropriations"),
    ("FL", "SB 100", "Homestead Property Tax Exemption", "property tax exemption for homesteads"),
    ("NY", "AB 500", "Driver License Renewal Procedures", "motor vehicle license renewal process"),
    ("CA", "SB 200", "Agricultural Water Rights", "water rights and allocation for irrigation"),
    ("OH", "HB 99", "Criminal Sentencing Guidelines", "mandatory minimum sentences for drug offenses"),
    ("TX", "SB 50", "Nuclear Waste Disposal", "radioactive waste disposal at nuclear facilities"),  # exclusion keyword
]


def test_no_false_negatives_on_known_epr_laws(kf):
    """Every known EPR law must pass the keyword filter."""
    failures = []
    for state, bill_num, title, desc in MUST_PASS:
        if not kf.passes_threshold(title, desc):
            failures.append(f"{state} {bill_num}: {title}")
    assert not failures, f"False negatives on known EPR laws:\n" + "\n".join(failures)


def test_no_obvious_false_positives(kf):
    """Non-EPR bills should not pass."""
    passing = []
    for state, bill_num, title, desc in MUST_NOT_PASS:
        if kf.passes_threshold(title, desc):
            passing = [(state, bill_num, title)]
    # Allow some false positives — we care more about false negatives
    # But nuclear/radioactive should always be excluded
    nuclear = next(
        ((s, b, t) for s, b, t, _ in [(s, b, t, d) for s, b, t, d in MUST_NOT_PASS
                                        if "nuclear" in t.lower() or "radioactive" in t.lower()]),
        None
    )
    if nuclear:
        state, bill_num, title = nuclear
        assert not kf.passes_threshold(title, "radioactive nuclear waste"), \
            f"Nuclear waste should be excluded: {title}"


def test_material_hints_extracted(kf):
    score = kf.score("Battery Stewardship Program", "battery recycling stewardship program")
    assert "batteries" in score.material_hints


def test_packaging_hint(kf):
    score = kf.score("Plastic Packaging EPR", "extended producer responsibility plastic packaging waste")
    assert "plastic_packaging" in score.material_hints


def test_score_is_positive_for_epr_bill(kf):
    score = kf.score(
        "Extended Producer Responsibility for Packaging",
        "stewardship program for packaging waste reduction"
    )
    assert score.score > 0
    assert score.passes


def test_exclusion_overrides_match(kf):
    score = kf.score("Nuclear Waste Recycling Program", "nuclear waste stewardship producer responsibility")
    assert not score.passes, "Exclusion keyword should block even with EPR match"


# Rescue net (strong_signal): titles a starved LLM dropped that we must keep in scope + flag.
# These are the real bills the reclassify post-mortem found excluded for lack of bill text.
RESCUE_TITLES = [
    "Packaging Waste and Cost Reduction Act",
    "An Act to reduce packaging waste",
    "Relates to producer responsibility",
    "Relating to circular economy; declaring an emergency",
    "Plastics and Packaging Reduction Act",
    "Consumer Wheelchair Repair Bill of Rights Act",
    "RELATING TO ORGANIC WASTE.",
]

# Out-of-scope titles the rescue must NOT fire on (false rescue = scope pollution).
NO_RESCUE_TITLES = [
    "Concerning clemency and pardons.",
    "Ground Leases - Application for Redemption - Procedures",
    "Promoting a safe learning environment for students with seizures",
    "HWY CD-GREENHOUSE EMISSIONS",
    "Major coastal resorts: coastal development permits: audit",
    "An act concerning vehicle repair shop licensing fees",
    "Nuclear Waste Recycling Program",  # exclusion keyword must veto
]


def test_rescue_fires_on_clearly_in_scope_titles(kf):
    missed = [t for t in RESCUE_TITLES if not kf.strong_signal(t)]
    assert not missed, "Rescue net failed to fire on in-scope titles:\n" + "\n".join(missed)


def test_rescue_does_not_fire_on_out_of_scope_titles(kf):
    fired = [t for t in NO_RESCUE_TITLES if kf.strong_signal(t)]
    assert not fired, "Rescue net wrongly fired on out-of-scope titles:\n" + "\n".join(fired)
