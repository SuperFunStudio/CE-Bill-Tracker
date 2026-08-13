"""Pins the double opt-in on the public sign-up.

POST /subscriptions is anonymous: the address in the body is an assertion by whoever sent the
request, not a fact about who owns the inbox. Before migration 049 that assertion was enough to
create an active, immediately-mailable subscription, so anyone could sign up anyone — the
list-bombing hole, whose cost lands on our sending domain rather than on the attacker.

The properties worth pinning are the ones that would silently regress:

  1. A fresh emailed sign-up is INACTIVE and unconfirmed. Every send path filters `active IS TRUE`,
     so this single flag is what makes the whole email fleet fail closed. A future refactor that
     "helpfully" restores active=True would reopen the hole with no other visible symptom.
  2. Signup sends the CONFIRMATION, never the welcome roundup. The welcome is what the attacker
     wanted delivered to the victim.
  3. Confirm and unsubscribe tokens are not interchangeable. They travel through the same inboxes
     and forwarding chains; a confirm link that also unsubscribed (or an unsubscribe link that
     could re-confirm a lapsed address) would defeat the point of having either.
  4. Confirming is idempotent, and a re-clicked confirm link can never resurrect someone who
     unsubscribed afterwards.
"""
import types
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.alerts.unsubscribe import CONFIRM, UNSUBSCRIBE, confirm_url, make_token, verify_token
from app.alerts.welcome_email import render_confirm_html, send_confirmation_email
from app.api.alerts import router
from app.config import settings
from app.database import get_db
from app.models import AlertSubscription
from app.ratelimit import limiter
from tests.test_alerts.conftest import _email_off, _email_on


# --- token purposes ------------------------------------------------------------------------------


def test_confirm_token_is_rejected_by_the_unsubscribe_purpose():
    token = make_token(7, CONFIRM)
    assert verify_token(token, CONFIRM) == 7
    assert verify_token(token, UNSUBSCRIBE) is None


def test_unsubscribe_token_is_rejected_by_the_confirm_purpose():
    token = make_token(7, UNSUBSCRIBE)
    assert verify_token(token, UNSUBSCRIBE) == 7
    assert verify_token(token, CONFIRM) is None


def test_legacy_bare_id_token_still_unsubscribes():
    # Unsubscribe links already sitting in delivered mail carry the original bare-id payload. They
    # have to keep working: the alternative is a recipient who clicks unsubscribe and stays subscribed.
    assert verify_token(make_token(42), UNSUBSCRIBE) == 42


def test_tampered_token_is_rejected():
    token = make_token(1, CONFIRM)
    payload, _, sig = token.rpartition(".")
    assert verify_token(f"confirm:999.{sig}", CONFIRM) is None  # swapped id, original signature
    assert verify_token(f"{payload}.{sig}x", CONFIRM) is None   # mangled signature


# --- endpoint behaviour --------------------------------------------------------------------------


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """Enough AsyncSession for these two handlers: one canned lookup result, and add/commit/refresh
    that record rather than persist. `added` holds whatever the endpoint constructed, which is the
    object the assertions are actually about."""

    def __init__(self, found=None):
        self.found = found
        self.added: list = []
        self.commits = 0

    async def execute(self, *_a, **_kw):
        return _Result(self.found)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        # Stand in for the column defaults the real flush applies. `active` matters most: the model
        # defaults it to True, so a handler that simply DOESN'T set it ends up mailable — which is
        # exactly the regression these tests exist to catch, and it would be invisible if the fake
        # left the attribute None.
        if obj.id is None:
            obj.id = 1
        if obj.active is None:
            obj.active = True
        if obj.created_at is None:
            obj.created_at = datetime.now(timezone.utc)


def _client(session, monkeypatch, sent: list):
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: session
    # Record which background email would fire, without sending anything.
    monkeypatch.setattr(
        "app.api.alerts.send_confirmation_for_subscription",
        lambda sub_id: sent.append(("confirmation", sub_id)),
    )
    monkeypatch.setattr(
        "app.api.alerts.send_welcome_for_subscription",
        lambda sub_id: sent.append(("welcome", sub_id)),
    )
    return TestClient(app)


def test_email_signup_is_created_inactive_and_unconfirmed(monkeypatch):
    session = _FakeSession(found=None)
    sent: list = []
    resp = _client(session, monkeypatch, sent).post(
        "/subscriptions", json={"email": "stranger@example.com"}
    )
    assert resp.status_code == 201
    sub = session.added[0]
    # The gate itself. If this ever comes back True, the sign-up is mailable before anyone at that
    # address has agreed to hear from us.
    assert sub.active is False
    assert sub.confirmed_at is None


def test_email_signup_sends_the_confirmation_not_the_welcome(monkeypatch):
    session = _FakeSession(found=None)
    sent: list = []
    _client(session, monkeypatch, sent).post("/subscriptions", json={"email": "a@example.com"})
    assert [kind for kind, _ in sent] == ["confirmation"]


def test_signup_reuses_an_existing_unconfirmed_row(monkeypatch):
    # Otherwise a stranger re-POSTing the same victim address just stacks up rows (and confirmation
    # emails) with only the per-IP rate limit in the way.
    pending = AlertSubscription(email="a@example.com", scope="filter", active=False)
    session = _FakeSession(found=pending)
    sent: list = []
    resp = _client(session, monkeypatch, sent).post(
        "/subscriptions", json={"email": "a@example.com", "instrument_types": ["epr"]}
    )
    assert resp.status_code == 201
    assert session.added == []            # nothing new created
    assert pending.instrument_types == ["epr"]   # the pending row took the new scope
    assert pending.active is False


def test_slack_only_subscription_stays_active(monkeypatch):
    # No address to confirm, so the confirmation gate doesn't apply — and must not silently disable
    # the Slack integration.
    session = _FakeSession(found=None)
    sent: list = []
    resp = _client(session, monkeypatch, sent).post(
        "/subscriptions", json={"slack_webhook": "https://hooks.slack.test/x"}
    )
    assert resp.status_code == 201
    sub = session.added[0]
    assert sub.active is True
    assert sub.confirmed_at is not None
    assert sent == []


def test_confirm_activates_and_fires_the_welcome(monkeypatch):
    sub = AlertSubscription(id=5, email="a@example.com", scope="filter", active=False)
    session = _FakeSession(found=sub)
    sent: list = []
    resp = _client(session, monkeypatch, sent).get(
        f"/subscriptions/confirm?token={make_token(5, CONFIRM)}"
    )
    assert resp.status_code == 200
    assert sub.active is True
    assert sub.confirmed_at is not None
    # The roundup they signed up for fires HERE, not at signup — signup is the moment we still don't
    # know whose address it is.
    assert sent == [("welcome", 5)]


def test_confirm_rejects_an_unsubscribe_token(monkeypatch):
    sub = AlertSubscription(id=5, email="a@example.com", scope="filter", active=False)
    session = _FakeSession(found=sub)
    sent: list = []
    resp = _client(session, monkeypatch, sent).get(
        f"/subscriptions/confirm?token={make_token(5, UNSUBSCRIBE)}"
    )
    assert resp.status_code == 400
    assert sub.active is False
    assert sent == []


def test_reconfirming_does_not_resend_or_resurrect(monkeypatch):
    # An old confirm link, clicked after the recipient unsubscribed. Mail clients prefetch links and
    # people click twice, so this must be inert — never an undo of a deliberate opt-out.
    sub = AlertSubscription(
        id=5,
        email="a@example.com",
        scope="filter",
        active=False,
        confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    session = _FakeSession(found=sub)
    sent: list = []
    resp = _client(session, monkeypatch, sent).get(
        f"/subscriptions/confirm?token={make_token(5, CONFIRM)}"
    )
    assert resp.status_code == 200
    assert sub.active is False   # stays unsubscribed
    assert sent == []            # and gets no second welcome


@pytest.mark.parametrize("token", ["", "garbage", "5.notasignature"])
def test_confirm_rejects_junk_tokens(monkeypatch, token):
    session = _FakeSession(found=None)
    resp = _client(session, monkeypatch, []).get(f"/subscriptions/confirm?token={token}")
    assert resp.status_code == 400


# --- the confirmation email ----------------------------------------------------------------------


class TestConfirmationEmail:
    """The one email an unconfirmed address ever receives. Two things carry real weight: the link
    (without it the sign-up is a dead row nobody can rescue) and the escape hatch for the person who
    didn't sign up — the whole reason this email exists is that they might not have."""

    def _sub(self):
        return types.SimpleNamespace(
            id=42,
            email="a@example.com",
            organization=None,
            states=["CA"],
            instrument_types=["epr"],
            material_categories=["packaging"],
            region_scope=None,
            scope="filter",
            firebase_uid=None,
            min_confidence=0.0,
            alert_on=["new_bill"],
        )

    def test_carries_the_confirm_link(self):
        html = render_confirm_html(self._sub())
        assert confirm_url(42) in html

    def test_tells_a_non_subscriber_to_do_nothing(self):
        html = render_confirm_html(self._sub()).lower()
        assert "didn't sign up" in html or "didn&#39;t sign up" in html

    def test_restates_the_scope_being_confirmed(self):
        # An informed click, not a reflexive one — and it doubles as a check that the wrong scope is
        # visible before it starts generating email.
        html = render_confirm_html(self._sub())
        assert "Extended Producer Responsibility" in html   # the topic they picked
        assert "Packaging" in html                          # and the material

    def test_carries_no_unsubscribe_or_referral_ask(self):
        html = render_confirm_html(self._sub())
        assert "/subscriptions/unsubscribe" not in html

    @pytest.mark.asyncio
    async def test_sends_even_when_the_marketing_flag_is_off(self, monkeypatch):
        # enable_welcome_email gates the marketing roundup. If it gated this too, turning the flag off
        # would leave every new sign-up permanently stuck unconfirmed with no way out.
        _email_on(monkeypatch, settings)
        monkeypatch.setattr(settings, "enable_welcome_email", False)
        sends: list = []

        class _Sender:
            async def send_html(self, to, subject, html, **kw):
                sends.append(to)
                return True

        monkeypatch.setattr("app.alerts.email_sender.EmailSender", lambda: _Sender())
        assert await send_confirmation_email(self._sub()) is True
        assert sends == ["a@example.com"]

    @pytest.mark.asyncio
    async def test_does_not_send_without_a_configured_provider(self, monkeypatch):
        _email_off(monkeypatch, settings)
        assert await send_confirmation_email(self._sub()) is False
