"""Security response headers.

The API previously set no security headers (the pre-launch sweep flagged the gap). This adds the safe,
broadly-applicable set to every response. Deliberately conservative on CSP: the app serves Swagger UI
at /docs (inline scripts + CDN assets), so a resource-restricting `default-src` policy would break it.
We instead use `frame-ancestors 'none'` — clickjacking protection that doesn't restrict resource loads —
which pairs with X-Frame-Options for older browsers. A full resource CSP belongs on the HTML frontend
(firebase.json), tested against the GA/Stripe/Firebase origins it actually loads.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_HEADERS = {
    # Don't let browsers MIME-sniff a response into an unexpected content type.
    "X-Content-Type-Options": "nosniff",
    # This JSON API is never meant to be framed — block clickjacking (legacy header + CSP directive).
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    # Force HTTPS for two years incl. subdomains. Cloud Run is HTTPS-only, so this is safe.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    # Don't leak full URLs (with query strings) to cross-origin destinations.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # No browser feature the API needs; deny the high-risk ones outright.
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in _HEADERS.items():
            response.headers.setdefault(key, value)
        return response
