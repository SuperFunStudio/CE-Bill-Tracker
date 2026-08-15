"""Pins the server-side enforcement of CAP_FEDERAL and CAP_INSIGHTS_IMPACT.

Both capabilities were defined in the plan matrix and then never wired to a route: the Federal
Actions page and the Insights page each put a membership card in front of endpoints that answered
anyone. For a product sold to consultancies and legal teams — a population that opens dev tools —
a client-side `if` is not a paywall.

Two shapes are enforced, and the tests pin the difference because getting it backwards breaks
something either way:

  TEASER (federal actions, bill outcomes) — free surfaces read these routes, so an unentitled caller
    gets a short slice, never a 403. The homepage preemption banner, the Standings rollup and the
    outcome ticker all live here. A hard gate would blank the public homepage.

  HARD 403 (litigation feed, insights analysis) — no free consumer exists, so the honest answer is a
    refusal rather than a silently-truncated list.

The third property is the one the reviewer of this code missed entirely and is the reason the gate
was worth nothing before: the CDN snapshot builder must not bake gated data into public/data/*.json.
A static fallback for a gated feed is unauthenticated by construction.
"""
import inspect
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import auth as auth_mod
from app.api.auth import CAP_FEDERAL, CAP_INSIGHTS_IMPACT, get_optional_capability
from app.api.federal import FEDERAL_TEASER_LIMIT
from app.config import settings

REPO = Path(__file__).resolve().parents[2]


# --- the optional-capability dependency ----------------------------------------------------------


class _Ent:
    """Minimal entitlement stand-in; resolve_plan/has_capability read plan + status."""

    def __init__(self, plan):
        self.plan = plan
        self.status = "active"
        self.comp = False
        self.current_period_end = None
        self.preview_until = None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "header",
    [None, "", "Basic abc", "Bearer", "bearer garbage"],
    ids=["missing", "empty", "wrong-scheme", "no-token", "unverifiable"],
)
async def test_optional_capability_returns_false_rather_than_raising(monkeypatch, header):
    """The whole point of the optional form: it must never 401 public traffic, whatever arrives in
    the header. A raise here takes the free homepage down with it."""
    dep = get_optional_capability(CAP_FEDERAL)
    assert await dep(authorization=header, db=None) is False


@pytest.mark.asyncio
async def test_optional_capability_true_only_for_a_carrying_plan(monkeypatch):
    async def _user(_authorization):
        return auth_mod.AuthedUser(uid="u1", email="a@example.com", email_verified=True)

    monkeypatch.setattr(auth_mod, "get_current_user", _user)
    monkeypatch.setattr(auth_mod, "is_admin", lambda _u: False)

    dep = get_optional_capability(CAP_FEDERAL)
    for plan, expected in [("pro", True), ("research", False), ("student", False), ("free", False)]:
        monkeypatch.setattr(auth_mod, "get_entitlement", _entitlement_returning(plan))
        assert await dep(authorization="Bearer t", db=None) is expected, plan


@pytest.mark.asyncio
async def test_insights_impact_is_pro_only(monkeypatch):
    """The Insights briefing room is a Pro feature — what the page has always said and what /pricing
    sells. CAP_INSIGHTS_IMPACT sat in the Researcher set while nothing enforced it, so the
    discrepancy was invisible until the capability was wired to a route. Pinned at Pro-only so it
    can't drift back down without someone deciding to sell it there.
    """
    async def _user(_authorization):
        return auth_mod.AuthedUser(uid="u1", email="a@example.com", email_verified=True)

    monkeypatch.setattr(auth_mod, "get_current_user", _user)
    monkeypatch.setattr(auth_mod, "is_admin", lambda _u: False)
    dep = get_optional_capability(CAP_INSIGHTS_IMPACT)
    for plan, expected in [("pro", True), ("enterprise", True), ("research", False), ("student", False)]:
        monkeypatch.setattr(auth_mod, "get_entitlement", _entitlement_returning(plan))
        assert await dep(authorization="Bearer t", db=None) is expected, plan


def test_researcher_keeps_what_it_is_actually_sold_on():
    """The other side of moving CAP_INSIGHTS_IMPACT up: Researcher must not lose the capabilities its
    pricing card promises (Student's set, plus citation/export workflow which isn't capability-gated).
    """
    from app.api.auth import CAP_ASK, CAP_DESIGN_GUIDE, CAP_EXPLORE, PLAN_CAPS

    assert {CAP_EXPLORE, CAP_ASK, CAP_DESIGN_GUIDE} <= PLAN_CAPS["research"]
    assert PLAN_CAPS["student"] <= PLAN_CAPS["research"] <= PLAN_CAPS["pro"]


def _entitlement_returning(plan):
    async def _get(_db, _user):
        return _Ent(plan)

    return _get


# --- hard-403 routers ----------------------------------------------------------------------------


def _client(router):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


INSIGHTS_PATHS = ["/insights/state-gap", "/insights/state-cycles?state=CA", "/insights/champions"]


def test_insights_routes_401_an_anonymous_caller():
    from app.api.insights import router

    client = _client(router)
    # Every route on the router, not just one — the gate is declared router-level and a future
    # route added below it must inherit it.
    for path in INSIGHTS_PATHS:
        assert client.get(path).status_code == 401, path


def test_insights_routes_403_a_paying_non_admin(monkeypatch):
    """The /insights router is ADMIN-only, not Pro. Its four routes rest on OpenStates sponsor data
    backfilled for US states alone, which is why the views they feed were moved off the member-facing
    Insights page into the admin console. A Pro seat reaching them directly would be sold access to
    unfinished analysis, so a paying non-admin must be refused as firmly as a stranger.

    Pinned because the failure is silent in the UI: nothing member-facing calls these, so a gate that
    drifted back down to Pro would look exactly like a gate that hadn't.
    """
    from app.api import insights as insights_mod
    from app.api.auth import get_current_user

    async def _user():
        return auth_mod.AuthedUser(uid="u1", email="pro@example.com", email_verified=True)

    # get_current_user is captured by reference inside require_admin's signature at import time, so
    # monkeypatching the module attribute does NOT reach it — the token would really be verified
    # against Firebase and 401 first. FastAPI's dependency_overrides is the seam that works here.
    # is_admin, by contrast, is looked up as a module global when require_admin runs, so it patches.
    app = FastAPI()
    app.include_router(insights_mod.router)
    app.dependency_overrides[get_current_user] = _user
    monkeypatch.setattr(auth_mod, "is_admin", lambda _u: False)

    client = TestClient(app)
    for path in INSIGHTS_PATHS:
        assert client.get(path, headers={"Authorization": "Bearer t"}).status_code == 403, path


def test_bulk_litigation_401s_an_anonymous_caller():
    from app.api.federal import litigation_router

    assert _client(litigation_router).get("/litigation-cases").status_code == 401


# --- the teaser limits ---------------------------------------------------------------------------


def test_federal_teaser_is_small_enough_to_be_a_teaser():
    # A "teaser" that returns the default page size is not a gate. Pinned as a ceiling rather than an
    # exact value so the number can be tuned without a test edit, but not quietly raised to 200.
    assert 1 <= FEDERAL_TEASER_LIMIT <= 10


def test_outcome_teaser_is_small_enough_to_be_a_teaser():
    from app.api.bills import OUTCOME_TEASER_LIMIT

    assert 1 <= OUTCOME_TEASER_LIMIT <= 10


# --- the CDN snapshot ----------------------------------------------------------------------------


def _snapshot_endpoint_paths() -> list[str]:
    """The `path` values in build-snapshot.mjs's ENDPOINTS array, read out of the source. Parsing the
    JS beats duplicating the list here — a duplicate would keep passing after someone adds a gated
    endpoint to the real one, which is exactly the regression this guards."""
    src = (REPO / "dashboard-next" / "scripts" / "build-snapshot.mjs").read_text(encoding="utf-8")
    block = src.split("const ENDPOINTS", 1)[1].split("];", 1)[0]
    return re.findall(r"path:\s*'([^']+)'", block)


# Routes that must never be baked to the public CDN, with why. The snapshot builder is
# unauthenticated, so anything gated that it fetches lands in public/data as either a leak (if the
# API answers) or a useless truncated file (if it doesn't).
GATED_PREFIXES = {
    "/federal-actions?": "CAP_FEDERAL action rows",
    "/litigation-cases": "CAP_FEDERAL litigation feed",
    "/insights/": "CAP_INSIGHTS_IMPACT analysis",
    "/bills/deadlines/upcoming": "Pro deadline calendar (C-1)",
    "/bills/outcomes": "CAP_INSIGHTS_IMPACT documented outcomes",
}


@pytest.mark.parametrize("prefix,why", list(GATED_PREFIXES.items()))
def test_snapshot_never_bakes_gated_data_to_the_public_cdn(prefix, why):
    for path in _snapshot_endpoint_paths():
        assert not path.startswith(prefix), f"{path} would publish {why} to public/data"


def test_snapshot_still_carries_the_free_aggregates():
    """The other half: gating must not have starved the free surfaces. Both banners fall back to
    these files on a cold or unreachable API."""
    paths = _snapshot_endpoint_paths()
    assert any(p.startswith("/federal-actions/summary") for p in paths)
    assert any(p.startswith("/bills/deadlines/summary") for p in paths)


def test_snapshot_bills_query_covers_every_region():
    """The corpus snapshot is the PRIMARY source for whole-corpus reads now (hooks/useBills.ts), not
    just a cold-API fallback — so an incomplete one is wrong data on the homepage, not a degraded
    fallback. /bills defaults to US-ONLY when no region is given, which had this baking 1,576 of
    2,493 rows and silently dropping every non-US jurisdiction from the file the site reads.
    """
    bills = [p for p in _snapshot_endpoint_paths() if p.startswith("/bills?")]
    assert bills, "the bills corpus is no longer snapshotted"
    for path in bills:
        assert "region=all" in path, f"{path} bakes only the US corpus — non-US rows would vanish"


# --- the anonymous bulk ceiling ------------------------------------------------------------------


def test_anon_bulk_limit_ships_dormant():
    """Pinned deliberately: the cap must NOT start enforcing on deploy. Public pages read the corpus
    from the CDN snapshot now, but that only became true in the same change — so enforcement is a
    Cloud Run env var flipped after watching real traffic, not a surprise in a build. A future edit
    lowering this default is a product decision that should have to change this test on purpose.
    """
    from app.api.bills import list_bills

    # Dormant means "equal to the schema maximum", so read that maximum off the route rather than
    # hardcoding it twice — if someone raises the ceiling on the Query, this still checks alignment.
    limit_q = inspect.signature(list_bills).parameters["limit"].default
    schema_max = next(getattr(m, "le") for m in limit_q.metadata if hasattr(m, "le"))
    assert settings.anon_bulk_limit == schema_max == 5000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "header",
    [None, "", "Basic abc", "Bearer", "bearer garbage"],
    ids=["missing", "empty", "wrong-scheme", "no-token", "unverifiable"],
)
async def test_bulk_ceiling_treats_an_unverified_caller_as_anonymous(header):
    """A header sniff would let `Authorization: Bearer anything` lift the cap for everyone, which is
    the whole failure this is supposed to prevent."""
    from app.api.bills import _caller_is_authenticated

    assert await _caller_is_authenticated(header) is False


@pytest.mark.asyncio
async def test_bulk_ceiling_refuses_rather_than_truncates(monkeypatch):
    """400, not a short 200. A caller who asked for the corpus and received a capped slice with a
    success status would reasonably publish it as the whole corpus."""
    from app.api import bills as bills_mod

    monkeypatch.setattr(bills_mod.settings, "anon_bulk_limit", 500)
    with pytest.raises(HTTPException) as exc:
        await bills_mod.list_bills(limit=5000, authorization=None, db=None)
    assert exc.value.status_code == 400
    # The refusal has to name the way through, or it's just a wall.
    assert "/data/bills.json" in exc.value.detail and "limit/offset" in exc.value.detail


def test_no_gated_snapshot_files_are_left_on_disk():
    """Deleting the endpoint from the builder doesn't delete yesterday's output — and public/ is
    copied verbatim into the static export, so a stale file keeps serving the paid dataset."""
    data_dir = REPO / "dashboard-next" / "public" / "data"
    if not data_dir.exists():
        pytest.skip("no snapshot directory in this checkout")
    for stale in ("federal-actions.json", "litigation-cases.json"):
        assert not (data_dir / stale).exists(), f"stale gated snapshot still present: {stale}"
