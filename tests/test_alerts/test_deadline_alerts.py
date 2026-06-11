from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from app.alerts.deadline_alerts import (
    DeadlineAlertContent,
    DeadlineItem,
    _deadline_matches,
    render_deadline_alert_subject,
)
from app.alerts.dispatcher import AlertDispatcher
from app.models import AlertSubscription, Bill, ComplianceDeadline, FederalAction


def _sub(**kw) -> AlertSubscription:
    s = MagicMock(spec=AlertSubscription)
    s.email = kw.get("email", "a@example.com")
    s.organization = kw.get("organization")
    s.states = kw.get("states", ["ALL"])
    s.material_categories = kw.get("material_categories", [])
    s.instrument_types = kw.get("instrument_types", ["ALL"])
    s.min_confidence = kw.get("min_confidence", 0.7)
    s.created_at = kw.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    s.active = True
    return s


def _bill(**kw) -> Bill:
    b = MagicMock(spec=Bill)
    b.state = kw.get("state", "CA")
    b.instrument_type = kw.get("instrument_type", "epr")
    b.material_categories = kw.get("material_categories", ["plastic_packaging"])
    b.confidence_score = kw.get("confidence_score", 0.9)
    return b


def _item(days_until=10, *, bill=None, federal_action_id=None, state="CA",
          deadline_type="compliance", deadline_date=date(2026, 7, 1)) -> DeadlineItem:
    d = MagicMock(spec=ComplianceDeadline)
    d.bill = bill
    d.federal_action_id = federal_action_id
    d.state = state
    d.deadline_type = deadline_type
    d.deadline_date = deadline_date
    return DeadlineItem(deadline=d, days_until=days_until)


class TestDeadlineMatches:
    def test_bill_linked_uses_topic_and_state(self):
        # Delegates to subscription_matches_bill: a topic mismatch on the linked bill excludes.
        on_topic = _sub(instrument_types=["epr"])
        off_topic = _sub(instrument_types=["right_to_repair"])
        item = _item(bill=_bill(instrument_type="epr"))
        assert _deadline_matches(on_topic, item, {})
        assert not _deadline_matches(off_topic, item, {})

    def test_bill_linked_respects_state(self):
        sub = _sub(states=["OR"])
        assert not _deadline_matches(sub, _item(bill=_bill(state="CA")), {})
        assert _deadline_matches(sub, _item(bill=_bill(state="OR")), {})

    def test_federal_linked_matches_epr_followers(self):
        action = MagicMock(spec=FederalAction)
        action.material_categories = ["plastic_packaging"]
        item = _item(bill=None, federal_action_id=7)
        assert _deadline_matches(_sub(instrument_types=["epr"]), item, {7: action})
        assert not _deadline_matches(_sub(instrument_types=["right_to_repair"]), item, {7: action})

    def test_bare_deadline_matches_on_jurisdiction_only(self):
        item = _item(bill=None, federal_action_id=None, state="WA")
        assert _deadline_matches(_sub(states=["ALL"]), item, {})
        assert _deadline_matches(_sub(states=["WA"]), item, {})
        assert not _deadline_matches(_sub(states=["CA"]), item, {})


class TestDeadlineSubject:
    def test_multiple_counts_and_soonest_lead(self):
        content = DeadlineAlertContent(items=[_item(days_until=21), _item(days_until=5)])
        subject = render_deadline_alert_subject(content)
        assert "2 compliance deadlines" in subject
        assert "in 5 days" in subject

    def test_single_uses_loss_countdown_and_bill(self):
        bill = _bill(state="CA")
        bill.bill_number = "SB 54"
        bill.status = "enacted"
        content = DeadlineAlertContent(items=[_item(days_until=47, bill=bill)])
        subject = render_deadline_alert_subject(content)
        assert subject.startswith("47 days — CA SB 54")
        assert "due Jul 1" in subject

    def test_single_today(self):
        content = DeadlineAlertContent(items=[_item(days_until=0)])
        subject = render_deadline_alert_subject(content)
        assert subject.startswith("Due today")


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_a, **_k):
        return _Result(self._rows)


class TestDispatcherScoping:
    """The dispatcher fix: real-time alert matching now respects the topic (instrument_type) and
    treats an empty material list as match-all (it previously did neither)."""

    async def test_off_topic_subscriber_excluded(self):
        dispatcher = AlertDispatcher.__new__(AlertDispatcher)  # skip sender construction
        epr = _sub(email="epr@x.com", instrument_types=["epr"])
        rtr = _sub(email="rtr@x.com", instrument_types=["right_to_repair"])
        bill = _bill(instrument_type="right_to_repair")
        matched = await dispatcher._subscriptions_for_bill(_DB([epr, rtr]), bill)
        emails = {s.email for s in matched}
        assert emails == {"rtr@x.com"}

    async def test_empty_material_list_matches(self):
        dispatcher = AlertDispatcher.__new__(AlertDispatcher)
        sub = _sub(material_categories=[])  # empty = "all materials"
        bill = _bill(material_categories=["glass"])
        matched = await dispatcher._subscriptions_for_bill(_DB([sub]), bill)
        assert len(matched) == 1
