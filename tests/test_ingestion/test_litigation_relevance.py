"""The relevance gate between CourtListener's search and a subscriber's inbox.

Every case here is a real production row. `litigation_cases` held 34 tracked cases; 33 of them were
unrelated federal litigation that CourtListener returned because a phrase appeared somewhere in a
filed PDF, and each one was alerted on under the subject "EPR Litigation Update: <case>". The one
true positive is NAWD v. Ryan — and it is docketed as "42:1983 Civil Rights Act", which is why the
gate has to read the complaint rather than the metadata.
"""
import pytest

from app.ingestion.courtlistener import EPR_LITIGATION_QUERIES
from app.ingestion.litigation_relevance import (
    SOURCE_KEYWORD,
    SOURCE_NO_SIGNAL,
    assess_relevance,
    build_evidence,
    pick_primary_document_id,
)


class TestSeedQueries:
    """CourtListener's Elasticsearch binds OR tighter than the surrounding terms, so
    `"PACK Act" OR "Packaging Act" preemption` means "any docket saying PACK Act" — 612 of them,
    including GLP-1 products liability and a police-department suit."""

    def test_no_or_arm_is_left_unparenthesized(self):
        for name, query in EPR_LITIGATION_QUERIES:
            if " OR " in query:
                assert "(" in query and ")" in query, f"{name}: unparenthesized OR — {query}"

    def test_every_term_is_a_quoted_phrase(self):
        """A bare token outside quotes is a one-word match against the full text of every filed
        exhibit. That is what pulled in BelAir Electronics v. Google on the word 'electronics'."""
        for name, query in EPR_LITIGATION_QUERIES:
            stripped = query.replace("(", " ").replace(")", " ")
            # Remove quoted phrases, then the boolean operators; nothing may remain.
            without_phrases = __import__("re").sub(r'"[^"]+"', " ", stripped)
            leftovers = [
                tok for tok in without_phrases.split() if tok not in {"AND", "OR", "NOT"}
            ]
            assert not leftovers, f"{name}: unquoted term(s) {leftovers} in {query}"


class TestStrongSignal:
    @pytest.mark.asyncio
    async def test_complaint_text_clears_a_case_its_metadata_hides(self):
        """NAWD v. Ryan (D. Colo.) challenges Colorado's packaging EPR program. Its cause is
        '42:1983 Civil Rights Act', its nature of suit is '440 Civil Rights: Other', and its docket
        entries are attorney appearances — the subject matter exists only in the complaint."""
        evidence = build_evidence(
            case_name="National Association of Wholesaler-Distributors v. Ryan",
            cause="42:1983 Civil Rights Act",
            nature_of_suit="440 Civil Rights: Other",
            party_names=["National Association of Wholesaler-Distributors", "Jill Hunsaker Ryan"],
            entry_descriptions=["NOTICE of Entry of Appearance by Pawan Nelson on behalf of ..."],
            document_text=(
                "COMPLAINT FOR DECLARATORY AND INJUNCTIVE RELIEF. Colorado's Producer "
                "Responsibility Program for Statewide Recycling imposes an extended producer "
                "responsibility scheme on packaging."
            ),
        )
        verdict = await assess_relevance(evidence)
        assert verdict.relevant is True
        assert verdict.source == SOURCE_KEYWORD

    @pytest.mark.asyncio
    async def test_metadata_alone_does_not_clear_it(self):
        """The same case without its complaint is indistinguishable from noise — so the gate must
        not pass it. This is why re-screening the existing backlog needs --mode fetch to rescue
        true positives, and why an unreadable docket is held rather than alerted on."""
        verdict = await assess_relevance(
            build_evidence(
                case_name="National Association of Wholesaler-Distributors v. Ryan",
                cause="42:1983 Civil Rights Act",
                nature_of_suit="440 Civil Rights: Other",
            )
        )
        assert verdict.relevant is False


class TestProductionFalsePositives:
    """Each of these was a live `litigation_cases` row that emailed subscribers."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "case_name,cause,nature_of_suit,entry",
        [
            (
                "United States v. State of Maryland",
                "28:1331 Constitutionality of State Statutes",
                "950 Constitutional - State Statute",
                "MOTION to Dismiss for Failure to State a Claim by Anthony Brown, State of Maryland",
            ),
            ("DAVIS v. PFIZER INC", "28:1332 Diversity-Product Liability", "365 Personal Inj. Prod. Liability", "COMPLAINT"),
            ("DRAFTKINGS INC. v. THE CITY OF PHILADELPHIA", "28:1331 Fed. Question", "190 Contract: Other", "NOTICE of Appearance"),
            ("KENNEDY v. NOVO NORDISK INC.", "28:1332 Diversity", "365 Personal Inj. Prod. Liability", "COMPLAINT"),
            (
                "American Outlaws Association d/b/a The Outlaws Motorcycle Club, Inc. v. Cekada",
                "42:1983 Civil Rights Act",
                "440 Civil Rights: Other",
                "COMPLAINT filed",
            ),
        ],
    )
    async def test_rejected_without_spending_a_classifier_call(
        self, case_name, cause, nature_of_suit, entry
    ):
        verdict = await assess_relevance(
            build_evidence(
                case_name=case_name,
                cause=cause,
                nature_of_suit=nature_of_suit,
                entry_descriptions=[entry],
            )
        )
        assert verdict.relevant is False
        # SOURCE_NO_SIGNAL means the decision cost nothing: no docket text, no Haiku call. The old
        # pipeline paid for a per-entry classification and a Sonnet risk score on every one of these.
        assert verdict.source == SOURCE_NO_SIGNAL


class TestWeakSignalFloor:
    @pytest.mark.asyncio
    async def test_single_passing_mention_is_not_a_case(self):
        """A products-liability complaint that mentions packaging once is not circular-economy
        litigation, and must not reach the classifier — or the inbox."""
        verdict = await assess_relevance(
            build_evidence(
                case_name="Pinckney v. The Stop & Shop Supermarket Company LLC",
                cause="28:1332 Diversity-Personal Injury",
                document_text="Plaintiff slipped on a torn packaging film in aisle six.",
            )
        )
        assert verdict.relevant is False
        assert verdict.source == SOURCE_NO_SIGNAL

    @pytest.mark.asyncio
    async def test_repeated_weak_vocabulary_escalates_rather_than_passing(self, monkeypatch):
        """Sustained recycling/waste vocabulary with no dispositive phrase is the ambiguous middle:
        it must not pass on keywords alone. With no classifier configured it stays excluded, but
        flagged for review rather than silently dropped."""
        from app.config import settings

        monkeypatch.setattr(settings, "enable_llm_classification", False)
        verdict = await assess_relevance(
            build_evidence(
                case_name="Texas Regional Landfill Co L P v. Shreveport",
                document_text=(
                    "The recycling contract governs solid waste collection. The recycling "
                    "facility accepts recyclable material under the solid waste ordinance."
                ),
            )
        )
        assert verdict.relevant is False
        assert verdict.needs_review is True


class TestDocumentSelection:
    def test_prefers_the_complaint_over_later_filings(self):
        """The complaint states what law is challenged; a scheduling order does not."""
        result = {
            "recap_documents": [
                {"id": 900, "is_available": True, "entry_number": 7, "short_description": "Order"},
                {"id": 100, "is_available": True, "entry_number": 1, "short_description": "Complaint"},
            ]
        }
        assert pick_primary_document_id(result, None) == 100

    def test_ignores_unavailable_documents(self):
        """RECAP knows about documents it doesn't hold; fetching one returns nothing."""
        result = {"recap_documents": [{"id": 1, "is_available": False, "short_description": "Complaint"}]}
        assert pick_primary_document_id(result, None) is None

    def test_falls_back_to_the_earliest_available_filing(self):
        entries = [
            {"recap_documents": [{"id": 5, "is_available": True, "entry_number": 4}]},
            {"recap_documents": [{"id": 2, "is_available": True, "entry_number": 2}]},
        ]
        assert pick_primary_document_id(None, entries) == 2


class TestEmptyEvidence:
    @pytest.mark.asyncio
    async def test_nothing_to_read_is_held_for_review_not_cleared(self):
        verdict = await assess_relevance("")
        assert verdict.relevant is False
        assert verdict.needs_review is True
