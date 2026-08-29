"""Bill-number agreement between the two US feeds.

The corpus stores ONE canonical form ("HB-4001"). OpenStates emits "HB 4001"; LegiScan emits
the unspaced "HB4001". If the two normalizers disagree, neither feed can recognize a row the
other already wrote, the cross-reference in IngestionCoordinator never fires, and every
overlapping bill is stored twice — which is exactly the state the corpus was in.

So the load-bearing assertion is not either function in isolation: it is that both land on the
SAME string for the same bill.
"""
import pytest

from app.ingestion.coordinator import _normalize_bill_number, _normalize_legiscan_number


@pytest.mark.parametrize("legiscan,openstates,canonical", [
    ("HB4001", "HB 4001", "HB-4001"),
    ("SB123", "SB 123", "SB-123"),
    ("HCR24", "HCR 24", "HCR-24"),
    ("SJR5", "SJR 5", "SJR-5"),
    # US Congress — the BRACE Act, the bill that exposed the federal coverage gap.
    ("HB9615", "HB 9615", "HB-9615"),
    ("HR1154", "HR 1154", "HR-1154"),
])
def test_both_feeds_agree(legiscan, openstates, canonical):
    assert _normalize_legiscan_number(legiscan) == canonical
    assert _normalize_bill_number(openstates) == canonical


@pytest.mark.parametrize("raw,expected", [
    ("hb4001", "HB-4001"),          # case-insensitive
    ("HB 4001", "HB-4001"),         # already spaced
    ("HB-4001", "HB-4001"),         # already canonical — must be idempotent
    ("  SB123  ", "SB-123"),        # surrounding whitespace
    ("", ""),                       # empty stays empty, never "-"
    ("ABC", "ABC"),                 # no digits: passed through, not mangled
])
def test_legiscan_normalization_edges(raw, expected):
    assert _normalize_legiscan_number(raw) == expected


def test_normalization_is_idempotent():
    """The cross-reference compares against values ALREADY stored by a prior run, so a second
    pass over an output must not shift it."""
    for raw in ("HB4001", "HB 4001", "HB-4001", "ABC"):
        once = _normalize_legiscan_number(raw)
        assert _normalize_legiscan_number(once) == once
