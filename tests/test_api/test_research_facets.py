"""Pure-function guards for research retrieval term extraction.

Regression coverage for the remanufacturing divergence (2026-07-20): the same topic asked three ways
matched 3 / 44 / 174 bills purely because query-framing words that survived the stopword filter got
AND-ed into websearch_to_tsquery and intersected the real subject word down. `meaningful_terms()` must
strip those framing words so the tsquery stays on the subject. No DB needed — this is string logic.
"""
from app.api.research_facets import Facets


def _facets(free_text: str) -> Facets:
    return Facets(
        place_ids=[], place_labels=[], reference_labels=[],
        material_slugs=[], material_labels=[], instrument_slugs=[], instrument_labels=[],
        product_slugs=[], product_labels=[], free_text=free_text, raw_question=free_text,
    )


def test_framing_nouns_are_stripped():
    # "What does the whole database of bills have on the topic of remanufacturing?" (place/material
    # resolution removes nothing here, so free_text == question). Only the SUBJECT should survive.
    terms = _facets("What does the whole database of bills have on the topic of remanufacturing?").meaningful_terms()
    assert terms == ["remanufacturing"], terms
    # None of the query-chrome words may leak into the tsquery (each would AND-poison the match).
    for chrome in ("whole", "topic", "database", "reference", "references", "corpus", "overall"):
        assert chrome not in terms


def test_reference_and_corpus_framing_stripped():
    terms = _facets(
        "Are there any references to remanufacturing across the whole corpus?"
    ).meaningful_terms()
    assert terms == ["remanufacturing"], terms


def test_real_subject_words_survive():
    # Guard against over-stripping: genuine topic nouns must remain so retrieval still has a subject.
    terms = _facets("recycled content thresholds for plastic packaging").meaningful_terms()
    assert "recycled" in terms and "content" in terms and "thresholds" in terms
