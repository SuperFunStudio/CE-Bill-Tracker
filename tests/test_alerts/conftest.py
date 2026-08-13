"""Shared helpers for the alert/email tests.

Turning the email channel on or off in a test used to mean setting one provider's API key, which
quietly stopped working the moment there were two providers: with EMAIL_PROVIDER on SendGrid,
clearing POSTMARK_API_KEY leaves the channel fully configured, so an "email is off" test asserts
nothing. These pin the provider AND its key together, so the switch can move without the suite
silently testing the wrong branch.
"""


def _email_on(monkeypatch, settings, provider: str = "sendgrid") -> None:
    """Configure the email channel — `settings.email_configured` becomes True."""
    monkeypatch.setattr(settings, "email_provider", provider)
    key = "postmark_api_key" if provider == "postmark" else "sendgrid_api_key"
    monkeypatch.setattr(settings, key, "test-email-key")


def _email_off(monkeypatch, settings, provider: str = "sendgrid") -> None:
    """Take the email channel away — no credential for the ACTIVE provider."""
    monkeypatch.setattr(settings, "email_provider", provider)
    key = "postmark_api_key" if provider == "postmark" else "sendgrid_api_key"
    monkeypatch.setattr(settings, key, "")
