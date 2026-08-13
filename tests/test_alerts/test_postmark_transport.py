"""The Postmark transport contract.

Postmark answers 200 for a *rejected* message too — the verdict lives in the body's ErrorCode, not
the status line. Reading only the status code is how a migration silently reports every suppressed
recipient and every unverified From-address as a successful send.
"""
import asyncio
import types

import pytest

from app.alerts import email_sender
from app.config import settings


def _run(payload, response, monkeypatch):
    """Drive _post against a canned Postmark response."""
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
    ok = asyncio.run(email_sender._post(payload, "test_send"))
    return ok, sent


def _response(status, body):
    return types.SimpleNamespace(
        status_code=status, json=lambda: body, text=str(body)
    )


@pytest.fixture
def payload():
    return email_sender._build_payload("a@example.com", "s", "<p>t</p>", "t")


class TestPost:
    def test_accepted_only_on_error_code_zero(self, payload, monkeypatch):
        ok, _ = _run(payload, _response(200, {"ErrorCode": 0, "MessageID": "abc"}), monkeypatch)
        assert ok is True

    def test_suppressed_recipient_is_a_failure_not_a_send(self, payload, monkeypatch):
        """ErrorCode 406 = the address is on the server's suppression list (hard bounce / spam
        complaint). Postmark still answers 200; treating that as delivered would hide churn."""
        ok, _ = _run(
            payload, _response(200, {"ErrorCode": 406, "Message": "Inactive recipient"}), monkeypatch
        )
        assert ok is False

    def test_unverified_sender_is_a_failure(self, payload, monkeypatch):
        ok, _ = _run(
            payload,
            _response(422, {"ErrorCode": 300, "Message": "Invalid 'From' address"}),
            monkeypatch,
        )
        assert ok is False

    def test_network_error_never_escapes(self, payload, monkeypatch):
        """A send failing must not take down the cycle that triggered it."""

        class _Exploding:
            async def __aenter__(self):
                raise RuntimeError("dns down")

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda **kw: _Exploding())
        assert asyncio.run(email_sender._post(payload, "test_send")) is False

    def test_authenticates_with_the_server_token(self, payload, monkeypatch):
        monkeypatch.setattr(settings, "postmark_api_key", "pm-test-token")
        _, sent = _run(payload, _response(200, {"ErrorCode": 0}), monkeypatch)
        assert sent["headers"]["X-Postmark-Server-Token"] == "pm-test-token"
        assert sent["url"] == email_sender.POSTMARK_ENDPOINT
