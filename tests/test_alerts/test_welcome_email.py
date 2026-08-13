"""Welcome email: the catch-up template.

Pinned here are the things that would quietly go wrong and still render: counts taken after the
display truncation (so "top 8 of 8"), a breakdown whose rows don't sum to the headline, a hardcoded
corpus size that goes stale, and the studio byline creeping back into the masthead.
"""
import types
from datetime import date

from app.config import settings
from app.alerts.welcome_email import (
    CorpusStats,
    StandingRow,
    StateOfPlay,
    render_welcome_html,
    render_welcome_preheader,
    render_welcome_subject,
)


def _sub(**kw):
    return types.SimpleNamespace(
        id=kw.get("id", 42),
        email=kw.get("email", "a@example.com"),
        organization=kw.get("organization", "Superfun Studio"),
        states=kw.get("states", ["CA", "OR"]),
        instrument_types=kw.get("instrument_types", ["epr"]),
        material_categories=kw.get("material_categories", ["packaging"]),
        region_scope=None,
        scope="filter",
        firebase_uid=None,
        min_confidence=0.0,
        alert_on=["new_bill"],
    )


def _bill(**kw):
    return types.SimpleNamespace(
        id=kw.get("id", 1),
        state=kw.get("state", "CA"),
        bill_number=kw.get("bill_number", "SB 54"),
        title=kw.get("title", "Plastic Pollution Producer Responsibility Act"),
        status=kw.get("status", "enacted"),
        instrument_type=kw.get("instrument_type", "epr"),
        material_categories=["packaging"],
        confidence_score=0.9,
        ai_summary=None,
        last_action_date=kw.get("last_action_date", date(2026, 6, 12)),
        status_date=kw.get("status_date", date(2026, 6, 12)),
        region="US",
    )


def _sop(**kw):
    return StateOfPlay(
        scope_total=kw.get("scope_total", 50),
        enacted_recent=kw.get("enacted_recent", 12),
        active_recent=kw.get("active_recent", 41),
        by_state=kw.get("by_state", [StandingRow("CA", 3, 9), StandingRow("OR", 1, 4)]),
        by_topic=kw.get("by_topic", [StandingRow("EPR", 8, 30), StandingRow("Repair", 1, 5)]),
        recent_enacted=kw.get("recent_enacted", [_bill()]),
        recent_movement=kw.get("recent_movement", [_bill(id=2, status="in_committee")]),
        topic_count=kw.get("topic_count", 2),
        jurisdiction_count=kw.get("jurisdiction_count", 14),
        other_jurisdictions=kw.get("other_jurisdictions", StandingRow("12 others", 2, 20)),
        on_the_books_total=kw.get("on_the_books_total", 7),
    )


CORPUS = CorpusStats(
    total_bills=2544, enacted_laws=1178, regions=37, year_bills=368, year=2026
)
WINDOW = (date(2026, 2, 1), date(2026, 8, 1))


class TestSubject:
    def test_leads_with_the_enacted_count(self):
        s = render_welcome_subject(_sop(), WINDOW[0])
        assert s == "12 laws enacted in your scope since 1 February 2026"

    def test_singular(self):
        assert render_welcome_subject(_sop(enacted_recent=1), WINDOW[0]).startswith("1 law enacted")

    def test_falls_back_to_movement_rather_than_boasting_a_zero(self):
        s = render_welcome_subject(_sop(enacted_recent=0), WINDOW[0])
        assert s.startswith("41 bills moving")

    def test_empty_scope_gets_neither_number(self):
        s = render_welcome_subject(_sop(enacted_recent=0, active_recent=0), WINDOW[0])
        assert "0" not in s


class TestCorpusStatsAreLive:
    def test_letter_quotes_the_computed_numbers(self):
        """The corpus grows weekly — a hardcoded total in a welcome email is the first thing a
        careful reader catches."""
        html = render_welcome_html(_sub(), _sop(), "August 2026", corpus=CORPUS, window=WINDOW)
        assert "1,178 enacted laws" in html
        assert "37 jurisdictions" in html
        assert "368 bills have already moved in 2026" in html

    def test_letter_is_omitted_when_stats_are_unavailable(self):
        """Better no paragraph than one claiming the Atlas holds zero laws."""
        html = render_welcome_html(_sub(), _sop(), "August 2026")
        # Probe a letter-only phrase: "enacted laws" also appears in the tables' "Showing N of M"
        # lines, so it can't distinguish the letter's presence.
        assert "inflection point" not in html
        assert "Glad you're here" not in html

    def test_asks_the_discovery_question(self):
        # The reply prompt is the point of the letter — it's the only customer-research channel in
        # the whole funnel.
        html = render_welcome_html(_sub(), _sop(), "August 2026", corpus=CORPUS, window=WINDOW)
        assert "what are you tracking by hand right now" in html


class TestBreakdownsAddUp:
    def test_jurisdiction_tail_is_rolled_up_not_dropped(self):
        html = render_welcome_html(_sub(), _sop(), "August 2026", corpus=CORPUS, window=WINDOW)
        assert "top 2 of 14" in html
        assert "12 others" in html

    def test_all_jurisdictions_shown_says_so(self):
        html = render_welcome_html(
            _sub(), _sop(jurisdiction_count=2, other_jurisdictions=None), "August 2026"
        )
        assert "all 2" in html

    def test_truncated_tables_declare_the_truncation(self):
        """A 6-row table under a headline of 41 must say it's showing 6 — otherwise the reader takes
        the table for the whole set."""
        html = render_welcome_html(_sub(), _sop(), "August 2026", corpus=CORPUS, window=WINDOW)
        assert "Showing 1 of 41 advancing bills" in html
        assert "Showing 1 of 12 enacted laws" in html


class TestChromeAndCopy:
    def test_sets_expectations_about_the_alerts_sender(self):
        """Naming the address the ongoing alerts will come from is both courtesy and a
        deliverability nudge ("add us to your contacts").

        It reads the address from settings rather than a literal: the welcome used to promise mail
        from alerts@ while every send moved to one identity, which made the copy quietly false. A
        hard-coded address here is a promise nothing enforces."""
        html = render_welcome_html(_sub(), _sop(), "August 2026", corpus=CORPUS, window=WINDOW)
        assert settings.email_from in html

    def test_links_the_substack(self):
        html = render_welcome_html(_sub(), _sop(), "August 2026", corpus=CORPUS, window=WINDOW)
        assert "atlascircular.substack.com" in html

    def test_no_studio_byline(self):
        html = render_welcome_html(_sub(), _sop(), "August 2026", corpus=CORPUS, window=WINDOW)
        # The subscriber's own org name may legitimately appear; the masthead kicker must not.
        assert "SUPERFUN STUDIO · PRESENTS" not in html

    def test_states_the_catch_up_window(self):
        html = render_welcome_html(_sub(), _sop(), "August 2026", corpus=CORPUS, window=WINDOW)
        assert "1 February 2026 – 1 August 2026" in html

    def test_preheader_names_the_scope(self):
        assert "Extended Producer Responsibility" in render_welcome_preheader(_sub(), _sop())

    def test_undated_filings_are_an_aside_not_a_table(self):
        html = render_welcome_html(_sub(), _sop(), "August 2026", corpus=CORPUS, window=WINDOW)
        assert "7</strong> filings with no dated action" in html
