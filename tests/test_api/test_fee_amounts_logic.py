"""Unit tests for the pure logic behind /compliance/fee-amounts — region resolution, the breadth gate,
and row building/filtering. No DB (the SQL fetch is thin and exercised by the smoke test instead)."""
from app.api.compliance import (
    FEE_TEASER_REGION,
    _build_fee_rows,
    _gate_regions,
    _resolve_regions,
)


# --- region resolution (fee endpoints default to ALL, unlike bills.py's US-default) ---

def test_resolve_defaults_to_all():
    assert _resolve_regions(None, None) is None  # None => no region filter => all


def test_resolve_single_region():
    assert _resolve_regions("EU", None) == ["EU"]
    assert _resolve_regions("all", None) is None


def test_resolve_regions_csv_wins():
    assert _resolve_regions("US", "EU,FR") == ["EU", "FR"]
    assert _resolve_regions("US", "all") is None


# --- the breadth gate ---

def test_gate_pro_keeps_scope():
    assert _gate_regions(None, is_pro=True) == (None, False)
    assert _gate_regions(["EU", "FR"], is_pro=True) == (["EU", "FR"], False)


def test_gate_non_pro_forced_to_us_teaser():
    # Whatever a non-Pro caller asked for, they get the US teaser.
    assert _gate_regions(None, is_pro=False) == ([FEE_TEASER_REGION], True)
    assert _gate_regions(["EU", "FR"], is_pro=False) == ([FEE_TEASER_REGION], True)


# --- row building / filtering ---

def _rec(**kw):
    base = {
        "bill_id": 1, "region": "US", "state": "CA", "bill_number": "SB 54",
        "bill_title": "T", "status": "enacted", "source_url": "http://x",
        "material_categories": ["plastic packaging"], "basis": "per_ton",
        "amount": "57.43", "currency": "GBP", "material": "packaging",
        "source_excerpt": "the fee is 57.43 per tonne", "extraction_version": "5",
    }
    base.update(kw)
    return base


def test_build_types_and_grounds():
    rows = _build_fee_rows([_rec()])
    assert len(rows) == 1
    r = rows[0]
    assert r.amount == 57.43 and isinstance(r.amount, float)
    assert r.fee_kind == "producer_fee"
    assert r.grounded is True
    assert r.extraction_version == 5


def test_build_amount_null_and_bad_value():
    assert _build_fee_rows([_rec(amount=None)])[0].amount is None
    assert _build_fee_rows([_rec(amount="tbd")])[0].amount is None  # non-numeric never crashes


def test_build_grounded_false_without_excerpt():
    assert _build_fee_rows([_rec(source_excerpt=None)])[0].grounded is False


def test_has_amount_filter():
    recs = [_rec(bill_id=1, amount="10"), _rec(bill_id=2, amount=None)]
    assert [r.bill_id for r in _build_fee_rows(recs, has_amount=True)] == [1]
    assert [r.bill_id for r in _build_fee_rows(recs, has_amount=False)] == [2]


def test_fee_kind_filter():
    recs = [
        _rec(bill_id=1, basis="per_ton", material="packaging"),                 # producer_fee
        _rec(bill_id=2, basis="flat", material="registration fee"),             # registration
    ]
    assert [r.bill_id for r in _build_fee_rows(recs, fee_kind="registration")] == [2]
    assert [r.bill_id for r in _build_fee_rows(recs, fee_kind="producer_fee")] == [1]


def test_material_category_filter_handles_json_string():
    # material_categories may arrive as a JSON string (driver-dependent) — must still filter.
    recs = [
        _rec(bill_id=1, material_categories='["plastic packaging"]'),
        _rec(bill_id=2, material_categories='["batteries"]'),
    ]
    got = _build_fee_rows(recs, material_category="plastic packaging")
    assert [r.bill_id for r in got] == [1]
