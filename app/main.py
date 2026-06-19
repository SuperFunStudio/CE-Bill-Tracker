from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import access, admin, bills, alerts, pipeline, health, federal, companies, webhooks, billing, design, user, compliance, referrals, insights
from app.api.federal import litigation_router
from app.ratelimit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler
    from app.scheduler.jobs import setup_scheduler
    scheduler = setup_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="SignalScout — Compliance Scout API",
    description="Monitor US state-level EPR legislation and regulatory instruments",
    version="0.1.0",
    lifespan=lifespan,
)

ALLOWED_ORIGINS = [
    "https://ce-bill-tracker.web.app",
    "https://ce-bill-tracker.firebaseapp.com",
    "https://battleofbills.com",
    "https://www.battleofbills.com",
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
app.include_router(admin.router)
app.include_router(compliance.router)
app.include_router(insights.router)
