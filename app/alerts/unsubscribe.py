"""Signed, stateless links into a subscription — leaving one, and joining one.

Both directions are an HMAC over the AlertSubscription id, so a link can't be forged or the id space
enumerated to act on someone else's subscription. Two purposes ride the same scheme:

  unsubscribe  GET/POST /subscriptions/unsubscribe — the recipient asking us to stop. Wired for
               RFC 8058 one-click via the List-Unsubscribe-Post header.
  confirm      GET/POST /subscriptions/confirm — the recipient proving the address is theirs before
               we send them anything else (double opt-in; see migration 049).

The purpose is INSIDE the signed payload, so the two are not interchangeable: an unsubscribe link
handed to the confirm endpoint fails signature-purpose validation and vice versa. That matters
because the tokens travel through the same inboxes and forwarding chains, and a confirm link that
doubled as an unsubscribe link (or worse, the reverse — a link in every marketing footer that could
silently re-confirm a lapsed address) would defeat the point of having either.

Unsubscribe tokens keep their original bare-id payload shape so links already sitting in delivered
mail keep working; only the newer purposes carry a prefix.

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


UNSUBSCRIBE = "unsubscribe"
CONFIRM = "confirm"


def _payload(sub_id: int, purpose: str) -> str:
    """The signed payload. `unsubscribe` is the bare id — its original shape, kept so tokens in
    already-delivered mail still verify. Every other purpose is prefixed."""
    return str(sub_id) if purpose == UNSUBSCRIBE else f"{purpose}:{sub_id}"


def make_token(sub_id: int, purpose: str = UNSUBSCRIBE) -> str:
    payload = _payload(sub_id, purpose)
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str | None, purpose: str = UNSUBSCRIBE) -> int | None:
    """Return the subscription id if the token is well-formed, correctly signed, AND was issued for
    this purpose — else None. The purpose check is not cosmetic: it is what stops a token minted for
    one endpoint from being replayed against the other."""
    if not token or "." not in token:
        return None
    payload, _, sig = token.rpartition(".")
    if not payload or not hmac.compare_digest(sig, _sign(payload)):
        return None
    # A signed payload is trusted to be ours, but not to be for the caller's purpose.
    kind, sep, raw_id = payload.partition(":")
    if sep:
        if kind != purpose:
            return None
    elif purpose != UNSUBSCRIBE:  # bare id = a legacy unsubscribe token, nothing else
        return None
    try:
        return int(raw_id if sep else payload)
    except ValueError:
        return None


def unsubscribe_url(sub_id: int) -> str:
    base = settings.api_base_url.rstrip("/")
    return f"{base}/subscriptions/unsubscribe?token={make_token(sub_id, UNSUBSCRIBE)}"


def confirm_url(sub_id: int) -> str:
    """The double opt-in link. Points at the API rather than the dashboard: the click has to reach a
    server that can write to the DB, and the static export can't."""
    base = settings.api_base_url.rstrip("/")
    return f"{base}/subscriptions/confirm?token={make_token(sub_id, CONFIRM)}"
