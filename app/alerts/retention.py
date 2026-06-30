"""Alert-retention policy — how long a subscription keeps receiving email alerts.

The product promise (surfaced in the watch-list onboarding email): the dashboard *features* lock the
moment a Pro trial ends, but the alert *emails* a user subscribed to keep flowing for a full year
after they subscribed. After that retention window a non-Pro account's alerts lapse.

This is the single source of truth for that rule, applied at every send path (the real-time
dispatcher plus the digest / deadline / new-bill cron cycles) by filtering the active-subscription
list before matching:

  - Anonymous "filter" subscriptions (no firebase_uid — the public newsletter signup) are unchanged:
    they have no Pro/trial concept, so they're always retained.
  - Account-owned subscriptions (firebase_uid set) are retained while the account is a live Pro seat,
    or within ALERT_RETENTION_DAYS of the subscription's created_at, whichever lasts longer.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertSubscription, Entitlement

# How long a lapsed-trial account keeps its subscribed alert emails after subscribing.
ALERT_RETENTION_DAYS = 365


def alerts_retained(
    sub: AlertSubscription, ent: Entitlement | None, now: datetime | None = None
) -> bool:
    """Whether this subscription should still receive alert emails. See module docstring."""
    # Lazy import avoids any import-time cycle between app.alerts and app.api.auth.
    from app.api.auth import is_pro

    if not sub.firebase_uid:
        return True  # anonymous public subscription — no Pro/trial concept, always on
    if is_pro(ent):
        return True
    now = now or datetime.now(timezone.utc)
    return bool(
        sub.created_at and sub.created_at + timedelta(days=ALERT_RETENTION_DAYS) >= now
    )


async def _entitlements_by_email(
    db: AsyncSession, emails: set[str]
) -> dict[str, Entitlement]:
    lowered = {e.lower() for e in emails if e}
    if not lowered:
        return {}
    res = await db.execute(
        select(Entitlement).where(func.lower(Entitlement.email).in_(lowered))
    )
    return {e.email.lower(): e for e in res.scalars().all()}


async def filter_retained_subscriptions(
    db: AsyncSession,
    subs: list[AlertSubscription],
    now: datetime | None = None,
) -> list[AlertSubscription]:
    """Drop account-owned subscriptions whose alert retention has lapsed (non-Pro, > 1 year old).

    Anonymous subscriptions pass through untouched. Loads each account-owned subscriber's entitlement
    once (by email) so the Pro check is a single query regardless of subscriber count."""
    owned_emails = {s.email for s in subs if s.firebase_uid and s.email}
    ents = await _entitlements_by_email(db, owned_emails)
    return [
        sub
        for sub in subs
        if alerts_retained(sub, ents.get((sub.email or "").lower()), now)
    ]
