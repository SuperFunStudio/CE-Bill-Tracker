from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.alerts.digest import (
    DigestContent,
    StatusChangeItem,
    _merge_subs_by_email,
    newly_tracked_activity_floor,
    render_digest_html,
    subscription_matches_bill,
    subscription_matches_federal,
)
from app.models import AlertSubscription, Bill, FederalAction


def _scope_from_states(states: list | None) -> dict:
    """Translate the legacy flat `states` list into the region-keyed region_scope the matcher now
    reads (migration 032). "ALL"/empty means match-all → {} ; otherwise US-scoped to those states."""
    if not states or "ALL" in states:
        return {}
    return {"US": states}


def _sub(**kw) -> AlertSubscription:
    s = MagicMock(spec=AlertSubscription)
    s.scope = kw.get("scope", "filter")
    s.firebase_uid = kw.get("firebase_uid")
    s.email = kw.get("email", "a@example.com")
    s.organization = kw.get("organization")
    s.states = kw.get("states", ["ALL"])  # legacy column, kept for the merge tests
    # region_scope is what the matcher actually reads; derive it from `states` (or pass explicitly).
    s.region_scope = kw.get("region_scope", _scope_from_states(s.states))
    s.material_categories = kw.get("material_categories", [])
    s.instrument_types = kw.get("instrument_types", ["ALL"])
    s.min_confidence = kw.get("min_confidence", 0.7)
    s.created_at = kw.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    s.active = True
    return s


def _bill(**kw) -> Bill:
    b = MagicMock(spec=Bill)
    b.id = kw.get("id", 1)
    b.region = kw.get("region", "US")
    b.state = kw.get("state", "CA")
    b.instrument_type = kw.get("instrument_type", "epr")
    b.material_categories = kw.get("material_categories", ["plastic_packaging"])
    b.confidence_score = kw.get("confidence_score", 0.9)
    return b


class TestSubscriptionMatchesBill:
    def test_all_filters_match_everything(self):
        assert subscription_matches_bill(_sub(), _bill(state="OR", instrument_type="labeling"))

    def test_state_filter_excludes_other_states(self):
        sub = _sub(states=["AZ", "GA", "DE"])
        assert not subscription_matches_bill(sub, _bill(state="CA"))
        assert subscription_matches_bill(sub, _bill(state="GA"))

    def test_topic_filter_excludes_other_topics(self):
        sub = _sub(instrument_types=["epr", "right_to_repair"])
        assert not subscription_matches_bill(sub, _bill(instrument_type="deposit_return"))
        assert subscription_matches_bill(sub, _bill(instrument_type="epr"))

    def test_confidence_floor(self):
        sub = _sub(min_confidence=0.8)
        assert not subscription_matches_bill(sub, _bill(confidence_score=0.5))
        assert subscription_matches_bill(sub, _bill(confidence_score=0.85))

    def test_material_filter_only_when_specific(self):
        # Empty material list = match-all, regardless of bill materials.
        assert subscription_matches_bill(_sub(material_categories=[]), _bill(material_categories=["glass"]))
        # Specific material list requires overlap.
        sub = _sub(material_categories=["plastic_packaging"])
        assert not subscription_matches_bill(sub, _bill(material_categories=["glass"]))
        assert subscription_matches_bill(sub, _bill(material_categories=["plastic_packaging"]))


class TestRegionScope:
    """Direct coverage of the region-keyed scope matching added in migration 032 — a US-scoped
    subscriber must never receive alerts for another region's bills, and a whole-region wildcard
    covers every jurisdiction in that region."""

    def test_us_scope_excludes_foreign_region(self):
        # A subscriber scoped to US states does NOT match an EU-region bill (region isn't a scope key).
        sub = _sub(region_scope={"US": ["CA", "OR"]})
        assert not subscription_matches_bill(sub, _bill(region="EU", state="DE"))
        assert subscription_matches_bill(sub, _bill(region="US", state="CA"))

    def test_whole_region_wildcard_matches_any_jurisdiction(self):
        sub = _sub(region_scope={"EU": ["*"]})
        assert subscription_matches_bill(sub, _bill(region="EU", state="FR"))
        assert subscription_matches_bill(sub, _bill(region="EU", state="IT"))
        assert not subscription_matches_bill(sub, _bill(region="US", state="CA"))

    def test_multi_region_scope_matches_each(self):
        sub = _sub(region_scope={"US": ["CA"], "EU": ["*"]})
        assert subscription_matches_bill(sub, _bill(region="US", state="CA"))
        assert subscription_matches_bill(sub, _bill(region="EU", state="FR"))
        assert not subscription_matches_bill(sub, _bill(region="US", state="TX"))

    def test_empty_scope_matches_all_regions(self):
        sub = _sub(region_scope={})
        assert subscription_matches_bill(sub, _bill(region="US", state="CA"))
        assert subscription_matches_bill(sub, _bill(region="EU", state="FR"))


class TestSubscriptionMatchesFederal:
    def _action(self, materials=None):
        a = MagicMock(spec=FederalAction)
        a.material_categories = materials if materials is not None else ["plastic_packaging"]
        return a

    def test_epr_or_all_topics_included(self):
        assert subscription_matches_federal(_sub(instrument_types=["ALL"]), self._action())
        assert subscription_matches_federal(_sub(instrument_types=["epr"]), self._action())

    def test_non_epr_topics_excluded(self):
        sub = _sub(instrument_types=["right_to_repair"])
        assert not subscription_matches_federal(sub, self._action())


class TestMergeSubsByEmail:
    def test_single_sub_passthrough(self):
        subs = [_sub(email="solo@x.com")]
        assert len(_merge_subs_by_email(subs)) == 1

    def test_dedupes_and_unions_scope(self):
        a = _sub(email="dup@x.com", states=["AZ", "GA"], instrument_types=["epr"], min_confidence=0.8)
        b = _sub(email="DUP@x.com", states=["ALL"], instrument_types=["right_to_repair"], min_confidence=0.6)
        merged = _merge_subs_by_email([a, b])
        assert len(merged) == 1
        m = merged[0]
        assert m.states == ["ALL"]  # any match-all collapses to ALL
        assert set(m.instrument_types) == {"epr", "right_to_repair"}
        assert m.min_confidence == 0.6  # broadest (lowest) floor

    def test_skips_emailless_subs(self):
        assert _merge_subs_by_email([_sub(email=None)]) == []


class TestEventDatedWindow:
    """A subscriber's monthly digest reported Illinois HB-3098 (CONSUMER ELECTRONICS RECYCLING) as
    an action of that month. The law was signed 2025-08-15; only our ingestion of it was recent.

    Both bill sections filtered purely on ingestion timestamps — `BillChange.detected_at` and
    `Bill.created_at` — so any re-ingest or historical backfill republished old law as current
    movement. The SQL now also bounds the legislative date; these tests pin the boundary the query
    uses and the dateline the reader sees.
    """

    def test_newly_tracked_floor_is_three_windows_back(self):
        """Lenient enough for a bill introduced weeks before we first saw it; strict enough that a
        2025 enactment ingested in 2026 cannot present itself as this month's news."""
        since = datetime(2026, 7, 8, tzinfo=timezone.utc)
        now = datetime(2026, 8, 7, tzinfo=timezone.utc)  # 30-day window
        floor = newly_tracked_activity_floor(since, now)
        assert floor == date(2026, 5, 9)
        assert date(2025, 8, 15) < floor  # IL HB-3098's real enactment date, excluded

    def test_floor_scales_with_the_window(self):
        """A weekly digest gets a proportionally tighter floor than a monthly one — the guard is
        relative to the cadence, not a hardcoded number of days."""
        now = datetime(2026, 8, 7, tzinfo=timezone.utc)
        weekly = newly_tracked_activity_floor(now - timedelta(days=7), now)
        monthly = newly_tracked_activity_floor(now - timedelta(days=30), now)
        assert weekly > monthly

    def test_status_change_line_carries_the_action_date(self):
        """'Enacted' with no date, inside a monthly roundup, asserts 'this month'."""
        bill = MagicMock(spec=Bill)
        bill.id = 83341
        bill.state = "IL"
        bill.bill_number = "HB-3098"
        bill.title = "CONSUMER ELECTRONICS RECYCLING"
        bill.instrument_type = "epr"
        bill.policy_stance = None
        bill.last_action_date = date(2025, 8, 15)
        bill.status_date = date(2025, 8, 15)
        content = DigestContent(
            status_changes=[
                StatusChangeItem(
                    bill=bill,
                    old_status="passed",
                    new_status="enacted",
                    detected_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                )
            ]
        )
        html = render_digest_html(_sub(), content, "monthly")
        assert "15 Aug 2025" in html
