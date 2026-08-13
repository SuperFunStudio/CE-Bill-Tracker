"""The dispatcher consolidation fix: a cycle's alert-worthy changes collapse into ONE message per
recipient (email + Slack), instead of one message per BillChange.

These drive dispatch_changes with the subscriber-matching and litigation lookups stubbed, so the
focus is the grouping/consolidation and the List-Unsubscribe wiring — not the SQL.
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import app.alerts.dispatcher as dispatcher_mod
from app.alerts.dispatcher import AlertDispatcher, _Bundle
from app.alerts.detector import ChangeDetector


def _bill(bid, **kw):
    return SimpleNamespace(
        id=bid,
        state=kw.get("state", "CA"),
        bill_number=kw.get("bill_number", f"SB {bid}"),
        title=kw.get("title", "A bill"),
        status=kw.get("status", "enacted"),
        instrument_type=kw.get("instrument_type", "epr"),
        material_categories=kw.get("material_categories", ["plastic_packaging"]),
        confidence_score=kw.get("confidence_score", 0.9),
        last_action_date=kw.get("last_action_date", date(2026, 8, 1)),
        status_date=kw.get("status_date", date(2026, 8, 1)),
        source_url=kw.get("source_url", "https://leg.example/bill"),
        ai_summary=kw.get("ai_summary", None),
    )


def _change(bid, change_type="status_change", new_status="enacted"):
    return SimpleNamespace(
        bill_id=bid,
        change_type=change_type,
        old_value={"status": "in_committee"},
        new_value={"status": new_status},
        alert_sent=False,
    )


def _sub(**kw):
    return SimpleNamespace(
        id=kw.get("id", 1),
        active=True,
        scope=kw.get("scope", "filter"),
        firebase_uid=kw.get("firebase_uid"),
        email=kw.get("email", "sub@example.com"),
        slack_webhook=kw.get("slack_webhook"),
        alert_on=kw.get("alert_on", ["status_change", "text_update"]),
        min_confidence=kw.get("min_confidence", 0.0),
    )


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDB:
    """execute() returns the per-change Bill load in call order; subs + litigation are stubbed out."""

    def __init__(self, bills_in_order):
        self._q = list(bills_in_order)
        self.committed = False

    async def execute(self, *_a, **_k):
        return _FakeResult(self._q.pop(0) if self._q else None)

    async def commit(self):
        self.committed = True


def _dispatcher(subs_for_bill):
    d = AlertDispatcher.__new__(AlertDispatcher)  # skip real sender construction
    d.detector = ChangeDetector()
    d.email_sender = AsyncMock()
    d.slack_sender = AsyncMock()

    async def _subs(_db, _bill):
        return subs_for_bill

    d._subscriptions_for_bill = _subs
    return d


def _patch_env(monkeypatch):
    monkeypatch.setattr(dispatcher_mod.settings, "postmark_api_key", "pm-test-token")

    async def _no_litigation(_db, _bill_id):
        return ""

    monkeypatch.setattr(dispatcher_mod, "_get_litigation_context", _no_litigation)


class TestBundle:
    def test_dedupes_bill_and_unions_changes(self):
        b = _bill(1)
        c1, c2 = _change(1), _change(1, change_type="text_update")
        bundle = _Bundle(_sub())
        bundle.add(b, [c1], "")
        bundle.add(b, [c1, c2], "")  # same bill again, overlapping + new change
        items = bundle.items()
        assert len(items) == 1
        bill, changes, _ = items[0]
        assert bill.id == 1
        assert len(changes) == 2 and c1 in changes and c2 in changes  # c1 not duplicated


class TestConsolidation:
    async def test_multiple_bills_one_email(self, monkeypatch):
        _patch_env(monkeypatch)
        sub = _sub(email="one@x.com")
        d = _dispatcher([sub])
        bills = [_bill(1), _bill(2), _bill(3)]
        changes = [_change(1), _change(2), _change(3)]
        db = _FakeDB(bills_in_order=bills)

        await d.dispatch_changes(db, changes)

        # ONE consolidated email, covering all three bills.
        assert d.email_sender.send_consolidated_alert.await_count == 1
        args, kwargs = d.email_sender.send_consolidated_alert.await_args
        assert args[0] == "one@x.com"
        items = args[1]
        assert {b.id for b, _c, _l in items} == {1, 2, 3}
        # List-Unsubscribe wired through.
        assert kwargs["list_unsubscribe_url"]
        assert all(c.alert_sent for c in changes)
        assert db.committed

    async def test_same_email_two_rows_still_one_message(self, monkeypatch):
        _patch_env(monkeypatch)
        # A filter row and a watch-list row for the same address — must not double-send.
        rows = [_sub(id=1, scope="filter"), _sub(id=2, scope="watchlist", firebase_uid="u1")]
        d = _dispatcher(rows)
        await d.dispatch_changes(_FakeDB([_bill(1)]), [_change(1)])
        assert d.email_sender.send_consolidated_alert.await_count == 1

    async def test_slack_consolidated_and_no_email_without_key(self, monkeypatch):
        _patch_env(monkeypatch)
        monkeypatch.setattr(dispatcher_mod.settings, "postmark_api_key", "")  # no email channel
        sub = _sub(email=None, slack_webhook="https://hooks.slack/x")
        d = _dispatcher([sub])
        await d.dispatch_changes(_FakeDB([_bill(1), _bill(2)]), [_change(1), _change(2)])
        assert d.email_sender.send_consolidated_alert.await_count == 0
        assert d.slack_sender.send_consolidated_alert.await_count == 1
        _args, _kw = d.slack_sender.send_consolidated_alert.await_args
        assert {b.id for b, _c, _l in _args[1]} == {1, 2}

    async def test_alert_on_filters_change_types(self, monkeypatch):
        _patch_env(monkeypatch)
        # Subscriber only wants status_change; a text_update-only bill must not reach them.
        sub = _sub(alert_on=["status_change"])
        d = _dispatcher([sub])
        changes = [_change(1, change_type="status_change"), _change(2, change_type="text_update")]
        # bill 2's text_update is alert-worthy only if confidence >= 0.7 (it is), so it survives to
        # grouping — but the subscriber's alert_on excludes it, so only bill 1 lands.
        await d.dispatch_changes(_FakeDB([_bill(1), _bill(2)]), changes)
        assert d.email_sender.send_consolidated_alert.await_count == 1
        items = d.email_sender.send_consolidated_alert.await_args[0][1]
        assert {b.id for b, _c, _l in items} == {1}

    async def test_non_alert_worthy_marked_and_no_send(self, monkeypatch):
        _patch_env(monkeypatch)
        d = _dispatcher([_sub()])
        # status_change to a non-significant status is not alert-worthy.
        change = _change(1, new_status="prefiled")
        await d.dispatch_changes(_FakeDB([_bill(1)]), [change])
        assert d.email_sender.send_consolidated_alert.await_count == 0
        assert change.alert_sent  # still marked handled so it won't be retried forever


class TestOutageHold:
    """A bill change is consumed on dispatch — no later cycle re-derives it — so marking it sent
    while the email channel is dark loses legislative movement silently. That is exactly the risk
    during a provider cutover, when the token is present but every send is rejected."""

    async def test_total_failure_holds_the_batch(self, monkeypatch):
        _patch_env(monkeypatch)
        d = _dispatcher([_sub(email="one@x.com")])
        d.email_sender.send_consolidated_alert = AsyncMock(return_value=False)
        changes = [_change(1), _change(2)]
        db = _FakeDB([_bill(1), _bill(2)])

        await d.dispatch_changes(db, changes)

        # Nobody received it, so holding can't double-send anyone — and the next cycle retries.
        assert not any(c.alert_sent for c in changes)
        assert db.committed

    async def test_partial_failure_still_marks(self, monkeypatch):
        """One bad address must not make everyone else get the alert twice on the next cycle."""
        _patch_env(monkeypatch)
        d = _dispatcher([_sub(id=1, email="good@x.com"), _sub(id=2, email="bad@x.com")])
        d.email_sender.send_consolidated_alert = AsyncMock(side_effect=[True, False])
        changes = [_change(1)]

        await d.dispatch_changes(_FakeDB([_bill(1)]), changes)

        assert d.email_sender.send_consolidated_alert.await_count == 2
        assert all(c.alert_sent for c in changes)

    async def test_slack_only_deployment_is_not_held(self, monkeypatch):
        """With no email channel configured at all there are no email bundles, so the batch is a
        Slack delivery and completes — otherwise a deliberately email-less deployment would retry
        the same changes to Slack forever."""
        _patch_env(monkeypatch)
        monkeypatch.setattr(dispatcher_mod.settings, "postmark_api_key", "")
        d = _dispatcher([_sub(email=None, slack_webhook="https://hooks.slack/x")])
        changes = [_change(1)]
        await d.dispatch_changes(_FakeDB([_bill(1)]), changes)
        assert all(c.alert_sent for c in changes)
