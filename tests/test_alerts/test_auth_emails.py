"""Account-security emails: rendering + the fail-soft send contract.

The behaviour worth pinning is the fallback semantics, not the copy: `send_*` must return False —
never raise — whenever we can't deliver, because the frontend reads False as "fall back to the
Firebase SDK's own mailer". A send path that raised (or that swallowed a failure and returned True)
would leave a new user with no verification email at all.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.alerts import auth_emails
from app.alerts.auth_emails import (
    render_reset_html,
    render_reset_subject,
    render_verify_html,
    render_verify_subject,
    send_verification_email,
)

LINK = "https://ce-bill-tracker.firebaseapp.com/__/auth/action?mode=verifyEmail&oobCode=abc123"


class TestRendering:
    @pytest.mark.parametrize("render", [render_verify_html, render_reset_html])
    def test_carries_the_action_link_twice(self, render):
        """Once in the CTA button, once as a pasteable URL for clients that strip buttons."""
        html = render(LINK)
        assert html.count(f'href="{LINK}"') == 2   # button + fallback anchor
        assert f">{LINK}</a>" in html              # ...and the fallback shows the URL as text

    @pytest.mark.parametrize("render", [render_verify_html, render_reset_html])
    def test_wears_the_shared_masthead(self, render):
        html = render(LINK)
        assert "Atlas Circular" in html
        # The studio byline was removed from the masthead across every template — it spent the
        # reader's first glance (and the inbox preview snippet) on the publisher, not the message.
        # It survives once in the footer identity block; what matters is that it's below the fold.
        assert html.upper().index("SUPERFUN") > html.upper().index("</H1>")

    @pytest.mark.parametrize("render", [render_verify_html, render_reset_html])
    def test_leads_with_inbox_preview_text(self, render):
        html = render(LINK)
        assert "display:none" in html
        assert html.index("display:none") < html.index("Atlas Circular")

    def test_subjects_name_the_brand_and_the_action(self):
        # These land in an inbox next to a dozen other verification mails — the brand has to be in
        # the subject line, not only the body.
        assert "Atlas Circular" in render_verify_subject()
        assert "Atlas Circular" in render_reset_subject()
        assert "password" in render_reset_subject().lower()

    def test_reset_reassures_the_unintended_recipient(self):
        # A reset email to someone who didn't ask for one must say so — otherwise it reads as a
        # breach notice.
        assert "didn't request this" in render_reset_html(LINK)


class TestSendIsFailSoft:
    @pytest.mark.asyncio
    async def test_returns_false_when_flag_off(self, monkeypatch):
        monkeypatch.setattr(auth_emails.settings, "enable_auth_emails", False)
        assert await send_verification_email("a@example.com") is False

    @pytest.mark.asyncio
    async def test_returns_false_without_sendgrid_key(self, monkeypatch):
        monkeypatch.setattr(auth_emails.settings, "enable_auth_emails", True)
        monkeypatch.setattr(auth_emails.settings, "sendgrid_api_key", "")
        assert await send_verification_email("a@example.com") is False

    @pytest.mark.asyncio
    async def test_returns_false_when_firebase_wont_mint_a_link(self, monkeypatch):
        """Unknown address / Identity Toolkit error — caller falls back, and we never raise."""
        monkeypatch.setattr(auth_emails.settings, "enable_auth_emails", True)
        monkeypatch.setattr(auth_emails.settings, "sendgrid_api_key", "SG.test")
        with patch.object(auth_emails, "_generate_link", AsyncMock(return_value=None)):
            assert await send_verification_email("nobody@example.com") is False

    @pytest.mark.asyncio
    async def test_swallows_an_unexpected_error(self, monkeypatch):
        monkeypatch.setattr(auth_emails.settings, "enable_auth_emails", True)
        monkeypatch.setattr(auth_emails.settings, "sendgrid_api_key", "SG.test")
        with patch.object(auth_emails, "_generate_link", AsyncMock(side_effect=RuntimeError("boom"))):
            assert await send_verification_email("a@example.com") is False

    @pytest.mark.asyncio
    async def test_true_only_when_sendgrid_accepted_it(self, monkeypatch):
        monkeypatch.setattr(auth_emails.settings, "enable_auth_emails", True)
        monkeypatch.setattr(auth_emails.settings, "sendgrid_api_key", "SG.test")
        sender = MagicMock()  # the class; calling it yields the instance
        sender.return_value.send_html = AsyncMock(return_value=True)
        with patch.object(auth_emails, "_generate_link", AsyncMock(return_value=LINK)), \
             patch("app.alerts.sendgrid_sender.SendGridSender", sender):
            assert await send_verification_email("a@example.com") is True
        to, subject, html = sender.return_value.send_html.await_args.args
        assert to == "a@example.com"
        assert subject == render_verify_subject()
        assert LINK in html
