"""Per-request access logging.

The app previously emitted no request-level trail of its own — an attacker enumerating endpoints,
fuzzing paths, or eating 429s was visible only in Cloud Run's raw httpRequest logs, with nothing
queryable by field in our own logs. This middleware logs exactly one structured line per request and
binds a request id + resolved client IP into structlog's contextvars, so any event a handler emits
during the request (auth failures, webhook signature failures, …) is correlated to the same request.

Client IP is resolved with the same spoof-resistant logic the rate limiter uses (read X-Forwarded-For
from the right), so the logged IP is the one an alert should key on. 429s and 5xx are logged at WARNING
so log-based alert policies can filter on severity=WARNING for the abuse/error signal.
"""
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.ratelimit import _client_ip

log = structlog.get_logger()

# Query strings can carry referral/unlock tokens; cap the logged length so a probing payload is still
# visible (SQLi/XSS attempts live here) without dumping unbounded caller-controlled data into logs.
_MAX_QUERY_LEN = 200


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:16]
        client_ip = _client_ip(request)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, client_ip=client_ip)

        start = time.perf_counter()
        status = 500
        try:
            response: Response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            query = request.url.query[:_MAX_QUERY_LEN]
            # WARNING for rate-limit hits and server errors — the two signals worth alerting on;
            # everything else stays INFO to keep the access log high-signal.
            level = "warning" if (status == 429 or status >= 500) else "info"
            getattr(log, level)(
                "http_request",
                method=request.method,
                path=request.url.path,
                query=query,
                status=status,
                client_ip=client_ip,
                user_agent=request.headers.get("user-agent", ""),
                referer=request.headers.get("referer", ""),
                duration_ms=duration_ms,
                request_id=request_id,
            )
            structlog.contextvars.clear_contextvars()
