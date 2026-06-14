"""Unit tests for watch-list (scope='watchlist') alert matching.

A watch-list subscription matches the explicit set of bills its owner follows, ignoring the filter
columns and confidence floor. These cover the scope branch in subscription_matches_bill, that federal
actions never match a watch list, and that _merge_subs_by_email keeps watch-list subs separate from
the filter-union rows.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.alerts.digest import (
    _merge_subs_by_email,
    subscription_matches_bill,
    subscription_matches_federal,
)
from app.models import AlertSubscription, Bill, FederalAction


def _watch_sub(**kw) -> AlertSubscription:
    s = MagicMock(spec=AlertSubscription)
    s.scope = "watchlist"
    s.firebase_uid = kw.get("firebase_uid", "uid-1")
    s.email = kw.get("email", "pro@example.com")
    # Filter columns are intentionally restrictive to prove they're ignored for watch-list subs.
    s.states = kw.get("states", ["AZ"])
    s.material_categories = kw.get("material_categories", ["glass"])
    s.instrument_types = kw.get("instrument_types", ["right_to_repair"])
    s.min_confidence = kw.get("min_confidence", 0.99)
    s.alert_on = kw.get("alert_on", ["status_change", "deadline"])
    s.created_at = kw.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    s.active = True
    return s


def _filter_sub(**kw) -> AlertSubscription:
    s = MagicMock(spec=AlertSubscription)
    s.scope = "filter"
    s.firebase_uid = kw.get("firebase_uid")
    s.email = kw.get("email", "filter@example.com")
    s.states = kw.get("states", ["ALL"])
    s.material_categories = kw.get("material_categories", [])
    s.instrument_types = kw.get("instrument_types", ["ALL"])
    s.min_confidence = kw.get("min_confidence", 0.7)
    s.created_at = kw.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    s.active = True
    return s


def _bill(**kw) -> Bill:
    b = MagicMock(spec=Bill)
    b.id = kw.get("id", 1)
    b.state = kw.get("state", "CA")
    b.instrument_type = kw.get("instrument_type", "epr")
    b.material_categories = kw.get("material_categories", ["plastic_packaging"])
    b.confidence_score = kw.get("confidence_score", 0.9)
    return b


class TestWatchlistMatching:
    def test_matches_when_bill_in_set_despite_filters(self):
        sub = _watch_sub()
        bill = _bill(id=42, state="CA", instrument_type="epr", confidence_score=0.1)
        # Bill fails every filter column and the confidence floor, but it's on the watch list.
        assert subscription_matches_bill(sub, bill, watchlist_ids={42, 7})

    def test_excluded_when_bill_not_in_set(self):
        sub = _watch_sub()
        assert not subscription_matches_bill(sub, _bill(id=99), watchlist_ids={42, 7})

    def test_no_resolved_set_matches_nothing(self):
        sub = _watch_sub()
        assert not subscription_matches_bill(sub, _bill(id=42), watchlist_ids=None)

    def test_filter_only_when_no_watchlist_ids(self):
        # A plain filter sub (no watch list resolved) matches purely on filters.
        sub = _filter_sub(states=["GA"])
        assert not subscription_matches_bill(sub, _bill(id=42, state="CA"))
        assert subscription_matches_bill(sub, _bill(id=7, state="GA"))


class TestCombinedMatching:
    """A combined subscriber (filter scope, owns a watch list) matches bills via filters OR the
    explicit watch-list set."""

    def test_matches_watched_bill_failing_filters(self):
        sub = _filter_sub(states=["GA"])  # filter would exclude a CA bill
        assert subscription_matches_bill(sub, _bill(id=42, state="CA"), watchlist_ids={42})

    def test_matches_filter_bill_not_watched(self):
        sub = _filter_sub(states=["GA"])
        assert subscription_matches_bill(sub, _bill(id=7, state="GA"), watchlist_ids={42})

    def test_excludes_bill_neither_watched_nor_in_filters(self):
        sub = _filter_sub(states=["GA"])
        assert not subscription_matches_bill(sub, _bill(id=7, state="CA"), watchlist_ids={42})


class TestWatchlistFederal:
    def test_watchlist_never_matches_federal(self):
        action = MagicMock(spec=FederalAction)
        action.material_categories = ["plastic_packaging"]
        assert not subscription_matches_federal(_watch_sub(instrument_types=["ALL"]), action)


class TestMergeCombinesFilterAndWatch:
    def test_same_email_collapses_to_one_combined_row(self):
        # Same email, one filter + one watch-list sub -> a single combined subscriber.
        filt = _filter_sub(email="same@x.com", states=["GA"], instrument_types=["epr"])
        watch = _watch_sub(email="same@x.com", firebase_uid="uid-9", alert_on=["status_change"])
        merged = _merge_subs_by_email([filt, watch])
        assert len(merged) == 1
        m = merged[0]
        # Combined: filter scope, but carries the watch owner's uid so the matcher ORs in the
        # starred bills, and the watch list's notification prefs.
        assert m.scope == "filter"
        assert m.firebase_uid == "uid-9"
        assert m.states == ["GA"]
        assert set(m.instrument_types) == {"epr"}
        assert m.alert_on == ["status_change"]

    def test_pure_watch_passes_through(self):
        watch = _watch_sub(email="solo@x.com", firebase_uid="uid-3")
        merged = _merge_subs_by_email([watch])
        assert merged == [watch]

    def test_lone_filter_passes_through(self):
        filt = _filter_sub(email="solo@x.com")
        merged = _merge_subs_by_email([filt])
        assert merged == [filt]
