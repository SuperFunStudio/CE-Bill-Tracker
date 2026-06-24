"""One-click unsubscribe tokens for the recurring (marketing) emails.

A signed, stateless token lets a recipient unsubscribe from an emailed link without authenticating —
the token is an HMAC over the AlertSubscription id, so it can't be forged or enumerated to unsubscribe
someone else. The endpoint that consumes it is GET/POST /subscriptions/unsubscribe (app/api/alerts.py),
wired for RFC 8058 one-click via the List-Unsubscribe-Post header.

The HMAC key is `unsubscribe_secret`, falling back to `stripe_webhook_secret` (always set in prod) so
links work without provisioning a new secret. Rotating that secret invalidates outstanding links —
acceptable, since the worst case is a stale link 404-ing rather than any data exposure.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

from app.config import settings


def _secret() -> bytes:
    key = settings.unsubscribe_secret or settings.stripe_webhook_secret or "signalscout-dev-unsub"
    return key.encode("utf-8")


def _sign(payload: str) -> str:
    mac = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


def make_token(sub_id: int) -> str:
    payload = str(sub_id)
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str | None) -> int | None:
    """Return the subscription id if the token is well-formed and the signature matches, else None."""
    if not token or "." not in token:
        return None
    payload, _, sig = token.rpartition(".")
    if not payload or not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        return int(payload)
    except ValueError:
        return None


def unsubscribe_url(sub_id: int) -> str:
    base = settings.api_base_url.rstrip("/")
    return f"{base}/subscriptions/unsubscribe?token={make_token(sub_id)}"
