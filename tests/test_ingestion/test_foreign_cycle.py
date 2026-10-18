"""run_foreign_cycle refreshes each configured region once it is a week stale, isolates per-region
failures, and refuses to count an empty discovery as a successful refresh."""
from datetime import datetime, timedelta, timezone

import pytest

from app.scheduler import jobs


class FakeSession:
    store: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, key):
        return FakeSession.store.get(key)

    def add(self, row):
        FakeSession.store[row.source] = row

    async def commit(self):
        pass


@pytest.fixture
def env(monkeypatch):
    import asyncio

    import app.database
    import app.ingestion.foreign

    FakeSession.store = {}
    calls = []
    outcomes = {}

    async def fake_sync(region, *, classify, only_new, max_laws):
        calls.append(region)
        assert classify and only_new and max_laws == jobs.settings.max_foreign_laws_per_run
        result = outcomes.get(region, {"found": 10, "ingested": 1})
        if isinstance(result, Exception):
            raise result
        return {"region": region, **result}

    async def no_sleep(_):
        pass

    monkeypatch.setattr(app.database, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(app.ingestion.foreign, "sync_foreign", fake_sync)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(jobs.settings, "enable_foreign_ingestion", True)
    monkeypatch.setattr(jobs.settings, "foreign_ingestion_regions", ["JP", "UK", "CN"])
    monkeypatch.setattr(jobs.settings, "foreign_refresh_interval_days", 7)
    return calls, outcomes


def _stamps():
    row = FakeSession.store.get(jobs.FOREIGN_CURSOR_SOURCE)
    return (row.cursor or {}).get("last_refreshed", {}) if row else {}


async def test_first_run_refreshes_every_region_and_stamps_them(env):
    calls, _ = env
    await jobs.run_foreign_cycle()
    assert calls == ["JP", "UK", "CN"]
    assert set(_stamps()) == {"JP", "UK", "CN"}


async def test_fresh_regions_are_skipped_until_stale(env):
    calls, _ = env
    await jobs.run_foreign_cycle()
    calls.clear()
    await jobs.run_foreign_cycle()
    assert calls == []
    # Backdate UK past the interval: only it is due.
    row = FakeSession.store[jobs.FOREIGN_CURSOR_SOURCE]
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    row.cursor = {"last_refreshed": {**_stamps(), "UK": old}}
    await jobs.run_foreign_cycle()
    assert calls == ["UK"]


async def test_a_failing_region_does_not_stop_the_rest_and_is_retried(env):
    calls, outcomes = env
    outcomes["UK"] = RuntimeError("source down")
    await jobs.run_foreign_cycle()
    assert calls == ["JP", "UK", "CN"]
    assert set(_stamps()) == {"JP", "CN"}
    calls.clear()
    outcomes.pop("UK")
    await jobs.run_foreign_cycle()
    assert calls == ["UK"]


async def test_empty_discovery_is_not_a_successful_refresh(env):
    calls, outcomes = env
    outcomes["CN"] = {"found": 0, "ingested": 0}
    await jobs.run_foreign_cycle()
    assert "CN" not in _stamps()
    # Nothing new but discovery worked: that IS a successful refresh.
    outcomes["CN"] = {"found": 40, "ingested": 0}
    calls.clear()
    await jobs.run_foreign_cycle()
    assert calls == ["CN"] and "CN" in _stamps()


async def test_disabled_does_nothing(env, monkeypatch):
    calls, _ = env
    monkeypatch.setattr(jobs.settings, "enable_foreign_ingestion", False)
    await jobs.run_foreign_cycle()
    assert calls == [] and _stamps() == {}


def test_scheduler_tolerates_late_wakeups_and_registers_the_job(monkeypatch):
    monkeypatch.setattr(jobs.settings, "enable_foreign_ingestion", True)
    scheduler = jobs.setup_scheduler()
    assert scheduler._job_defaults["misfire_grace_time"] == 3600
    assert scheduler._job_defaults["coalesce"] is True
    assert scheduler.get_job("foreign_refresh") is not None


async def test_every_fetch_failing_is_not_a_successful_refresh(env):
    calls, outcomes = env
    outcomes["JP"] = {"found": 4, "discovered": 3, "fetched": 0, "ingested": 0}
    await jobs.run_foreign_cycle()
    assert "JP" not in _stamps()
    # All already ingested (nothing new to fetch) is fine.
    outcomes["JP"] = {"found": 4, "discovered": 0, "fetched": 0, "ingested": 0}
    await jobs.run_foreign_cycle()
    assert "JP" in _stamps()
