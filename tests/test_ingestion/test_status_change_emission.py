"""Unit tests for the status-change alert event emitted by the OpenStates upsert.

`_upsert_openstates_bill` is the only producer of `status_change` BillChange rows (the real-time
dispatcher consumes them and matches subscribers by topic/jurisdiction/material). It must emit one —
and exactly one — when an already-tracked, ce_relevant bill's stored status differs from the freshly
inferred one, and must stay silent for brand-new bills, irrelevant bills, and no-op re-ingests.

These use a lightweight fake session (no DB): `_upsert_openstates_bill` issues two reads in order —
the LegiScan-dedup `select(Bill)` (`.scalar_one_or_none()`) then the stored-row lookup
(`.one_or_none()`) — followed by the upsert `execute`. The fake returns queued results in that order
and records `db.add(...)` calls.
"""
from types import SimpleNamespace

import pytest

from app.ingestion.coordinator import IngestionCoordinator
from app.models import BillChange

# A bill_data payload whose normalized actions infer to "enacted" (executive-signature), with the
# includes (abstracts/sources/actions) the real search cycle requests.
_ENACTED_BILL = {
    "id": "ocd-bill/abc-123",
    "identifier": "SB 54",
    "title": "Packaging Extended Producer Responsibility Act",
    "abstracts": [{"abstract": "An act relating to packaging EPR."}],
    "sources": [{"url": "https://leginfo.example.gov/sb54"}],
    "latest_action_date": "2026-06-01",
    "latest_action_description": "Signed by governor",
    "actions": [{"classification": ["executive-signature"]}],
    "updated_at": "2026-06-02T00:00:00Z",
}


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def one_or_none(self):
        return self._value


class _FakeDB:
    """Returns queued results for successive execute() calls; records add()s."""

    def __init__(self, results):
        self._results = list(results)
        self._i = 0
        self.added = []

    async def execute(self, *_a, **_k):
        value = self._results[self._i] if self._i < len(self._results) else None
        self._i += 1
        return _FakeResult(value)

    def add(self, obj):
        self.added.append(obj)


def _stored(**kw):
    """A stored-row stand-in matching the SELECT id, status, ce_relevant, change_hash, source_url."""
    return SimpleNamespace(
        id=kw.get("id", 99),
        status=kw.get("status", "introduced"),
        ce_relevant=kw.get("ce_relevant", True),
        # Deliberately != the freshly computed hash so the idempotency skip doesn't fire.
        change_hash=kw.get("change_hash", "STALEHASH"),
        source_url=kw.get("source_url", "https://leginfo.example.gov/sb54"),
    )


async def _run(stored_row, bill_data=_ENACTED_BILL):
    # results order: [LegiScan dedup -> None, stored-row lookup -> stored_row, upsert execute -> _]
    db = _FakeDB([None, stored_row, None])
    coordinator = IngestionCoordinator()
    outcome = await coordinator._upsert_openstates_bill(db, bill_data, "CA")
    return outcome, db


class TestStatusChangeEmission:
    async def test_emits_status_change_when_relevant_bill_advances(self):
        outcome, db = await _run(_stored(id=42, status="introduced", ce_relevant=True))
        assert outcome == "upserted"
        changes = [o for o in db.added if isinstance(o, BillChange)]
        assert len(changes) == 1
        change = changes[0]
        assert change.change_type == "status_change"
        assert change.bill_id == 42
        assert change.old_value == {"status": "introduced"}
        assert change.new_value == {"status": "enacted"}

    async def test_no_event_when_status_unchanged(self):
        # Stored status already matches the freshly inferred "enacted" -> no movement, no event.
        outcome, db = await _run(_stored(status="enacted"))
        assert outcome == "upserted"
        assert [o for o in db.added if isinstance(o, BillChange)] == []

    async def test_no_event_for_new_bill(self):
        # No stored row (first time we see this openstates_id) -> the new-bill alert's job, not this.
        outcome, db = await _run(stored_row=None)
        assert outcome == "upserted"
        assert [o for o in db.added if isinstance(o, BillChange)] == []

    async def test_no_event_when_not_ce_relevant(self):
        outcome, db = await _run(_stored(status="introduced", ce_relevant=False))
        assert outcome == "upserted"
        assert [o for o in db.added if isinstance(o, BillChange)] == []

    async def test_no_event_when_ce_relevant_is_null(self):
        # Unclassified bills (ce_relevant NULL) are falsy -> excluded, same as False.
        outcome, db = await _run(_stored(status="introduced", ce_relevant=None))
        assert outcome == "upserted"
        assert [o for o in db.added if isinstance(o, BillChange)] == []
