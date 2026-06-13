"""Per-account settings + the Pro watch list, behind Firebase-token auth.

/me/settings is free (any authenticated user) — it persists UI prefs (the saved scope) per Firebase
uid so they follow the user across devices. /me/watchlist is Pro-gated — the bills an account
follows. See app/api/auth.py + gating-and-monetization-plan.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthedUser, get_current_user, require_pro
from app.database import get_db
from app.models import UserSettings, WatchlistItem

router = APIRouter(prefix="/me", tags=["me"])


class SettingsUpdate(BaseModel):
    prefs: dict


@router.get("/settings")
async def get_settings(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(UserSettings).where(UserSettings.firebase_uid == user.uid))
    row = res.scalar_one_or_none()
    return {"prefs": row.prefs if row else {}}


@router.put("/settings")
async def put_settings(
    payload: SettingsUpdate,
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(UserSettings).where(UserSettings.firebase_uid == user.uid))
    row = res.scalar_one_or_none()
    if row is None:
        row = UserSettings(firebase_uid=user.uid, email=user.email, prefs=payload.prefs or {})
        db.add(row)
    else:
        row.prefs = payload.prefs or {}
        if not row.email:
            row.email = user.email
    await db.commit()
    return {"prefs": row.prefs}


class WatchAdd(BaseModel):
    bill_id: int


@router.get("/watchlist")
async def get_watchlist(
    user: AuthedUser = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(WatchlistItem.bill_id).where(WatchlistItem.firebase_uid == user.uid)
    )
    return {"bill_ids": [r[0] for r in res.all()]}


@router.post("/watchlist", status_code=201)
async def add_watch(
    payload: WatchAdd,
    user: AuthedUser = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    exists = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.firebase_uid == user.uid,
            WatchlistItem.bill_id == payload.bill_id,
        )
    )
    if exists.scalar_one_or_none() is None:
        db.add(WatchlistItem(firebase_uid=user.uid, bill_id=payload.bill_id))
        try:
            await db.commit()
        except IntegrityError:
            # Bad bill_id (FK) or a concurrent insert — neither should 500 the client.
            await db.rollback()
    return {"bill_id": payload.bill_id, "watched": True}


@router.delete("/watchlist/{bill_id}")
async def remove_watch(
    bill_id: int,
    user: AuthedUser = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.firebase_uid == user.uid,
            WatchlistItem.bill_id == bill_id,
        )
    )
    await db.commit()
    return {"bill_id": bill_id, "watched": False}
