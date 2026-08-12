"""Tests for AlertSubscription.set_active — migration 048's provenance rules.

The bug being fixed is that `active` was written directly from two call sites and neither recorded
who did it, so an admin mute and a real unsubscribe were indistinguishable afterwards. These tests
pin the three rules that make the columns trustworthy: the source is recorded, re-muting doesn't
overwrite when they actually left, and reactivating clears the spell instead of leaving a live
subscriber looking churned.
"""
from datetime import datetime, timedelta, timezone

from app.models import AlertSubscription


def _sub(active=True):
    s = AlertSubscription()
    s.active = active
    s.deactivated_at = None
    s.deactivation_source = None
    return s


def test_deactivating_records_when_and_why():
    s = _sub()
    s.set_active(False, source="self_unsubscribe")
    assert s.active is False
    assert s.deactivation_source == "self_unsubscribe"
    assert s.deactivated_at is not None


def test_admin_mute_and_self_unsubscribe_are_distinguishable():
    """The whole point. Both set active=False; only the source separates them."""
    muted, left = _sub(), _sub()
    muted.set_active(False, source="admin_mute")
    left.set_active(False, source="self_unsubscribe")
    assert muted.active == left.active is False
    assert muted.deactivation_source != left.deactivation_source


def test_remuting_does_not_overwrite_the_original_departure():
    """An admin muting an already-unsubscribed row must not rewrite history to say we muted them —
    that would turn a churn event into an admin action and silently lose the real date."""
    s = _sub()
    s.set_active(False, source="self_unsubscribe")
    original_when = s.deactivated_at
    s.deactivated_at = original_when - timedelta(days=7)  # pretend it happened a week ago
    s.set_active(False, source="admin_mute")
    assert s.deactivation_source == "self_unsubscribe"
    assert s.deactivated_at == original_when - timedelta(days=7)


def test_reactivating_clears_the_spell():
    """Stale provenance on a live subscriber would report them as churned forever."""
    s = _sub()
    s.set_active(False, source="admin_mute")
    s.set_active(True, source="admin_mute")
    assert s.active is True
    assert s.deactivated_at is None
    assert s.deactivation_source is None


def test_unknown_source_stays_none_rather_than_being_guessed():
    """Pre-048 rows carry NULL. A caller that doesn't know must be able to say so — inventing a
    plausible value is worse than admitting the information was never recorded."""
    s = _sub()
    s.set_active(False)
    assert s.active is False
    assert s.deactivation_source is None
    assert s.deactivated_at is not None


def test_deactivated_at_is_timezone_aware():
    """Naive timestamps compared against a tz-aware column silently break churn windows."""
    s = _sub()
    s.set_active(False, source="admin_mute")
    assert s.deactivated_at.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - s.deactivated_at).total_seconds()) < 60
