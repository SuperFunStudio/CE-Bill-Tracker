"""Per-IP rate limiting (slowapi).

The API is public (Cloud Run --allow-unauthenticated), so every endpoint — including the ones that
send email, create Stripe objects, or trigger LLM/external calls — is reachable by anyone. This adds a
blanket per-IP ceiling plus tighter limits on the abuse-prone POSTs. See docs/SECURITY_ASSESSMENT.md H-1.

Storage is in-memory (per Cloud Run instance). With min-instances=1/max-3 that's an approximate global
limit, not exact — good enough as a first defense; move to a shared Redis backend if precise global
limits are ever needed.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _client_ip(request: Request) -> str:
    """Real client IP. Behind Cloud Run the socket peer is a Google front-end, so prefer the first
    hop in X-Forwarded-For (the originating client) when present."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


# Blanket default applies to every route; specific routes tighten it with @limiter.limit(...).
limiter = Limiter(key_func=_client_ip, default_limits=["240/minute"])
