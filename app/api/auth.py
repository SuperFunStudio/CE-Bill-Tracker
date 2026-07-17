"""Firebase ID-token verification for premium routes.

The dashboard signs users in with Firebase Auth (email/password + Google) and sends the resulting
ID token as `Authorization: Bearer <token>`. We verify it with firebase-admin (project-scoped, via
the Cloud Run service account's ADC) and resolve the caller's entitlement. Identity is keyed on the
verified email, the same key the billing webhook writes. See gating-and-monetization-plan.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Entitlement

log = structlog.get_logger()

_initialized = False


def _ensure_firebase() -> None:
    """Initialize the firebase-admin app once. Token verification only needs the project id plus
    Google's public certs (fetched over HTTPS), so this works with ADC on Cloud Run and without
    any credentials locally."""
    global _initialized
    if _initialized:
        return
    import firebase_admin
    from firebase_admin import credentials

    if not firebase_admin._apps:
        try:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})
        except Exception as e:
            # ADC unavailable (e.g. local dev) — fall back to a project-id-only app. Token verification
            # still validates Google's signature, so this is safe, but log it loudly (L-2): if it fires
            # in prod it signals a credentials misconfiguration worth investigating.
            log.warning("firebase_adc_unavailable_fallback", error=str(e))
            firebase_admin.initialize_app(options={"projectId": settings.firebase_project_id})
    _initialized = True


class AuthedUser:
    def __init__(self, uid: str, email: str, email_verified: bool = False):
        self.uid = uid
        self.email = email
        # Whether Firebase considers the email verified. Google sign-ins are always True; email/password
        # signups are False until the user clicks the verification link. Gates complimentary Pro grants
        # (H-2) so a script can't farm free seats from throwaway, unverified accounts.
        self.email_verified = email_verified


async def get_current_user(authorization: str | None = Header(default=None)) -> AuthedUser:
    """Verify the Bearer Firebase ID token; 401 on missing/invalid. Returns uid + verified email."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    _ensure_firebase()
    from firebase_admin import auth as fb_auth

    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception as e:
        log.info("firebase_token_invalid", error=str(e))
        raise HTTPException(status_code=401, detail="invalid or expired token")
    email = (decoded.get("email") or "").lower().strip()
    uid = decoded.get("uid") or decoded.get("user_id") or ""
    if not email or not uid:
        raise HTTPException(status_code=401, detail="token missing email/uid")
    return AuthedUser(uid=uid, email=email, email_verified=bool(decoded.get("email_verified")))


async def get_entitlement(db: AsyncSession, user: AuthedUser) -> Entitlement | None:
    res = await db.execute(select(Entitlement).where(Entitlement.email == user.email))
    return res.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Membership capability model (Atlas Circular)
#
# We moved from a single free/Pro boolean to a per-feature capability model over five plans. Gating
# asks "does this plan carry capability X" instead of "is this Pro", so tiers between free and Pro
# (Student, Research) can each unlock a coherent slice. `is_pro`/`require_pro` are kept as thin shims
# (Pro == "has the deadlines capability") so every existing Pro-only route works unchanged.
# ---------------------------------------------------------------------------
CAP_EXPLORE = "explore"                 # Bill Explorer + jurisdiction data
CAP_ASK = "ask"                         # Ask the Atlas (research Q&A)
CAP_DESIGN_GUIDE = "design_guide"       # full Design Guide
CAP_INSIGHTS_IMPACT = "insights_impact" # Real-World Impact table + Bills-over-time chart
CAP_DEADLINES = "deadlines"             # Upcoming Deadlines calendar
CAP_ALERTS = "alerts"                   # watchlist / new-bill + deadline alerts
CAP_STUDIO = "studio"                   # Packaging Studio
CAP_FEDERAL = "federal"                 # Federal Actions (also US-region gated at the route)

_CAPS_STUDENT = {CAP_EXPLORE, CAP_ASK, CAP_DESIGN_GUIDE}
_CAPS_RESEARCH = _CAPS_STUDENT | {CAP_INSIGHTS_IMPACT}
_CAPS_PRO = _CAPS_RESEARCH | {CAP_DEADLINES, CAP_ALERTS, CAP_STUDIO, CAP_FEDERAL}

# plan → the capabilities it carries. Enterprise mirrors Pro on features (its extras are seats/support,
# handled operationally, not by a feature flag).
PLAN_CAPS: dict[str, frozenset[str]] = {
    "free": frozenset({CAP_EXPLORE}),
    "student": frozenset(_CAPS_STUDENT),
    "research": frozenset(_CAPS_RESEARCH),
    "pro": frozenset(_CAPS_PRO),
    "enterprise": frozenset(_CAPS_PRO),
}

_PAID_PLANS = ("student", "research", "pro", "enterprise")


def resolve_plan(ent: Entitlement | None) -> str:
    """The plan actually in effect right now — collapses to "free" when a paid plan isn't live.

    A paid plan counts only while its subscription is in good standing (active or trialing). A
    complimentary grant (ent.comp) has no Stripe webhook to flip it off, so its expiry is enforced here:
    a comp seat past current_period_end resolves to free (NULL period_end on a comp seat = indefinite).
    Mirrors the old is_pro standing check, generalized across the tiers.
    """
    if not ent:
        return "free"
    plan = ent.plan or "free"
    if plan not in _PAID_PLANS:
        return "free"
    if ent.status not in ("active", "trialing"):
        return "free"
    if ent.comp and ent.current_period_end and ent.current_period_end < datetime.now(timezone.utc):
        return "free"
    return plan


def _has_active_preview(ent: Entitlement | None) -> bool:
    """A temporary Pro preview (Student/Research perk) that's still within its window."""
    return bool(
        ent
        and getattr(ent, "preview_until", None)
        and ent.preview_until > datetime.now(timezone.utc)
    )


def effective_capabilities(ent: Entitlement | None) -> set[str]:
    """Every capability this entitlement carries: its resolved plan's set, unioned with the Pro set
    while a temporary Pro preview is active (the preview lets a Student/Research member try Pro features
    without changing their underlying plan)."""
    caps = set(PLAN_CAPS.get(resolve_plan(ent), PLAN_CAPS["free"]))
    if _has_active_preview(ent):
        caps |= PLAN_CAPS["pro"]
    return caps


def has_capability(ent: Entitlement | None, capability: str) -> bool:
    return capability in effective_capabilities(ent)


def is_pro(ent: Entitlement | None) -> bool:
    """Pro-level access: the seat carries the full Pro feature set (Pro, Enterprise, or an active
    temporary Pro preview). Kept as a shim over the capability model so the many existing `is_pro` /
    `require_pro` call sites keep working. "trialing" still counts (founding 90-day Stripe trial)."""
    return CAP_DEADLINES in effective_capabilities(ent)


# Educational email suffixes that qualify for the Student tier are configured in settings so the list
# can grow without a code change; see settings.edu_email_suffixes.
def is_edu_email(email: str | None) -> bool:
    """Does this address look like a student/faculty educational account (.edu, .ac.uk, …)?"""
    e = (email or "").lower().strip()
    return bool(e) and any(e.endswith(suffix) for suffix in settings.edu_email_suffixes)


# Hard ceiling on how far out a stacked complimentary grant can reach. Bounds the payoff of referral
# farming (each referral is +30d, stackable) regardless of how many fake-but-verified accounts a
# sharer musters — a comp seat can never extend more than this far from "now". See H-2.
MAX_COMP_DAYS = 180


def grant_comp_days(ent: Entitlement, days: int) -> None:
    """Give an entitlement `days` of complimentary (no-card) Pro, stacking on an existing comp grant.
    A real paid subscription is left untouched — it doesn't need it. Used by the signup trial (7d) and
    the referral reward (30d); is_pro() enforces the expiry since there's no Stripe webhook behind it.
    Stacking is capped at MAX_COMP_DAYS from now so the comp window can't be farmed indefinitely.
    """
    now = datetime.now(timezone.utc)
    # A real paid seat on ANY tier (student/research/pro/enterprise) is left untouched — converting it to
    # a comp Pro grant would clobber the underlying plan and, on comp expiry, silently drop a paying
    # member to free. Only a non-paid (free) or already-comp seat receives/stacks the grant.
    if not ent.comp and resolve_plan(ent) in _PAID_PLANS:
        return
    base = (
        ent.current_period_end
        if (ent.comp and ent.current_period_end and ent.current_period_end > now)
        else now
    )
    ent.plan = "pro"
    ent.status = "active"
    ent.comp = True
    ent.current_period_end = min(base + timedelta(days=days), now + timedelta(days=MAX_COMP_DAYS))


def grant_pro_preview(ent: Entitlement, days: int) -> None:
    """Give a member a temporary Pro *preview* — Pro capabilities for `days`, WITHOUT changing their
    plan (a Student stays a Student). Distinct from grant_comp_days, which converts the seat to a comp
    Pro plan. Stacks on an existing preview and is capped at MAX_COMP_DAYS from now (same anti-farming
    ceiling). effective_capabilities() unions the Pro set while preview_until is in the future.
    """
    now = datetime.now(timezone.utc)
    base = (
        ent.preview_until
        if (ent.preview_until and ent.preview_until > now)
        else now
    )
    ent.preview_until = min(base + timedelta(days=days), now + timedelta(days=MAX_COMP_DAYS))


async def require_pro(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthedUser:
    """Guard for Pro-only routes — 401 if unauthenticated, 403 if authenticated but not Pro."""
    ent = await get_entitlement(db, user)
    if not is_pro(ent):
        raise HTTPException(status_code=403, detail="pro subscription required")
    return user


async def get_optional_pro(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> bool:
    """Best-effort Pro check for teaser/full endpoints. NEVER raises — returns False for an
    anonymous, malformed-token, expired-token, or non-Pro caller, and True only for a verified
    live Pro seat (or an admin). Lets one endpoint serve full data to Pro and a teaser to everyone
    else without 401-ing public traffic."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return False
    try:
        user = await get_current_user(authorization)
    except HTTPException:
        return False
    if is_admin(user):
        return True
    ent = await get_entitlement(db, user)
    return is_pro(ent)


def require_capability(capability: str):
    """Build a FastAPI dependency that guards a route on a single capability — 401 if unauthenticated,
    403 if the caller's plan doesn't carry it. Admins pass everything. Usage:

        _user: AuthedUser = Depends(require_capability(CAP_FEDERAL))
    """

    async def _dep(
        user: AuthedUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> AuthedUser:
        if is_admin(user):
            return user
        ent = await get_entitlement(db, user)
        if not has_capability(ent, capability):
            raise HTTPException(status_code=403, detail=f"{capability} access required")
        return user

    return _dep


def get_optional_capability(capability: str):
    """Build a non-raising best-effort capability check for teaser/full endpoints (mirrors
    get_optional_pro). Returns True only for an admin or a caller whose plan carries `capability`;
    False for anonymous, malformed/expired-token, or under-tier callers — never raises."""

    async def _dep(
        authorization: str | None = Header(default=None),
        db: AsyncSession = Depends(get_db),
    ) -> bool:
        if not authorization or not authorization.lower().startswith("bearer "):
            return False
        try:
            user = await get_current_user(authorization)
        except HTTPException:
            return False
        if is_admin(user):
            return True
        ent = await get_entitlement(db, user)
        return has_capability(ent, capability)

    return _dep


def is_admin(user: AuthedUser) -> bool:
    """Is this caller an allowlisted admin? Requires a VERIFIED email (M-2/M-1): admin is resolved by
    email, so without the verified check anyone who got a Firebase account asserting an admin address
    (where the project allows it) would inherit the console. Admins sign in with Google (verified) or
    must verify their address."""
    if not user.email_verified:
        return False
    allow = {e.lower().strip() for e in settings.admin_emails}
    return bool(user.email) and user.email.lower().strip() in allow


async def require_admin(
    user: AuthedUser = Depends(get_current_user),
) -> AuthedUser:
    """Guard for the hidden /admin console — 401 if unauthenticated, 403 if not an admin."""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="admin access required")
    return user
