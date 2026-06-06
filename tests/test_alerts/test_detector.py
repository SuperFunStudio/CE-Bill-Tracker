import pytest
from unittest.mock import MagicMock

from app.alerts.detector import ChangeDetector
from app.models import Bill, BillChange


def _make_bill(**kwargs) -> Bill:
    bill = MagicMock(spec=Bill)
    bill.id = kwargs.get("id", 1)
    bill.state = kwargs.get("state", "OR")
    bill.bill_number = kwargs.get("bill_number", "SB 582")
    bill.status = kwargs.get("status", "introduced")
    bill.change_hash = kwargs.get("change_hash", "abc123")
    bill.confidence_score = kwargs.get("confidence_score", 0.9)
    bill.material_categories = kwargs.get("material_categories", ["plastic_packaging"])
    return bill


class TestChangeDetector:
    def setup_method(self):
        self.detector = ChangeDetector()

    def test_detects_status_change(self):
        bill = _make_bill(status="introduced")
        new_data = {"status": "enacted", "change_hash": "abc123"}
        changes = self.detector.detect_changes(bill, new_data)
        assert len(changes) == 1
        assert changes[0].change_type == "status_change"
        assert changes[0].old_value == {"status": "introduced"}
        assert changes[0].new_value == {"status": "enacted"}

    def test_detects_hash_change(self):
        bill = _make_bill(change_hash="abc123")
        new_data = {"status": "introduced", "change_hash": "xyz999"}
        changes = self.detector.detect_changes(bill, new_data)
        text_changes = [c for c in changes if c.change_type == "text_update"]
        assert len(text_changes) == 1

    def test_no_changes_when_same(self):
        bill = _make_bill(status="introduced", change_hash="abc123")
        new_data = {"status": "introduced", "change_hash": "abc123"}
        changes = self.detector.detect_changes(bill, new_data)
        assert len(changes) == 0

    def test_both_changes_detected(self):
        bill = _make_bill(status="in_committee", change_hash="old")
        new_data = {"status": "enacted", "change_hash": "new"}
        changes = self.detector.detect_changes(bill, new_data)
        types = {c.change_type for c in changes}
        assert "status_change" in types
        assert "text_update" in types

    def test_status_change_is_alert_worthy(self):
        bill = _make_bill(confidence_score=0.9)
        change = MagicMock(spec=BillChange)
        change.change_type = "status_change"
        change.new_value = {"status": "enacted"}
        assert self.detector.is_alert_worthy(change, bill)

    def test_low_confidence_text_update_not_alert_worthy(self):
        bill = _make_bill(confidence_score=0.3)
        change = MagicMock(spec=BillChange)
        change.change_type = "text_update"
        change.new_value = {}
        assert not self.detector.is_alert_worthy(change, bill)

    def test_high_confidence_text_update_is_alert_worthy(self):
        bill = _make_bill(confidence_score=0.85)
        change = MagicMock(spec=BillChange)
        change.change_type = "text_update"
        change.new_value = {}
        assert self.detector.is_alert_worthy(change, bill)
