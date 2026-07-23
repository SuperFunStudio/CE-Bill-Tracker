"""Per-IP rate limiting (slowapi).

The API is public (Cloud Run --allow-unauthenticated), so every endpoint — including the ones that
send email, create Stripe objects, or trigger LLM/external calls — is reachable by anyone. This adds a
blanket per-IP ceiling plus tighter limits on the abuse-prone POSTs. See docs/SECURITY_ASSESSMENT.md H-1.

Storage is in-memory (per Cloud Run instance). With min-instances=1/max-3 that's an approximate global
limit, not exact — good enough as a first defense; move to a shared Redis backend if precise global
limits are ever needed.
"""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

# How many rightmost X-Forwarded-For hops were added by trusted infrastructure (Google's front-end).
# 1 = direct Cloud Run ingress (default); set TRUSTED_PROXY_HOPS=2 via env if a Cloud Load Balancer
# is placed in front of the service, so the client IP is still read from the correct position.
TRUSTED_PROXY_HOPS = max(1, int(os.getenv("TRUSTED_PROXY_HOPS", "1")))


def _client_ip(request: Request) -> str:
    """Real client IP, resolved so it can't be spoofed by the caller.

    On Cloud Run the socket peer is a Google front-end, and the front-end *appends* the true client
    IP to the RIGHT of X-Forwarded-For, preserving any value the client itself sent. So the leftmost
    hop is attacker-controlled (a client can inject `X-Forwarded-For: 1.2.3.4` and it lands first),
    while the rightmost `TRUSTED_PROXY_HOPS` entries are the ones Google added and can be trusted.
    Read from the right, not the left — otherwise every per-IP limit (and the anonymous free-ask cap
    that keys on this) is bypassable by rotating a header. See docs/SECURITY_ASSESSMENT.md H-1 / H-new.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            # Count TRUSTED_PROXY_HOPS in from the right (the entries Google appended). Default 1 =
            # direct Cloud Run ingress (rightmost is the client). Raise to 2 if a Cloud LB is fronting.
            idx = min(TRUSTED_PROXY_HOPS, len(parts))
            return parts[-idx]
    return get_remote_address(request)


# Blanket default applies to every route; specific routes tighten it with @limiter.limit(...).
limiter = Limiter(key_func=_client_ip, default_limits=["240/minute"])
