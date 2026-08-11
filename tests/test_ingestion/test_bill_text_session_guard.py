"""Pins the session guard on the LegiScan text ladder.

Bill numbers reset every session, so a (state, bill_number) match can resolve a completely different
statute. Prod evidence: CA SB-54 (2022 packaging EPR) had the 2025-26 SB 54 "court fee waivers" text
attached, and the extractor — correctly, given what it was handed — reported every circular-economy
dimension as not_applicable. These tests hold the two defenses: the search is constrained by the
bill's year, and the resolved bill's session window is verified before its text is accepted.
"""
import types

import pytest

from app.ingestion.bill_text import (
    _legiscan_text,
    _resolve_legiscan_id,
    _session_matches,
    bill_year,
)


def _bill(**kw):
    base = dict(
        state="CA", bill_number="SB-54", legiscan_bill_id=None,
        openstates_id=None, source_url=None, status_date=None, last_action_date=None,
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


class _FakeDate:
    def __init__(self, year):
        self.year = year


class _FakeClient:
    """Records how search was called and serves a canned bill."""

    def __init__(self, results=None, bill=None):
        self.results = results or []
        self.bill = bill or {}
        self.search_kwargs = None

    async def search(self, query, state=None, year=None, page=1):
        self.search_kwargs = {"query": query, "state": state, "year": year}
        return self.results

    async def get_bill(self, bill_id):
        return self.bill


# --- session window matching ---------------------------------------------------------------

def test_session_window_contains_the_year():
    assert _session_matches({"session": {"year_start": 2021, "year_end": 2022}}, 2022)


def test_session_window_two_sessions_away_is_rejected():
    # The exact CA SB-54 failure: a 2022 bill offered 2025-26 text.
    assert not _session_matches({"session": {"year_start": 2025, "year_end": 2026}}, 2022)


def test_one_year_of_slack_for_bills_chaptered_after_the_session_closed():
    assert _session_matches({"session": {"year_start": 2021, "year_end": 2022}}, 2023)


def test_unknown_session_window_is_not_a_match():
    # An unverifiable match is precisely the case that attached the wrong statute.
    assert not _session_matches({}, 2022)


# --- year resolution ------------------------------------------------------------------------

def test_bill_year_prefers_status_date_then_last_action():
    assert bill_year(_bill(status_date=_FakeDate(2022), last_action_date=_FakeDate(2025))) == 2022
    assert bill_year(_bill(last_action_date=_FakeDate(2025))) == 2025
    assert bill_year(_bill()) is None


# --- id resolution --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_is_constrained_by_the_bills_own_year():
    client = _FakeClient(results=[{"state": "CA", "bill_number": "SB54", "bill_id": 111}])
    lid, needs_check = await _resolve_legiscan_id(client, _bill(status_date=_FakeDate(2022)))
    assert (lid, needs_check) == (111, True)
    # Without year=, LegiScan's getSearch skews to the current session — that was the bug.
    assert client.search_kwargs["year"] == 2022


@pytest.mark.asyncio
async def test_stored_id_is_trusted_and_skips_the_session_check():
    client = _FakeClient()
    lid, needs_check = await _resolve_legiscan_id(client, _bill(legiscan_bill_id=999))
    assert (lid, needs_check) == (999, False)
    assert client.search_kwargs is None  # no search at all


@pytest.mark.asyncio
async def test_a_bill_with_no_year_is_not_resolved_by_search():
    client = _FakeClient(results=[{"state": "CA", "bill_number": "SB54", "bill_id": 111}])
    lid, _ = await _resolve_legiscan_id(client, _bill())
    assert lid is None  # falls through to OpenStates / source_url rather than guessing


# --- the guard actually withholds text ------------------------------------------------------

@pytest.mark.asyncio
async def test_wrong_session_text_is_withheld():
    client = _FakeClient(bill={
        "session": {"year_start": 2025, "year_end": 2026},
        "texts": [{"doc_id": 1, "mime": "text/html"}],
    })
    assert await _legiscan_text(client, 111, expect_year=2022) == ""


@pytest.mark.asyncio
async def test_expect_year_none_does_not_gate_a_trusted_id():
    # Stored ids must keep working even when the session block is absent from getBill.
    client = _FakeClient(bill={"texts": []})
    assert await _legiscan_text(client, 111, expect_year=None) == ""  # no docs, but no crash


# --- scraped page shells ----------------------------------------------------------------------

def test_page_footer_in_the_tail_is_rejected():
    from app.ingestion.bill_text import clean_text
    # The exact RI shape: a bill page whose document ends on the site's copyright footer.
    ri = ("Senate House Auditor General Captiol Television House Fiscal " + "statutory body " * 60
          + "Home | Privacy Policy © 2026 State of Rhode Island General Assembly. All Rights Reserved.")
    assert clean_text(ri) == ""


def test_the_same_words_mid_document_are_kept():
    from app.ingestion.bill_text import clean_text
    # A privacy bill legitimately says "privacy policy" in its body — only the TAIL is furniture,
    # so keying on the phrase anywhere would silently drop real statutes.
    body = ("A controller shall publish a privacy policy describing the categories of personal data "
            "collected. " + "and further provided that the controller shall comply. " * 40)
    assert clean_text(body) != ""


def test_javascript_shell_is_not_bill_text():
    from app.ingestion.bill_text import clean_text
    assert clean_text("<div>You need to enable JavaScript to run this app.</div>") == ""


@pytest.mark.asyncio
async def test_a_junk_rung_falls_through_instead_of_ending_the_ladder():
    """A scrape that cleans to nothing must not mask a good document on a later rung."""
    from app.ingestion.bill_text import SOURCE_OPENSTATES, fetch_clean_text

    class _LS:
        async def search(self, *a, **k):
            return []

    class _OS:
        async def get_bill_text(self, _id):
            return "SECTION 1. A producer shall register with the department. " * 20
        async def get_text_from_source(self, _url):
            return "You need to enable JavaScript to run this app."

    # legiscan resolves nothing; openstates has the real document. Before the fix, a bill whose
    # earlier rung returned un-cleanable bytes returned ("", that_source) and never got here.
    bill = _bill(state="MT", openstates_id="ocd-bill/1", source_url="https://x", 
                 status_date=_FakeDate(2025))
    txt, src = await fetch_clean_text(_LS(), _OS(), bill)
    assert src == SOURCE_OPENSTATES
    assert "producer shall register" in txt


# --- document version selection ----------------------------------------------------------------

class _DocClient:
    """Serves a bill with several text versions; records which doc_id was actually fetched."""

    def __init__(self, docs):
        self.docs = docs
        self.fetched = []

    async def get_bill(self, _id):
        return {"session": {"year_start": 2021, "year_end": 2022}, "texts": self.docs}

    async def _get(self, _op, id):  # noqa: A002
        self.fetched.append(id)
        import base64
        return {"text": {"doc": base64.b64encode(b"SECTION 1. " + b"x" * 900).decode()}}


# The real CA SB 54 document set, in the order LegiScan returns it (oldest first).
_SB54_DOCS = [
    {"doc_id": 2218821, "type": "Introduced", "date": "2020-12-07", "mime": "text/html"},
    {"doc_id": 2313600, "type": "Amended", "date": "2021-02-25", "mime": "text/html"},
    {"doc_id": 2600074, "type": "Enrolled", "date": "2022-06-30", "mime": "text/html"},
    {"doc_id": 2600075, "type": "Chaptered", "date": "2022-06-30", "mime": "text/html"},
]


@pytest.mark.asyncio
async def test_the_chaptered_version_wins_not_the_introduced_draft():
    client = _DocClient(list(_SB54_DOCS))
    await _legiscan_text(client, 111, expect_year=2022)
    assert client.fetched[0] == 2600075  # Chaptered — the text that IS the law


@pytest.mark.asyncio
async def test_later_date_wins_within_the_same_stage():
    client = _DocClient([
        {"doc_id": 1, "type": "Amended", "date": "2022-06-16", "mime": "text/html"},
        {"doc_id": 2, "type": "Amended", "date": "2022-06-24", "mime": "text/html"},
    ])
    await _legiscan_text(client, 111, expect_year=2022)
    assert client.fetched[0] == 2


@pytest.mark.asyncio
async def test_an_unknown_type_never_outranks_a_chaptered_version():
    client = _DocClient([
        {"doc_id": 9, "type": "Some New Label", "date": "2023-01-01", "mime": "text/html"},
        {"doc_id": 2600075, "type": "Chaptered", "date": "2022-06-30", "mime": "text/html"},
    ])
    await _legiscan_text(client, 111, expect_year=2022)
    assert client.fetched[0] == 2600075
