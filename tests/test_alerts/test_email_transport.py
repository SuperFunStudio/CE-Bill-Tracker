"""The email transport contract, for both providers.

Two transports are wired at once (SendGrid today, Postmark waiting on account approval), and the
switch between them is a single setting. What makes that safe is that they disagree about almost
everything on the wire — most dangerously about what SUCCESS looks like:

  - SendGrid accepts with 202 and an empty body.
  - Postmark answers 200 for a *rejected* message too; the verdict is the body's ErrorCode.

Reading a status code the other provider's way is how a cutover silently reports every suppressed
recipient and every unverified From-address as a successful send. These tests pin each provider's
verdict against the other's shape, so a future switch fails loudly in CI instead of quietly in the
inbox.
"""
import asyncio
import types

import pytest

from app.alerts import email_sender
from app.config import settings


@pytest.fixture
def message():
    """The provider-neutral message every caller builds — the seam the switch turns on."""
    return email_sender._build_message("a@example.com", "s", "<p>t</p>", "t")


def _run(message, response, monkeypatch):
    """Drive _post against a canned provider response, capturing what went on the wire."""
    sent = {}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json, headers):
            sent.update(url=url, json=json, headers=headers)
            return response

    monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda **kw: _FakeClient())
    ok = asyncio.run(email_sender._post(message, "test_send"))
    return ok, sent


def _response(status, body, text=None):
    return types.SimpleNamespace(
        status_code=status, json=lambda: body, text=text if text is not None else str(body)
    )


@pytest.fixture
def sendgrid(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "sendgrid")
    monkeypatch.setattr(settings, "sendgrid_api_key", "SG.test-key")


@pytest.fixture
def postmark(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "postmark")
    monkeypatch.setattr(settings, "postmark_api_key", "pm-test-token")


class TestSendGridTransport:
    def test_accepted_on_202(self, message, sendgrid, monkeypatch):
        """SendGrid's success is 202 with no body at all — so json() raising must not read as a
        failure."""
        ok, _ = _run(message, _response(202, None, text=""), monkeypatch)
        assert ok is True

    def test_a_200_is_not_an_accepted_send(self, message, sendgrid, monkeypatch):
        """Postmark's success code is SendGrid's not-quite. Only 202 means queued here."""
        ok, _ = _run(message, _response(200, {}), monkeypatch)
        assert ok is False

    def test_unverified_sender_is_a_failure(self, message, sendgrid, monkeypatch):
        """403 "does not match a verified Sender Identity" — the SendGrid analogue of Postmark's
        ErrorCode 300, and the reason to check domain authentication first."""
        body = {"errors": [{"message": "The from address does not match a verified Sender Identity"}]}
        ok, _ = _run(message, _response(403, body), monkeypatch)
        assert ok is False

    def test_authenticates_with_a_bearer_key(self, message, sendgrid, monkeypatch):
        _, sent = _run(message, _response(202, None, text=""), monkeypatch)
        assert sent["headers"]["Authorization"] == "Bearer SG.test-key"
        assert sent["url"] == email_sender.SENDGRID_ENDPOINT

    def test_text_part_precedes_html(self, message, sendgrid, monkeypatch):
        """Not cosmetic: SendGrid requires content parts in increasing preference and rejects the
        request outright if text/html comes first."""
        _, sent = _run(message, _response(202, None, text=""), monkeypatch)
        assert [c["type"] for c in sent["json"]["content"]] == ["text/plain", "text/html"]

    def test_from_name_is_a_separate_field_not_a_header(self, monkeypatch, sendgrid):
        """SendGrid takes {email, name}; handing it Postmark's '"Name" <addr>' header string would
        make the whole quoted string the address."""
        monkeypatch.setattr(settings, "email_from", "hello@atlascircular.com")
        monkeypatch.setattr(settings, "email_from_name", "Atlas Circular")
        payload = email_sender._TRANSPORTS["sendgrid"].render(
            email_sender._build_message("a@example.com", "s", "<p>t</p>", "t")
        )
        assert payload["from"] == {"email": "hello@atlascircular.com", "name": "Atlas Circular"}

    def test_one_click_headers_ride_along(self, sendgrid):
        payload = email_sender._TRANSPORTS["sendgrid"].render(
            email_sender._build_message(
                "a@example.com", "s", "<p>t</p>", "t",
                list_unsubscribe_url="https://x.test/u?t=1",
            )
        )
        assert payload["headers"]["List-Unsubscribe"] == "<https://x.test/u?t=1>"
        assert payload["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    def test_click_tracking_off_covers_the_text_part_too(self, monkeypatch, sendgrid):
        """Disabling only the HTML rewrite leaves the plain-text part pointing at the click host —
        which is the host whose certificate sent readers to a browser security warning."""
        monkeypatch.setattr(settings, "email_click_tracking", False)
        payload = email_sender._TRANSPORTS["sendgrid"].render(
            email_sender._build_message("a@example.com", "s", "<p>t</p>", "t")
        )
        assert payload["tracking_settings"]["click_tracking"] == {
            "enable": False,
            "enable_text": False,
        }


class TestPostmarkTransport:
    def test_accepted_only_on_error_code_zero(self, message, postmark, monkeypatch):
        ok, _ = _run(message, _response(200, {"ErrorCode": 0, "MessageID": "abc"}), monkeypatch)
        assert ok is True

    def test_suppressed_recipient_is_a_failure_not_a_send(self, message, postmark, monkeypatch):
        """ErrorCode 406 = the address is on the server's suppression list (hard bounce / spam
        complaint). Postmark still answers 200; treating that as delivered would hide churn."""
        ok, _ = _run(
            message, _response(200, {"ErrorCode": 406, "Message": "Inactive recipient"}), monkeypatch
        )
        assert ok is False

    def test_unverified_sender_is_a_failure(self, message, postmark, monkeypatch):
        ok, _ = _run(
            message,
            _response(422, {"ErrorCode": 300, "Message": "Invalid 'From' address"}),
            monkeypatch,
        )
        assert ok is False

    def test_authenticates_with_the_server_token(self, message, postmark, monkeypatch):
        _, sent = _run(message, _response(200, {"ErrorCode": 0}), monkeypatch)
        assert sent["headers"]["X-Postmark-Server-Token"] == "pm-test-token"
        assert sent["url"] == email_sender.POSTMARK_ENDPOINT


class TestTransportSelection:
    """The switch itself. One message, two wires — and nothing above _post knows which."""

    def test_the_provider_setting_picks_the_endpoint(self, message, monkeypatch):
        for provider, endpoint in (
            ("sendgrid", email_sender.SENDGRID_ENDPOINT),
            ("postmark", email_sender.POSTMARK_ENDPOINT),
        ):
            monkeypatch.setattr(settings, "email_provider", provider)
            _, sent = _run(message, _response(202, {"ErrorCode": 0}), monkeypatch)
            assert sent["url"] == endpoint

    def test_a_provider_switch_needs_no_caller_changes(self, monkeypatch):
        """_build_message is provider-free: the same dict renders for either transport. If this ever
        needs a provider argument, the seam has leaked upward into thirty call sites."""
        built = email_sender._build_message("a@example.com", "s", "<p>t</p>", "t")
        assert set(built) == {
            "to", "subject", "html", "text", "from_email", "reply_to", "list_unsubscribe_url"
        }
        for transport in email_sender._TRANSPORTS.values():
            assert transport.render(built)

    def test_network_error_never_escapes(self, message, monkeypatch):
        """A send failing must not take down the cycle that triggered it."""

        class _Exploding:
            async def __aenter__(self):
                raise RuntimeError("dns down")

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda **kw: _Exploding())
        assert asyncio.run(email_sender._post(message, "test_send")) is False


class TestSendingIdentity:
    """One mailbox, two voices — and the rule that keeps them apart survives a provider switch.

    `_from_parts` is the single source of truth; each transport only formats it (Postmark as one
    header string, SendGrid as {email, name}). "Kenny" alone — an unfamiliar first name to someone
    who signed up for Atlas Circular — is what this replaced.
    """

    @pytest.fixture(autouse=True)
    def _one_address(self, monkeypatch):
        """The shipped configuration: both voices on one mailbox."""
        monkeypatch.setattr(settings, "email_from", "hello@atlascircular.com")
        monkeypatch.setattr(settings, "email_hello_from", "hello@atlascircular.com")

    def test_automated_mail_sends_as_the_brand(self):
        assert email_sender._from_parts(None) == ("hello@atlascircular.com", "Atlas Circular")

    def test_founder_voice_sends_as_a_person_from_the_same_mailbox(self):
        """The whole point of choosing by caller intent rather than by address: one mailbox, two
        names. Keying off the address would silently hand the welcome email the brand name."""
        assert email_sender._from_parts(settings.email_hello_from) == (
            "hello@atlascircular.com",
            "Kenny at Atlas Circular",
        )

    def test_a_split_identity_still_works_if_someone_wants_one(self, monkeypatch):
        monkeypatch.setattr(settings, "email_hello_from", "kenny@atlascircular.com")
        assert email_sender._from_parts("kenny@atlascircular.com") == (
            "kenny@atlascircular.com",
            "Kenny at Atlas Circular",
        )

    def test_an_unrecognised_override_goes_out_bare(self):
        """Better no display name than one that describes a different identity."""
        assert email_sender._from_header("ops@atlascircular.com") == "ops@atlascircular.com"

    def test_a_quote_in_the_name_cannot_break_the_postmark_header(self, monkeypatch):
        """Only Postmark builds a header string, so only Postmark can have it broken by a quote."""
        monkeypatch.setattr(settings, "email_from_name", 'Atlas "AC" Circular')
        assert email_sender._from_header(None) == (
            '"Atlas \\"AC\\" Circular" <hello@atlascircular.com>'
        )

    def test_an_empty_name_falls_back_to_the_bare_address(self, monkeypatch):
        monkeypatch.setattr(settings, "email_from_name", "")
        assert email_sender._from_header(None) == "hello@atlascircular.com"
        payload = email_sender._TRANSPORTS["sendgrid"].render(
            email_sender._build_message("a@example.com", "s", "<p>t</p>", "t")
        )
        assert payload["from"] == {"email": "hello@atlascircular.com"}


class TestReplyTo:
    """Four templates end with "or reply to this email" — including the cancellation email, which
    asks for churn feedback. Without a Reply-To those replies land in a send-only mailbox."""

    def test_replies_route_to_the_monitored_mailbox_on_both_providers(self, monkeypatch):
        monkeypatch.setattr(settings, "email_reply_to", "kenny@atlascircular.com")
        message = email_sender._build_message("a@example.com", "s", "<p>t</p>", "t")
        assert email_sender._TRANSPORTS["postmark"].render(message)["ReplyTo"] == (
            "kenny@atlascircular.com"
        )
        assert email_sender._TRANSPORTS["sendgrid"].render(message)["reply_to"] == {
            "email": "kenny@atlascircular.com"
        }

    def test_reply_to_is_independent_of_who_the_mail_is_from(self, monkeypatch):
        """A founder-voice send as hello@ still routes replies to the monitored mailbox."""
        monkeypatch.setattr(settings, "email_reply_to", "kenny@atlascircular.com")
        message = email_sender._build_message(
            "a@example.com", "s", "<p>t</p>", "t", from_email=settings.email_hello_from
        )
        payload = email_sender._TRANSPORTS["postmark"].render(message)
        assert "hello@atlascircular.com" in payload["From"]
        assert payload["ReplyTo"] == "kenny@atlascircular.com"

    def test_unconfigured_sends_with_no_reply_to_header(self, monkeypatch):
        monkeypatch.setattr(settings, "email_reply_to", "")
        message = email_sender._build_message("a@example.com", "s", "<p>t</p>", "t")
        assert "ReplyTo" not in email_sender._TRANSPORTS["postmark"].render(message)
        assert "reply_to" not in email_sender._TRANSPORTS["sendgrid"].render(message)


class TestMessageStream:
    """Postmark rejects bulk traffic on a transactional stream, and mixing them means a digest
    opt-out can suppress a password-reset email. Carrying a one-click unsubscribe URL is what marks
    a send as bulk. SendGrid has no streams — the same flag only sets its unsubscribe headers, which
    is why `_build_message` records the URL rather than a resolved stream name."""

    def _render(self, **kw):
        return email_sender._TRANSPORTS["postmark"].render(
            email_sender._build_message("a@example.com", "s", "<p>t</p>", "t", **kw)
        )

    def test_transactional_by_default(self):
        assert self._render()["MessageStream"] == settings.postmark_message_stream

    def test_unsubscribable_mail_goes_out_on_the_broadcast_stream(self):
        payload = self._render(list_unsubscribe_url="https://x.test/u?t=1")
        assert payload["MessageStream"] == settings.postmark_broadcast_stream

    def test_one_click_headers_ride_along(self):
        headers = {
            h["Name"]: h["Value"]
            for h in self._render(list_unsubscribe_url="https://x.test/u?t=1")["Headers"]
        }
        assert headers["List-Unsubscribe"] == "<https://x.test/u?t=1>"
        assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


class TestProviderResolution:
    """Which provider a given environment lands on. The failure this guards is an environment
    holding exactly one working credential and sending nothing through the other provider."""

    def _settings(self, **kw):
        from app.config import Settings

        return Settings(_env_file=None, **kw)

    def test_an_explicit_choice_wins_even_with_both_keys_present(self):
        s = self._settings(
            email_provider="postmark", sendgrid_api_key="SG.x", postmark_api_key="pm-x"
        )
        assert s.email_provider == "postmark"
        assert s.email_api_key == "pm-x"

    def test_falls_to_whichever_key_exists(self):
        assert self._settings(postmark_api_key="pm-x").email_provider == "postmark"
        assert self._settings(sendgrid_api_key="SG.x").email_provider == "sendgrid"

    def test_sendgrid_breaks_the_tie(self):
        """Both keys, no explicit choice: SendGrid, the approved account."""
        s = self._settings(sendgrid_api_key="SG.x", postmark_api_key="pm-x")
        assert s.email_provider == "sendgrid"

    def test_no_key_means_the_channel_is_off_not_a_wall_of_401s(self):
        s = self._settings()
        assert s.email_configured is False

    def test_the_active_key_is_the_gate(self):
        """Postmark's key must not make a SendGrid deployment look configured."""
        s = self._settings(email_provider="sendgrid", postmark_api_key="pm-x")
        assert s.email_configured is False

    def test_an_unknown_provider_fails_at_boot(self):
        with pytest.raises(ValueError):
            self._settings(email_provider="mailgun")
