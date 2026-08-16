"""The opt-in contract for the two "extra email" channels (deadline reminders, weekly digest).

Both flags live in AlertSubscription.alert_on, and the invariant under test is: their presence is
ALWAYS an explicit user choice — never a default (models/schemas exclude them; migration 051
stripped the fossil "deadline" the old default left on every row). A subscription without the flag
must be excluded from that channel entirely, and a weekly opt-in must leave the monthly audience so
nobody is double-mailed.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.alerts.deadline_alerts import wants_deadline_alerts
from app.alerts.digest import filter_by_cadence
from app.api.user import DEFAULT_WATCHLIST_ALERT_ON, WATCHLIST_ALERT_EVENTS
from app.models import AlertSubscription
from app.schemas import SubscriptionCreate


def _sub(alert_on) -> AlertSubscription:
    s = MagicMock(spec=AlertSubscription)
    s.email = "a@example.com"
    s.alert_on = alert_on
    s.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    s.active = True
    return s


# --- Defaults never carry the opt-in flags --------------------------------------------------------

def test_watchlist_default_excludes_optin_channels():
    assert "deadline" not in DEFAULT_WATCHLIST_ALERT_ON
    assert "weekly_digest" not in DEFAULT_WATCHLIST_ALERT_ON


def test_watchlist_allowed_events_include_optin_channels():
    # The prefs endpoint cleans against this set — the toggles must survive a round-trip.
    assert "deadline" in WATCHLIST_ALERT_EVENTS
    assert "weekly_digest" in WATCHLIST_ALERT_EVENTS


def test_public_subscribe_default_excludes_deadline():
    assert "deadline" not in SubscriptionCreate().alert_on


def test_model_column_default_excludes_deadline():
    # The Python-side default applied on INSERT — a fresh row must not be silently opted in.
    default = AlertSubscription.__table__.c.alert_on.default.arg(None)
    assert "deadline" not in default
    assert "weekly_digest" not in default


# --- Deadline reminders: no flag, no mail ---------------------------------------------------------

def test_deadline_channel_requires_explicit_flag():
    assert not wants_deadline_alerts(_sub(["status_change", "new_bill"]))
    assert not wants_deadline_alerts(_sub([]))
    assert not wants_deadline_alerts(_sub(None))
    assert wants_deadline_alerts(_sub(["status_change", "deadline"]))


# --- Weekly digest: opt-ins move OUT of monthly (no double-send) ----------------------------------

def test_weekly_cadence_keeps_only_optins():
    opted = _sub(["status_change", "weekly_digest"])
    not_opted = _sub(["status_change"])
    none_prefs = _sub(None)  # merged multi-filter rows carry alert_on=None
    assert filter_by_cadence([opted, not_opted, none_prefs], "weekly") == [opted]


def test_monthly_cadence_excludes_weekly_optins():
    opted = _sub(["status_change", "weekly_digest"])
    not_opted = _sub(["status_change"])
    none_prefs = _sub(None)
    assert filter_by_cadence([opted, not_opted, none_prefs], "monthly") == [not_opted, none_prefs]
