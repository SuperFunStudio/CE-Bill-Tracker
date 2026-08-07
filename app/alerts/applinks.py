"""Deep links from emails back into the web app.

Every email that lists a bill or a state should land the reader inside the dashboard, not on a bare
external legislature page (which also reads as a low-reputation link to spam filters). Bills open via
the ?bill={id} query param the bills page reads to auto-open the detail panel; states have their own
profile route. Centralised here so the URL scheme lives in one place across all the alert templates.
"""
from __future__ import annotations

# The deployed dashboard origin (Atlas Circular). Mirrors _DASHBOARD_URL in digest.py; kept here so
# non-digest emails can build links without importing the digest module. battleofbills.com 301-redirects
# here, so old links in already-sent emails keep resolving.
DASHBOARD_URL = "https://www.atlascircular.com"


def with_utm(url: str, campaign: str, medium: str = "email") -> str:
    """Tag an outbound link so GA4 can attribute the session back to the message that sent it.

    We can't use SendGrid's click tracking for this — its branded click host has a broken certificate,
    so link rewriting is disabled (see docs/EMAIL_DELIVERABILITY.md). UTM params do the same job
    without an intermediary: the frontend's captureAttribution() reads utm_* on landing and GA4
    credits the campaign, so "how many people opened the litigation alert and actually read the case"
    becomes answerable.

    `medium` distinguishes channels for links that go out on more than one (an alert block shared
    between email and Slack).
    """
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source=atlas_alert&utm_medium={medium}&utm_campaign={campaign}"


def bill_url(bill_id: int) -> str:
    """Deep link that opens a bill's detail panel on the bills page (see ?bill handling in app/page)."""
    return f"{DASHBOARD_URL}/?bill={bill_id}"


def subscribe_url(campaign: str = "forwarded", medium: str = "email") -> str:
    """Where a forwarded-to colleague goes to start their own alerts. Tagged separately from the
    body links so the "someone forwarded this" loop is measurable on its own."""
    return with_utm(f"{DASHBOARD_URL}/", campaign, medium)


def litigation_case_url(case_id: int, medium: str = "email") -> str:
    """Deep link that opens one litigation case on the Federal Actions page (see the ?case handling
    in app/federal/page).

    Litigation alerts point here rather than straight at CourtListener: the reader lands on our
    analysis — preemption risk, the linked bill, the docket timeline — and the outbound CourtListener
    link lives on that page for anyone who wants the primary source. Same "in-app first, source
    second" rule the bill emails follow, and it keeps a cold external domain out of the email body.
    """
    return with_utm(f"{DASHBOARD_URL}/federal?case={case_id}", "litigation_alert", medium)


def state_url(state: str | None) -> str | None:
    """Profile route for a 2-letter state code, or None if there's no usable code to link."""
    code = (state or "").strip().lower()
    if len(code) != 2 or not code.isalpha():
        return None
    return f"{DASHBOARD_URL}/states/{code}/"
