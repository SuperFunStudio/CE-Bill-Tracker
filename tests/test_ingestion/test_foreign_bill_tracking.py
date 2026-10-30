"""Bill-tracking foreign adapters (tracks_status): the Câmara status mapping, and sync_foreign's
re-fetch of tracked rows that discovery no longer returns, with status_change events.

sync_foreign runs against an in-memory fake session that answers the four queries it issues (the
only_new id list, the tracked-rows refresh query, the per-law Bill and BillText lookups) by
evaluating them over a dict of Bill rows — the refresh query's filters are applied for real, so the
"final outcomes are not re-fetched" and "only in-scope rows" rules are exercised, not assumed.
"""
import datetime

import httpx
import pytest

import app.database
from app.ingestion import foreign
from app.ingestion.foreign import (
    BR_CAMARA_PAGE, BrazilCamaraClient, ForeignLaw, ForeignSourceClient, br_camara_status,
)
from app.models import Bill, BillChange, BillText


def test_situation_codes_map_onto_the_canonical_statuses():
    assert br_camara_status(1140) == "enacted"         # Transformado em Norma Jurídica
    assert br_camara_status(937) == "vetoed"
    assert br_camara_status(1303) == "passed_chamber"  # Enviada ao Senado Federal
    assert br_camara_status(1150) == "passed"          # Aguardando Sanção
    assert br_camara_status(915) == "in_committee"     # Aguardando Parecer
    assert br_camara_status(923) == "failed"           # Arquivada
    assert br_camara_status(925) == "introduced"       # Tramitando em Conjunto: still moving
    assert br_camara_status("1140") == "enacted"
    assert br_camara_status(None) == "introduced"
    assert BrazilCamaraClient.tracks_status


@pytest.mark.asyncio
async def test_camara_fetch_reads_status_and_last_action_date():
    detail = {"dados": {
        "siglaTipo": "PL", "numero": 505, "ano": 2022, "ementa": "Dispõe sobre logística reversa.",
        "dataApresentacao": "2022-03-09T15:45",
        "statusProposicao": {"codSituacao": 923, "descricaoSituacao": "Arquivada",
                             "dataHora": "2027-02-01T10:00"},
    }}
    client = BrazilCamaraClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=detail)))
    law = await client.fetch("2317473")
    assert law.title == "PL 505/2022"
    assert law.status == "failed"
    assert law.status_date == datetime.date(2022, 3, 9)
    assert law.last_action_date == datetime.date(2027, 2, 1)
    assert law.source_url == BR_CAMARA_PAGE.format(id="2317473")


# --- sync_foreign against a fake session -------------------------------------------------------

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeDB:
    bills: dict[str, Bill] = {}
    texts: dict[int, BillText] = {}
    changes: list[BillChange] = []
    next_id = 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, row):
        if isinstance(row, Bill):
            FakeDB.bills[row.foreign_id] = row
        elif isinstance(row, BillText):
            self._pending_text = row
        elif isinstance(row, BillChange):
            FakeDB.changes.append(row)

    async def flush(self):
        for b in FakeDB.bills.values():
            if b.id is None:
                b.id, FakeDB.next_id = FakeDB.next_id, FakeDB.next_id + 1
        pending = getattr(self, "_pending_text", None)
        if pending is not None:
            FakeDB.texts[pending.bill_id] = pending
            self._pending_text = None

    async def commit(self):
        await self.flush()

    async def execute(self, stmt):
        sql = str(stmt)
        params = stmt.compile().params
        if "FROM bill_texts" in sql:
            await self.flush()
            bid = next(v for k, v in params.items() if k.startswith("bill_id"))
            return _Result([t for t in [FakeDB.texts.get(bid)] if t])
        if "LIKE" in sql:  # the tracks_status refresh query — apply its filters for real
            prefix = next(v for k, v in params.items() if k.startswith("foreign_id")).rstrip("%")
            final = next(v for k, v in params.items() if k.startswith("status"))
            return _Result([b.foreign_id for b in FakeDB.bills.values()
                            if b.foreign_id.startswith(prefix) and b.ce_relevant is True
                            and b.status not in final])
        if "IS NOT NULL" in sql:  # only_new: every stored foreign_id
            return _Result(list(FakeDB.bills))
        fid = next(v for k, v in params.items() if k.startswith("foreign_id"))
        return _Result([b for b in [FakeDB.bills.get(fid)] if b])


class FakeTracker(ForeignSourceClient):
    """Discovery returns only `discovered`; fetch serves `laws` (source_id -> (status, text))."""
    region, source, tracks_status = "BR", "camara", True
    discovered: list[str] = []
    laws: dict[str, tuple[str, str]] = {}

    async def discover(self):
        return [(sid, "") for sid in self.discovered]

    async def fetch(self, source_id, english_label=""):
        status, text = self.laws[source_id]
        return ForeignLaw(source_id=source_id, region="BR", source="camara", title=f"PL {source_id}",
                          full_text=text, source_url="https://example.test", status=status,
                          status_date=datetime.date(2025, 1, 1),
                          last_action_date=datetime.date(2026, 10, 20))


@pytest.fixture
def db(monkeypatch):
    FakeDB.bills, FakeDB.texts, FakeDB.changes, FakeDB.next_id = {}, {}, [], 1
    FakeTracker.discovered, FakeTracker.laws = [], {}
    monkeypatch.setattr(app.database, "AsyncSessionLocal", FakeDB)
    monkeypatch.setitem(foreign.FOREIGN_CLIENTS, "BR_TEST", FakeTracker)
    return FakeDB


def _stored(sid, status, text="same text", relevant=True, reviewed=False):
    b = Bill(foreign_id=f"BR:camara:{sid}", region="BR", state="BR", status=status,
             ce_relevant=relevant, reviewed=reviewed)
    b.id, FakeDB.next_id = FakeDB.next_id, FakeDB.next_id + 1
    FakeDB.bills[b.foreign_id] = b
    FakeDB.texts[b.id] = BillText(bill_id=b.id, text=text, char_len=len(text))
    return b


async def _sync():
    return await foreign.sync_foreign("BR_TEST", classify=False, only_new=True)


async def test_tracked_row_outside_discovery_is_refetched_and_its_move_recorded(db):
    old = _stored("1", "in_committee")
    FakeTracker.laws = {"1": ("passed_chamber", "same text")}
    summary = await _sync()
    assert summary["refreshed"] == 1 and summary["status_changes"] == 1
    assert old.status == "passed_chamber"
    assert old.last_action_date == datetime.date(2026, 10, 20)
    (change,) = db.changes
    assert (change.old_value, change.new_value) == ({"status": "in_committee"},
                                                    {"status": "passed_chamber"})
    assert summary["to_classify"] == 0  # status moved, text didn't: no re-classification


async def test_final_outcomes_and_out_of_scope_rows_are_not_refetched(db):
    _stored("1", "enacted")
    _stored("2", "vetoed")
    _stored("3", "introduced", relevant=False)
    _stored("4", "failed")  # archived bills can be unarchived, so they stay tracked
    FakeTracker.laws = {"4": ("failed", "same text")}
    summary = await _sync()
    assert summary["refreshed"] == 1 and summary["status_changes"] == 0


async def test_legacy_active_relabel_is_not_an_alert_but_a_real_outcome_is(db):
    a = _stored("1", "active")
    b = _stored("2", "active")
    FakeTracker.laws = {"1": ("in_committee", "same text"), "2": ("failed", "same text")}
    summary = await _sync()
    assert (a.status, b.status) == ("in_committee", "failed")
    assert [c.bill_id for c in db.changes] == [b.id]
    assert summary["status_changes"] == 1


async def test_refreshed_row_is_reclassified_only_if_its_text_changed_and_never_if_reviewed(db):
    _stored("1", "introduced", text="old text")
    _stored("2", "introduced", text="old text", reviewed=True)
    FakeTracker.discovered = ["9"]  # one genuinely new bill alongside the refresh
    FakeTracker.laws = {"1": ("introduced", "new text"), "2": ("introduced", "new text"),
                        "9": ("introduced", "brand new")}
    summary = await _sync()
    assert summary["refreshed"] == 2
    assert summary["to_classify"] == 2  # bill 1 (text changed) + the new bill 9; not reviewed bill 2
    assert summary["status_changes"] == 0
    assert db.texts[db.bills["BR:camara:2"].id].text == "new text"  # text still refreshed


async def test_only_new_matches_multi_region_adapters_through_foreign_id_for(db, monkeypatch):
    # A TRIS-style adapter: region "EU" on the client, each law stored under its own country.
    monkeypatch.setattr(FakeTracker, "tracks_status", False)
    monkeypatch.setattr(FakeTracker, "foreign_id_for",
                        lambda self, sid: f"{sid[-2:]}:camara:{sid}")
    stored = Bill(foreign_id="PL:camara:2026/0550/PL", region="PL", state="PL", status="introduced")
    db.bills[stored.foreign_id] = stored
    FakeTracker.discovered = ["2026/0550/PL", "2026/0109/FI"]
    FakeTracker.laws = {"2026/0109/FI": ("introduced", "text")}
    summary = await _sync()
    assert summary["discovered"] == 1  # the stored Polish notification is not re-fetched


async def test_enacted_law_adapters_are_untouched(db, monkeypatch):
    monkeypatch.setattr(FakeTracker, "tracks_status", False)
    _stored("1", "introduced")
    summary = await _sync()
    assert summary["refreshed"] == 0 and summary["discovered"] == 0
