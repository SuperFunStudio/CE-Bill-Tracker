from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.alerts.digest import (
    _merge_subs_by_email,
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
