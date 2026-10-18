"""The nightly OpenStates rotation must resume where it stopped and search each query from its own
last sweep — not restart at query 1 with a 2-day window. See app/ingestion/openstates_cursor.py."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.ingestion import coordinator as coord_mod
from app.ingestion.coordinator import IngestionCoordinator
from app.ingestion.openstates_cursor import SweepCursor

QUERIES = ["q0", "q1", "q2"]
STATES = ["AL", "AK", "AZ"]
NOW = datetime(2026, 10, 18, 2, 0, tzinfo=timezone.utc)


def _steps(cursor, now=NOW):
    return list(cursor.steps(QUERIES, STATES, now, window_days=2, fallback_days=90))


def test_fresh_cursor_walks_one_full_lap_with_fallback_window():
    steps = _steps(SweepCursor())
    assert [(s.query, s.state) for s in steps] == [(q, st) for q in QUERIES for st in STATES]
    assert all(s.since == NOW - timedelta(days=90) for s in steps)


def test_resumes_mid_query_and_wraps_to_finish_the_lap():
    cursor = SweepCursor(position={"query": "q1", "state": "AK", "page": 3,
                                   "started_at": "2026-10-17T02:00:00+00:00",
                                   "since": "2026-08-01T00:00:00+00:00"})
    steps = _steps(cursor)
    assert [(s.query, s.state) for s in steps] == [
        ("q1", "AK"), ("q1", "AZ"), ("q2", "AL"), ("q2", "AK"), ("q2", "AZ"),
        ("q0", "AL"), ("q0", "AK"), ("q0", "AZ"), ("q1", "AL"),
    ]
    assert steps[0].start_page == 3 and steps[1].start_page == 1
    # The in-progress sweep keeps the window it started with.
    assert steps[1].since == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert steps[1].started_at == datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc)
    # The trailing q1/AL belongs to a new sweep of q1, not the resumed one.
    assert steps[-1].started_at == NOW and not steps[-1].last_state_of_query


def test_since_is_last_sweep_start_but_never_narrower_than_the_nightly_window():
    cursor = SweepCursor(swept_at={"q0": "2026-08-20T02:00:00+00:00",
                                   "q1": "2026-10-17T23:00:00+00:00"})
    assert cursor.since_for("q0", NOW, 2, 90) == datetime(2026, 8, 20, 2, tzinfo=timezone.utc)
    assert cursor.since_for("q1", NOW, 2, 90) == NOW - timedelta(days=2)


def test_stale_position_from_an_edited_keyword_list_restarts_at_the_top():
    cursor = SweepCursor(position={"query": "removed", "state": "AL", "page": 1})
    assert _steps(cursor)[0].query == "q0"


def test_mark_done_stamps_the_sweep_start_and_advances_to_the_next_query():
    cursor = SweepCursor()
    steps = _steps(cursor)
    cursor.mark_done(steps[0], QUERIES, STATES)
    assert cursor.position["query"] == "q0" and cursor.position["state"] == "AK"
    cursor.mark_done(steps[2], QUERIES, STATES)
    assert cursor.swept_at == {"q0": NOW.isoformat()}
    assert cursor.position == {"query": "q1", "state": "AL", "page": 1,
                               "started_at": None, "since": None}


# --- End to end through run_openstates_cycle, with a fake client and session ---------------------


class FakeSession:
    def __init__(self):
        self.rows = {}

    async def get(self, model, key):
        return self.rows.get(key)

    def add(self, row):
        self.rows[row.source] = row

    async def commit(self):
        pass


class FakeClient:
    """Answers `budget` calls a night, then 429s. One page per (query, state)."""

    calls: list = []
    budget = 0

    def __init__(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def search_bills(self, query, jurisdiction, updated_since, page, per_page):
        if FakeClient.budget <= 0:
            request = httpx.Request("GET", "https://v3.openstates.org/bills")
            raise httpx.HTTPStatusError("429", request=request,
                                        response=httpx.Response(429, request=request))
        FakeClient.budget -= 1
        FakeClient.calls.append((query, jurisdiction.upper(), updated_since))
        return {"results": [], "pagination": {"page": 1, "max_page": 1}}


@pytest.fixture
def fake_env(monkeypatch):
    monkeypatch.setattr(coord_mod, "OpenStatesClient", FakeClient)
    monkeypatch.setattr(coord_mod, "OPENSTATES_EPR_QUERIES", QUERIES)
    monkeypatch.setattr(coord_mod, "ALL_STATES", STATES)
    monkeypatch.setattr(coord_mod.settings, "openstates_request_delay_seconds", 0)
    FakeClient.calls = []
    return FakeSession()


async def _night(db, budget):
    FakeClient.budget = budget
    FakeClient.calls = []
    return await IngestionCoordinator().run_openstates_cycle(db, resume=True)


async def test_consecutive_nights_cover_every_query_without_repeats(fake_env):
    db = fake_env
    seen = []
    for _ in range(3):
        summary = await _night(db, budget=4)
        assert summary["openstates_throttled"]
        seen += [(q, s) for q, s, _ in FakeClient.calls]
    # 3 nights x 4 calls = 12 >= 9 steps: a full lap, in order, then the next lap begins.
    assert seen[:9] == [(q, st) for q in QUERIES for st in STATES]
    assert seen[9:] == [("q0", "AL"), ("q0", "AK"), ("q0", "AZ")]
    assert set(db.rows["openstates"].cursor["swept_at"]) == {"q0", "q1", "q2"}


async def test_second_sweep_of_a_query_searches_from_its_first_sweep(fake_env):
    db = fake_env
    await _night(db, budget=3)  # completes q0
    # Pretend q0's sweep was a month ago (the nights here run seconds apart, so the 2-day floor
    # would otherwise win). Reassign the dict, as the coordinator does, so the change sticks.
    first_sweep = datetime.now(timezone.utc) - timedelta(days=30)
    row = db.rows["openstates"]
    row.cursor = {**row.cursor, "swept_at": {**row.cursor["swept_at"],
                                             "q0": first_sweep.isoformat()}}
    # q1, q2, then the 429s land on q0/AL: its new sweep has begun, with its window fixed now.
    await _night(db, budget=6)
    await _night(db, budget=1)  # q0/AL again
    (_, _, since), = FakeClient.calls
    assert since == first_sweep


async def test_state_filtered_runs_leave_the_cursor_alone(fake_env):
    db = fake_env
    FakeClient.budget = 10
    since = NOW - timedelta(days=2)
    await IngestionCoordinator().run_openstates_cycle(
        db, state_filter="AK", updated_since=since, resume=True)
    assert "openstates" not in db.rows
    assert [s for _, _, s in FakeClient.calls] == [since] * 3
