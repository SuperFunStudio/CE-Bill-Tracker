"""The footer every outbound email must wear: sender identity, postal address, privacy policy.

These aren't cosmetic assertions. SendGrid's compliance review is what gates the sending account, and
it reviews *sample content* — a template that ships without an identifiable sender and a physical
mailing address puts the whole sending identity at risk, not just that one message. CAN-SPAM
§7704(a)(5) compels the address on commercial mail; we carry it on transactional mail too, because
the review looks at the account and the marginal cost is four lines of grey type.

`render_shell` is the single choke point — every template in app/alerts/ goes through it — so testing
the shell covers templates that don't exist yet. That's the point: the next email someone writes
inherits compliance instead of having to remember it.
"""
from __future__ import annotations

import pytest

from app.alerts import email_shell
from app.alerts.email_shell import PRIVACY_URL, identity_text, render_shell
from app.config import settings

ADDRESS = "1924 Example St | San Diego, CA 92110"


@pytest.fixture
def address(monkeypatch):
    """A synthetic address — the real one is env-only (BUSINESS_ADDRESS) and not in git."""
    monkeypatch.setattr(settings, "business_address", ADDRESS)
    return ADDRESS


def _render(**kwargs) -> str:
    return render_shell("<p>body</p>", colophon="why you got this", **kwargs)


class TestHtmlFooter:
    def test_carries_address_publisher_and_privacy(self, address):
        html = _render()
        assert "1924 Example St · San Diego, CA 92110" in html  # pipes become display separators
        assert email_shell.PUBLISHER_NAME in html
        assert PRIVACY_URL in html
        assert "Privacy Policy" in html

    def test_transactional_mail_carries_it_too(self, address):
        """No unsubscribe, no referral, no subscribe line — the barest possible shell still identifies
        the sender. This is the shape a password-reset email renders in."""
        html = _render(unsubscribe_url=None, subscribe_url=None, referral=False)
        assert "Unsubscribe" not in html
        assert "1924 Example St" in html and PRIVACY_URL in html

    def test_sits_below_the_masthead(self, address):
        """Publisher attribution above the wordmark is what made the inbox preview read
        'SUPERFUN STU…' — see docs/EMAIL_DELIVERABILITY.md."""
        html = _render()
        assert html.index(email_shell.PUBLISHER_NAME) > html.index("</h1>")

    def test_missing_address_degrades_instead_of_exploding(self, monkeypatch):
        """An unset env var in a fresh deploy must cost us the address line, not every outbound
        email. Fail loud in review, not at send time."""
        monkeypatch.setattr(settings, "business_address", "")
        html = _render()
        assert PRIVACY_URL in html  # the rest of the block still renders

    def test_newline_separated_address_also_works(self, monkeypatch):
        monkeypatch.setattr(settings, "business_address", "1924 Example St\nSan Diego, CA 92110")
        assert "1924 Example St · San Diego, CA 92110" in _render()


class TestPlainTextFooter:
    def test_text_twin_carries_the_same_facts(self, address):
        text = identity_text()
        assert "1924 Example St" in text
        assert PRIVACY_URL in text
        assert email_shell.PUBLISHER_URL in text

    def test_hand_written_text_parts_get_it_appended(self, address, monkeypatch):
        """The two senders that build their own text/plain part bypass html_to_text, so the identity
        has to be appended explicitly or the MIME parts diverge — itself a spam signal."""
        from app.alerts import email_sender

        captured = {}

        # _post receives the provider-NEUTRAL message, so this assertion holds whichever transport
        # is active — the footer is a CAN-SPAM obligation, not a provider detail.
        async def _fake_post(message, event):
            captured.update(message)
            return True

        monkeypatch.setattr(email_sender, "_post", _fake_post)
        import asyncio

        asyncio.run(
            email_sender.EmailSender().send_html("a@b.com", "s", "<p>hi</p>", text="hand written")
        )
        assert "hand written" in captured["text"]
        assert "1924 Example St" in captured["text"]
