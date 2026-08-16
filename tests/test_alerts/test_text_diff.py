"""compute_text_diff — the "what changed" payload behind text_update alerts.

The contract that matters most: a whitespace-only re-render must come back `empty` (the detector
suppresses the alert on that), and a real amendment must produce bounded hunks with honest full
counts even when truncated.
"""
from unittest.mock import MagicMock

from app.alerts.detector import ChangeDetector
from app.alerts.text_diff import MAX_HUNKS, compute_text_diff
from app.models import Bill, BillChange


def test_whitespace_only_change_is_empty():
    old = "Section 1. Producers shall register.\nSection 2. Fees apply."
    new = "Section 1.   Producers shall register.\n\n\nSection 2. Fees\tapply.\n"
    d = compute_text_diff(old, new)
    assert d["empty"] is True
    assert d["hunks"] == []


def test_real_change_produces_hunks_and_counts():
    old = "Section 1. Producers shall register.\nSection 2. The fee is $500."
    new = "Section 1. Producers shall register.\nSection 2. The fee is $5,000.\nSection 3. Penalties apply."
    d = compute_text_diff(old, new)
    assert d["empty"] is False
    assert d["added"] == 2  # amended fee line + new section
    assert d["removed"] == 1  # old fee line
    joined = "\n".join(d["hunks"])
    assert "+Section 2. The fee is $5,000." in joined
    assert "-Section 2. The fee is $500." in joined


def test_large_rewrite_is_truncated_but_counts_stay_honest():
    old = "\n".join(f"old line {i}" for i in range(400))
    new = "\n".join(f"new line {i}" for i in range(400))
    d = compute_text_diff(old, new)
    assert d["truncated"] is True
    assert len(d["hunks"]) <= MAX_HUNKS
    # Counts cover the WHOLE diff, not just the shown hunks, so "+400 / −400 lines" stays true.
    assert d["added"] == 400
    assert d["removed"] == 400


def test_detector_suppresses_empty_diff_but_fails_open_without_one():
    det = ChangeDetector()
    bill = MagicMock(spec=Bill)
    bill.confidence_score = 0.9

    def change(new_value):
        c = MagicMock(spec=BillChange)
        c.change_type = "text_update"
        c.old_value = {"change_hash": "a"}
        c.new_value = new_value
        return c

    # Formatting-only re-render: diff computed and empty → not alert-worthy.
    assert det.is_alert_worthy(change({"change_hash": "b", "diff": {"empty": True}}), bill) is False
    # Real amendment: alert-worthy.
    assert det.is_alert_worthy(
        change({"change_hash": "b", "diff": {"empty": False, "hunks": ["@@\n+x"]}}), bill
    ) is True
    # No diff attached (older rows, unindexable text): fail open, alert as before.
    assert det.is_alert_worthy(change({"change_hash": "b"}), bill) is True
