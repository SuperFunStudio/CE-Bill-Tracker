from unittest.mock import MagicMock

from app.alerts.new_bill_alerts import (
    NewBillAlertContent,
    _materials_phrase,
    render_new_bill_alert_subject,
)
from app.models import Bill


def _bill(**kw) -> Bill:
    b = MagicMock(spec=Bill)
    b.state = kw.get("state", "CT")
    b.bill_number = kw.get("bill_number", "SB 457")
    b.title = kw.get("title", "An Act Concerning the State's Bottle Bill")
    b.status = kw.get("status", "introduced")
    b.instrument_type = kw.get("instrument_type", "deposit_return")
    b.material_categories = kw.get("material_categories", ["glass", "metals", "plastic_packaging"])
    return b


class TestMaterialsPhrase:
    def test_single(self):
        assert _materials_phrase(_bill(material_categories=["glass"])) == "glass"

    def test_oxford_join(self):
        phrase = _materials_phrase(_bill(material_categories=["glass", "metals", "plastic_packaging"]))
        assert phrase == "glass, metals and plastic packaging"

    def test_empty_falls_back(self):
        assert _materials_phrase(_bill(material_categories=[])) == "the materials you follow"


class TestNewBillSubject:
    def test_single_names_state_topic_materials(self):
        subject = render_new_bill_alert_subject(NewBillAlertContent(bills=[_bill()]))
        assert subject == "New in CT — a deposit return bill affecting glass, metals and plastic packaging"

    def test_multiple(self):
        content = NewBillAlertContent(bills=[_bill(), _bill(state="OR")])
        assert render_new_bill_alert_subject(content) == "2 new bills on your radar"
