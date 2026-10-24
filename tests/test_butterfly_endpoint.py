"""/bills/butterfly: region + status filtering and counting over the cached per-bill placement."""
import pytest

from app.api import bills as bills_api

# (region, status, wing, steps, unplaced): the shape _butterfly_rows caches.
ROWS = [
    ("FR", "enacted", "technical", frozenset({"collect", "recycle"}), frozenset()),
    ("FR", "active", "both", frozenset({"maintain"}), frozenset({"incentives"})),
    ("DE", "enacted", "technical", frozenset({"collect"}), frozenset()),
    ("US", "introduced", "biological", frozenset({"compost"}), frozenset()),
    ("US", "failed", "unclassified", frozenset(), frozenset({"other", "no_step"})),
]


@pytest.fixture(autouse=True)
def _rows(monkeypatch):
    async def fake(_db):
        return ROWS
    monkeypatch.setattr(bills_api, "_butterfly_rows", fake)


async def _call(**kw):
    kw.setdefault("regions", None)
    kw.setdefault("status", "all")
    return await bills_api.get_butterfly(response=None, db=None, **kw)


async def test_whole_corpus():
    r = await _call()
    assert r.total == 5
    assert r.steps == {"collect": 2, "recycle": 1, "maintain": 1, "compost": 1}
    assert r.wings == {"technical": 2, "biological": 1, "both": 1, "unclassified": 1}
    assert r.unplaced == {"incentives": 1, "waste_shipment": 0, "other": 1, "no_step": 1}


async def test_region_and_enacted_includes_active():
    r = await _call(regions="FR", status="enacted")
    assert r.total == 2   # "active" counts as in force
    assert r.steps == {"collect": 1, "recycle": 1, "maintain": 1}


async def test_pending_and_ended_split():
    assert (await _call(regions="US", status="pending")).total == 1
    assert (await _call(regions="US", status="ended")).total == 1
    assert (await _call(regions="FR,DE", status="enacted")).steps["collect"] == 2
