"""Deep links from emails back into the web app.

Every email that lists a bill or a state should land the reader inside the dashboard, not on a bare
external legislature page (which also reads as a low-reputation link to spam filters). Bills open via
the ?bill={id} query param the bills page reads to auto-open the detail panel; states have their own
profile route. Centralised here so the URL scheme lives in one place across all the alert templates.
"""
from __future__ import annotations

# The deployed dashboard origin. Mirrors _DASHBOARD_URL in digest.py; kept here so non-digest emails
# can build links without importing the digest module.
DASHBOARD_URL = "https://battleofbills.com"


def bill_url(bill_id: int) -> str:
    """Deep link that opens a bill's detail panel on the bills page (see ?bill handling in app/page)."""
    return f"{DASHBOARD_URL}/?bill={bill_id}"


def state_url(state: str | None) -> str | None:
    """Profile route for a 2-letter state code, or None if there's no usable code to link."""
    code = (state or "").strip().lower()
    if len(code) != 2 or not code.isalpha():
        return None
    return f"{DASHBOARD_URL}/states/{code}/"
