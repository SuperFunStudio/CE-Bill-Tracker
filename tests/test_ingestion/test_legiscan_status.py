"""LegiScan status sync: number parsing, session/title guards, forward-only status moves."""
from datetime import date

from app.ingestion.legiscan_status import (
    TrackedBill,
    parse_number,
    plan_updates,
    should_move,
)
from app.ingestion.openstates import _canonical_doc_url, fix_dead_host

SESSION_2025 = {"session_id": 2172, "year_start": 2025, "year_end": 2026}


def _bill(**kw):
    return TrackedBill(
        id=kw.get("id", 1), state=kw.get("state", "CA"), bill_number=kw.get("num", "AB-864"),
        title=kw.get("title", "Hazardous waste: solar photovoltaic modules."),
        status=kw.get("status", "introduced"),
        last_action_date=kw.get("lad", date(2026, 2, 1)),
        legiscan_bill_id=kw.get("lid"),
    )


def _item(**kw):
    return {
        "bill_id": kw.get("bill_id", 1976451), "number": kw.get("number", "AB864"),
        "title": kw.get("title", "Hazardous waste: solar photovoltaic modules."),
        "description": kw.get("description", "An act to amend Section 25259."),
        "status": kw.get("status", 4), "status_date": kw.get("status_date", "2026-09-30"),
        "last_action_date": kw.get("last_action_date", "2026-09-30"),
        "last_action": "Chaptered by Secretary of State - Chapter 872, Statutes of 2026.",
    }


class TestParseNumber:
    def test_formats(self):
        assert parse_number("AB-864") == ("AB", None, 864)
        assert parse_number("AB864") == ("AB", None, 864)
        assert parse_number("HB-25-1059") == ("HB", 25, 1059)   # CO
        assert parse_number("B-24-0534") == ("B", 24, 534)      # DC
        assert parse_number("B24-0534") == ("B", 24, 534)       # DC, LegiScan form
        assert parse_number("H.B.-27") == ("HB", None, 27)      # UT
        assert parse_number("H0204") == ("H", None, 204)        # VT, LegiScan zero-pads
        assert parse_number("") is None


class TestShouldMove:
    def test_forward_only(self):
        assert should_move("introduced", "enacted")
        assert should_move("in_committee", "passed_chamber")
        assert not should_move("passed_chamber", "introduced")
        assert not should_move("in_committee", "introduced")

    def test_enacted_is_final(self):
        assert not should_move("enacted", "failed")
        assert not should_move("enacted", "vetoed")

    def test_terminal_from_open(self):
        assert should_move("in_committee", "failed")
        assert should_move("introduced", "vetoed")
        assert not should_move("failed", "passed_chamber")
        assert should_move("vetoed", "enacted")  # veto override


class TestPlanUpdates:
    def test_ab864_enacted(self):
        ups, counts = plan_updates([_bill()], {"0": _item()}, SESSION_2025)
        assert counts["matched"] == 1
        (u,) = ups
        assert u.new_status == "enacted"
        assert u.status_date == date(2026, 9, 30)
        assert u.legiscan_bill_id == 1976451

    def test_reused_number_in_other_session_is_rejected(self):
        # A 2023 AB-864 must not pick up the 2025-26 AB-864's status.
        ups, counts = plan_updates([_bill(lad=date(2023, 6, 1))], {"0": _item()}, SESSION_2025)
        assert ups == [] and counts["year_mismatch"] == 1

    def test_title_mismatch_is_rejected(self):
        item = _item(title="Us President Elect. Popular Vote Compact", description="Elections.")
        ups, counts = plan_updates([_bill()], {"0": item}, SESSION_2025)
        assert ups == [] and counts["title_mismatch"] == 1

    def test_description_overlap_counts(self):
        item = _item(title="Something else entirely", description=_bill().title)
        ups, _ = plan_updates([_bill()], {"0": item}, SESSION_2025)
        assert len(ups) == 1

    def test_prefile_year_needs_strong_title(self):
        prefile = _bill(lad=date(2024, 12, 2))
        assert len(plan_updates([prefile], {"0": _item()}, SESSION_2025)[0]) == 1
        weak = _item(title="Hazardous waste: batteries and other modules.", description="")
        assert plan_updates([prefile], {"0": weak}, SESSION_2025)[0] == []

    def test_co_year_in_number_must_match_session(self):
        b = _bill(state="CO", num="HB-20-1195", lad=date(2026, 1, 1))
        ups, counts = plan_updates([b], {"0": _item(number="HB1195")}, SESSION_2025)
        assert ups == [] and counts["year_mismatch"] == 1

    def test_older_legiscan_record_is_ignored(self):
        b = _bill(lad=date(2026, 10, 15))
        ups, counts = plan_updates([b], {"0": _item()}, SESSION_2025)
        assert ups == [] and counts["older_than_ours"] == 1

    def test_adopted_resolution_is_passed_not_enacted(self):
        b = _bill(num="HR-184", title="Requesting a study of reuse programs.")
        item = _item(number="HR184", title="Requesting a study of reuse programs.")
        (u,) = plan_updates([b], {"0": item}, SESSION_2025)[0]
        assert u.new_status == "passed"

    def test_unchanged_status_still_stores_id(self):
        b = _bill(status="enacted", lad=date(2026, 9, 30))
        (u,) = plan_updates([b], {"0": _item()}, SESSION_2025)[0]
        assert u.new_status is None and u.legiscan_bill_id == 1976451


class TestDeadHosts:
    def test_beta_ilga_rewritten(self):
        url = "https://beta.ilga.gov/Legislation/BillStatus?DocNum=2153&GAID=17&DocTypeID=HB"
        assert fix_dead_host(url) == url.replace("beta.ilga.gov", "www.ilga.gov")
        assert _canonical_doc_url(url).startswith("https://www.ilga.gov/")

    def test_other_hosts_untouched(self):
        assert fix_dead_host("https://www.njleg.state.nj.us/x") == "https://www.njleg.state.nj.us/x"
