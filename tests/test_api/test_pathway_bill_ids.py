"""Tests for the ?bill_ids= scope on GET /compliance/pathways — the per-bill lookup behind the
"What you must do" block on the deadline modal and the bill page.

Pure parser tests only (no DB): the parsing is where the failure modes are — a stray value must not
422 the modal, and the cap must hold. The "an id scope suppresses the US region default" branch keys
off this returning None vs a list, which is what the None cases below pin down.
"""
from app.api.compliance import PATHWAY_BILL_ID_LIMIT, _parse_bill_ids


def test_parses_csv_of_ids():
    assert _parse_bill_ids("1,2,3") == [1, 2, 3]


def test_tolerates_whitespace_and_drops_non_numeric():
    # A stray value is dropped rather than raising — the modal's lookup must never hard-fail.
    assert _parse_bill_ids(" 10 , abc, 20 ,, ") == [10, 20]


def test_empty_and_none_yield_none():
    # None means "no id scope", which is what restores the region default.
    assert _parse_bill_ids(None) is None
    assert _parse_bill_ids("") is None
    assert _parse_bill_ids("abc,,") is None


def test_caps_at_limit():
    raw = ",".join(str(i) for i in range(PATHWAY_BILL_ID_LIMIT + 50))
    assert len(_parse_bill_ids(raw)) == PATHWAY_BILL_ID_LIMIT
