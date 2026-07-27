"""Unit tests for the fee_kind classifier — pure, no DB.

Cases are drawn from real prod fee_amounts.rates[] descriptors (docs/FEE_DATA_API_SPEC.md §4) so the
ordered rules are pinned against the actual corpus noise the classifier exists to cut through.
"""
from app.synthesis.fee_kind import FEE_KINDS, classify_fee_kind


def test_all_labels_are_known():
    # Every possible return value is a declared kind.
    assert set(FEE_KINDS) == {
        "producer_fee", "registration", "incentive", "penalty",
        "threshold", "admin_cost", "unspecified",
    }


def test_penalty_beats_everything():
    # A fine is a penalty even though "flat" basis would otherwise read as a producer fee.
    assert classify_fee_kind("flat", "Administrative fine minimum (violations of Article 4(4))") == "penalty"
    assert classify_fee_kind("per_unit", "Penalty per non-compliant unit placed on market") == "penalty"


def test_threshold_deminimis():
    assert classify_fee_kind("flat", "Minimum threshold below which no product fee is due (annual total)") == "threshold"
    assert classify_fee_kind("percent_revenue", "de-minimis turnover floor below which producer is exempt") == "threshold"


def test_incentive_direction_guard():
    # Money flowing TO a consumer/technician is an incentive, not a producer fee — even with a per_unit basis.
    assert classify_fee_kind("per_unit", "mattresses recycled or reused by nonprofit (minimum social impact payment)") == "incentive"
    assert classify_fee_kind("per_unit", "mercury-added thermostat returned to consumer (minimum financial incentive)") == "incentive"
    assert classify_fee_kind("flat", "container deposit refunded to the consumer on return") == "incentive"


def test_registration_fee():
    assert classify_fee_kind("flat", "Computer manufacturer initial registration fee") == "registration"
    assert classify_fee_kind("flat", "Producer registration fee (per producer per year)") == "registration"
    assert classify_fee_kind("flat", "annual renewal fee for producers") == "registration"


def test_admin_cost():
    assert classify_fee_kind("flat", "agency oversight cost recovery cap") == "admin_cost"
    assert classify_fee_kind("flat", "program administrative cost, allocated pro rata") == "admin_cost"


def test_producer_fee_by_basis_residual():
    # No descriptor keyword, but a producer-fee basis → producer_fee.
    assert classify_fee_kind("per_ton", "All packaging placed on market") == "producer_fee"
    assert classify_fee_kind("per_unit", "beverage containers") == "producer_fee"
    assert classify_fee_kind("percent_revenue", "net revenues from placing equipment on market") == "producer_fee"
    assert classify_fee_kind("eco_modulated", "fee adjusted by recyclability grade") == "producer_fee"


def test_unspecified_when_ambiguous():
    # A flat amount with no telling descriptor is not force-fit into producer_fee.
    assert classify_fee_kind("flat", "amount to be determined by the council") == "unspecified"
    assert classify_fee_kind("unspecified", "") == "unspecified"
    assert classify_fee_kind(None, None) == "unspecified"


def test_order_registration_before_producer_basis():
    # A per_ton basis that is actually a registration descriptor → registration wins (rule order).
    assert classify_fee_kind("per_ton", "annual producer fee for scheme membership") == "registration"
