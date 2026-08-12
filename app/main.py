from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import access, admin, auth_email, bills, alerts, pipeline, health, federal, companies, webhooks, billing, design, user, compliance, referrals, insights, research, evaluate, scope
from app.api.federal import litigation_router
from app.ratelimit import limiter
from app.utils.logging_config import configure_logging
from app.utils.request_logging import RequestLoggingMiddleware
from app.utils.security_headers import SecurityHeadersMiddleware

# Configure structlog once, at import time, before anything logs — JSON on Cloud Run, console locally.
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler
    from app.scheduler.jobs import setup_scheduler
    scheduler = setup_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    # Internal service name (SignalScout) stays in infra identifiers; the public brand is Atlas Circular.
    title="Atlas Circular API",
    description="Track circular-economy legislation and regulatory instruments across jurisdictions",
    version="0.1.0",
    lifespan=lifespan,
)

ALLOWED_ORIGINS = [
    "https://ce-bill-tracker.web.app",
    "https://ce-bill-tracker.firebaseapp.com",
    # Atlas Circular public domain (primary going forward).
    "https://atlascircular.com",
    "https://www.atlascircular.com",
    # Legacy domain — kept through the 301-redirect window so existing links keep working.
    "https://battleofbills.com",
    "https://www.battleofbills.com",
    # Dev lane frontend (Firebase hosting site ce-bill-tracker-dev) — the dev API shares this image,
    # so the dev origin must be allow-listed or every cross-origin call from the dev site is blocked.
    "https://ce-bill-tracker-dev.web.app",
    "https://ce-bill-tracker-dev.firebaseapp.com",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Per-IP rate limiting (H-1). The blanket default lives on the limiter; abuse-prone POSTs tighten it
# with @limiter.limit(...) decorators in their routers.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security headers on every response (nosniff, frame-deny, HSTS, referrer/permissions policy).
app.add_middleware(SecurityHeadersMiddleware)

# Added last so it's the OUTERMOST middleware: it wraps SlowAPI and the exception handler, so every
# request is logged with its final status — including 429s the limiter rejects and 500s the handler
# returns. See app/utils/request_logging.py.
app.add_middleware(RequestLoggingMiddleware)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Reflect the Origin only when it's on the allowlist (M-2) — never echo an arbitrary caller's
    # Origin, even on error responses, so the CORS allowlist holds for error bodies too.
    origin = request.headers.get("origin", "")
    headers = {"Access-Control-Allow-Origin": origin} if origin in ALLOWED_ORIGINS else {}
    return JSONResponse(status_code=500, content={"detail": "Internal server error"}, headers=headers)


app.include_router(health.router)
app.include_router(bills.router)
app.include_router(alerts.router)
app.include_router(access.router)
app.include_router(pipeline.router)
app.include_router(federal.router)
app.include_router(companies.router)
app.include_router(companies.bills_exposure_router)
app.include_router(companies.queue_router)
app.include_router(webhooks.router)
app.include_router(litigation_router)
app.include_router(billing.router)
app.include_router(referrals.router)
app.include_router(design.router)
app.include_router(user.router)
app.include_router(auth_email.router)
app.include_router(admin.router)
app.include_router(compliance.router)
app.include_router(insights.router)
app.include_router(research.router)
app.include_router(evaluate.router)
app.include_router(scope.router)
