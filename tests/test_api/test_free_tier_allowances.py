"""Pins the two free-tier allowances that replaced hard walls (2026-10-30).

  ASK — a signed-in free account gets ONE answered question (persisted like a member's, so it lands in
    My Library), then `ask_upgrade_required`. Keyed on owning no research session yet.

  WATCHLIST — a free account follows up to FREE_WATCHLIST_LIMIT bills; the next add is a 403
    `watchlist_free_limit`, which the frontend turns into a soft prompt rather than a Stripe redirect.
"""
import pytest
from fastapi import HTTPException

from app.api import research as research_mod
from app.api import user as user_mod


class _Db:
    """Async-session stand-in: `scalar` returns a fixed count; `execute` finds no existing row."""

    def __init__(self, count):
        self.count = count
        self.added = []

    async def scalar(self, _stmt):
        return self.count

    async def execute(self, _stmt):
        class _Res:
            def scalar_one_or_none(self):
                return None
        return _Res()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass


class _User:
    uid = "u1"
    email = "a@example.com"


def _free_account(monkeypatch, mod):
    async def _current_user(_auth):
        return _User()
    async def _entitlement(_db, _user):
        return None
    if hasattr(mod, "get_current_user"):
        monkeypatch.setattr(mod, "get_current_user", _current_user)
    monkeypatch.setattr(mod, "get_entitlement", _entitlement)


# --- Ask -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_free_account_first_ask_is_answered_and_persisted(monkeypatch):
    _free_account(monkeypatch, research_mod)
    monkeypatch.setattr(research_mod, "is_admin", lambda _u: False)
    monkeypatch.setattr(research_mod, "has_capability", lambda _e, _c: False)
    access = await research_mod._ask_access(authorization="Bearer t", db=_Db(count=0))
    # uid set → the turn is persisted (lands in My Library); is_member → no anonymous IP counter.
    assert access.uid == "u1" and access.is_member and not access.is_admin


@pytest.mark.asyncio
async def test_free_account_is_walled_once_its_question_is_spent(monkeypatch):
    _free_account(monkeypatch, research_mod)
    monkeypatch.setattr(research_mod, "is_admin", lambda _u: False)
    monkeypatch.setattr(research_mod, "has_capability", lambda _e, _c: False)
    with pytest.raises(HTTPException) as exc:
        await research_mod._ask_access(authorization="Bearer t", db=_Db(count=1))
    assert exc.value.status_code == 403 and exc.value.detail == "ask_upgrade_required"


# --- Watchlist -----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_free_account_can_follow_up_to_the_limit(monkeypatch):
    _free_account(monkeypatch, user_mod)
    monkeypatch.setattr(user_mod, "is_pro", lambda _e: False)
    db = _Db(count=user_mod.FREE_WATCHLIST_LIMIT - 1)
    out = await user_mod.add_watch(user_mod.WatchAdd(bill_id=7), user=_User(), db=db)
    assert out == {"bill_id": 7, "watched": True}
    assert any(isinstance(o, user_mod.WatchlistItem) for o in db.added)


@pytest.mark.asyncio
async def test_free_account_past_the_limit_gets_the_soft_wall_code(monkeypatch):
    _free_account(monkeypatch, user_mod)
    monkeypatch.setattr(user_mod, "is_pro", lambda _e: False)
    with pytest.raises(HTTPException) as exc:
        await user_mod.add_watch(
            user_mod.WatchAdd(bill_id=7), user=_User(), db=_Db(count=user_mod.FREE_WATCHLIST_LIMIT))
    assert exc.value.status_code == 403 and exc.value.detail == "watchlist_free_limit"


@pytest.mark.asyncio
async def test_pro_account_has_no_watchlist_limit(monkeypatch):
    _free_account(monkeypatch, user_mod)
    monkeypatch.setattr(user_mod, "is_pro", lambda _e: True)
    out = await user_mod.add_watch(user_mod.WatchAdd(bill_id=7), user=_User(), db=_Db(count=500))
    assert out["watched"] is True
