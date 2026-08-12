"""Tests for the anonymous scope endpoint — app/api/scope.py.

This is the only UNAUTHENTICATED write in the API that isn't a lead-capture form, so the tests are
weighted toward what an unauthenticated write must never do: accept free text, accept unbounded
input, or accept an id we didn't mint. The happy path is one row; the abuse paths are the point.

The sanitizers are pure, so most of this needs no DB. The 422 path is exercised through the router
because the rejection has to happen before anything touches the database.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.scope import _clean_materials, _clean_states, router
from app.database import get_db
from app.schemas import _CLIENT_ID_RE


# --- Free text must not survive ---------------------------------------------------

def test_material_slugs_outside_the_vocabulary_are_dropped():
    """The closed vocabulary is what stops this being an anonymous storage channel."""
    assert _clean_materials(["plastic_packaging", "'; DROP TABLE bills;--"]) == ["plastic_packaging"]
    assert _clean_materials(["mailto:someone@example.com"]) == []


def test_states_must_be_two_letter_codes():
    assert _clean_states(["ca", "OR"]) == ["CA", "OR"]
    # Anything that isn't a bare two-letter alpha code is not a state code.
    assert _clean_states(["California", "C4", "", "  ", "N"]) == []


def test_partial_validity_keeps_the_good_half():
    """A stale client shipping one unknown slug shouldn't cost us the rest of the signal —
    dropping beats 422ing, because the remaining selections are still a true answer."""
    assert _clean_materials(["electronics", "unobtainium", "batteries"]) == [
        "electronics",
        "batteries",
    ]


# --- Bounded input ----------------------------------------------------------------

def test_lists_are_capped():
    """Caps bound the row size; without them an unauthenticated POST sets the size of a JSONB
    column. 51 states + DC is the real ceiling, so a 500-element list is abuse, not a user."""
    assert len(_clean_states([f"{a}{b}" for a in "ABCDEFGH" for b in "ABCDEFGHIJ"])) <= 60
    assert len(_clean_materials(["electronics"] * 500)) == 1  # dedupe also holds


def test_duplicates_collapse_and_order_is_preserved():
    assert _clean_states(["OR", "CA", "OR"]) == ["OR", "CA"]
    assert _clean_materials(["glass", "glass", "metals"]) == ["glass", "metals"]


# --- The id must be one we could have minted ---------------------------------------

def test_client_id_accepts_a_uuid_and_rejects_a_tracking_key():
    assert _CLIENT_ID_RE.match("3f2504e0-4f89-11d3-9a0c-0305e82c3301")
    # An email, a uid, or anything long/structured is not a randomUUID.
    assert not _CLIENT_ID_RE.match("someone@example.com")
    assert not _CLIENT_ID_RE.match("firebase-uid-with-letters-zzz")
    assert not _CLIENT_ID_RE.match("short")
    assert not _CLIENT_ID_RE.match("x" * 80)


def test_bad_client_id_never_reaches_a_write():
    """A malformed id must 422 without the handler issuing a statement. FastAPI resolves the DB
    dependency before the body either way, so the assertion that matters is that nothing was
    EXECUTED — the session stub raises if the endpoint tries."""

    class _ExplodingSession:
        async def execute(self, *a, **kw):
            raise AssertionError("endpoint issued a query despite an invalid client_id")

        async def commit(self):
            raise AssertionError("endpoint committed despite an invalid client_id")

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: _ExplodingSession()
    client = TestClient(app)

    res = client.post(
        "/anon-scope",
        json={"client_id": "not-a-uuid@example.com", "states": ["CA"], "material_categories": []},
    )
    assert res.status_code == 422
    # The rejection names the offending field rather than failing opaquely.
    assert "client_id" in res.text


@pytest.mark.parametrize("field", ["states", "material_categories"])
def test_missing_lists_default_to_empty(field):
    """An explicit "show me everything" is a real answer, so the schema must accept a scope with
    nothing selected rather than requiring a selection."""
    from app.schemas import AnonScopeUpsert

    payload = AnonScopeUpsert(client_id="3f2504e0-4f89-11d3-9a0c-0305e82c3301")
    assert getattr(payload, field) == []
