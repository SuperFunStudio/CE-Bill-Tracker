"""The blanket-scope gate: which "covers the whole class" clauses may expand the catalog.

Cases are real prod excerpts from the 2026-08-18 audit of blanket expansion, which found that
61% of bill_product_coverage came from the deterministic expander and ~1 in 6 clusters over-reached.
The load-bearing property is the LAST test: a gate tight enough to catch fragments and closed lists
must not reject genuine WEEE / right-to-repair class definitions, which are most of the corpus.
"""
from app.synthesis.product_coverage import classify_blanket_scope

# OR HB-3220 — "covered electronic device" is a CLOSED (A)-(H) list. The expander previously added
# cameras, game consoles, e-readers and wearables off this, none of which appear in it.
ENUMERATED = (
    '"Covered electronic device" means: (A) A computer monitor of any type having a viewable area '
    "greater than four inches measured diagonally; (B) A desktop computer or portable computer; "
    "(C) A television; (D) A peripheral; (E) A printer; (F) A facsimile machine; (G) A "
    "videocassette recorder; (H) A portable digital music player"
)
# RI H7180 — a real blanket definition. Note it also uses lettered sub-clauses in other bills, but
# for conjunctive TESTS rather than device names, which is what separates it from ENUMERATED.
CLASS_DEFN = (
    '"Digital electronic equipment" or "equipment" means any product that depends for its '
    "functioning, in whole or in part, on digital electronics embedded in or attached to the product."
)
PREDICATE_SUBCLAUSES = (
    '"Consumer Electronic Device" or "device" means any product or electronic that: (a) Depends, in '
    "whole or in part, on digital electronics, such as a microprocessor or microcontroller, embedded "
    "in or attached to the product in order to function; (b) Is tangible personal property; (c) Is "
    "generally used for personal, family, or household purposes"
)


def test_closed_enumerated_list_does_not_expand():
    may_expand, _conf, reason = classify_blanket_scope(ENUMERATED)
    assert may_expand is False
    assert reason == "enumerated"


def test_predicate_subclauses_are_not_an_enumerated_list():
    """(a)(b)(c) conjunctive tests must still expand — enumeration markers alone can't gate."""
    may_expand, conf, reason = classify_blanket_scope(PREDICATE_SUBCLAUSES)
    assert may_expand is True
    assert conf == 0.7
    assert reason == "class_definition"


def test_thin_excerpt_expands_but_is_demoted():
    """A title fragment is kept (absence would be indistinguishable from 'never extracted') but
    must not carry the same confidence as a real definition. Real prod cases: UK nisr/2014/202
    expanded 15 products off this string; NY S-2906 expanded 7 battery products off 30 chars."""
    for fragment in ("Waste Electrical and Electronic Equipment (WEEE)",
                     "rechargeable battery recycling",
                     "Electronic devices"):
        may_expand, conf, reason = classify_blanket_scope(fragment)
        assert may_expand is True, fragment
        assert conf == 0.35, fragment
        assert reason == "thin_excerpt", fragment


def test_genuine_class_definitions_are_never_rejected():
    """The safety property. These are the expansions that make the electronics corpus useful —
    a gate that demotes or blocks any of them is worse than no gate."""
    sound = [
        CLASS_DEFN,
        PREDICATE_SUBCLAUSES,
        # NL Regeling AEEA — WEEE equipment definition
        "elektrische en elektronische apparatuur: apparaten die afhankelijk zijn van elektrische "
        "stromen of elektromagnetische velden om naar behoren te werken en apparaten voor het "
        "opwekken, overbrengen en meten van die stromen en velden",
        # PL ustawa o zużytym sprzęcie — same WEEE definition in Polish
        "sprzęt - urządzenie, którego prawidłowe działanie jest uzależnione od dopływu prądu "
        "elektrycznego lub od obecności pól elektromagnetycznych oraz mogące służyć do wytwarzania, "
        "przesyłu lub pomiaru prądu elektrycznego",
        # CT HB-6512 — consumer-electronics class definition
        "Consumer electronics - digital electronic products originally manufactured for "
        "distribution and sale primarily to consumers",
    ]
    for clause in sound:
        may_expand, conf, reason = classify_blanket_scope(clause)
        assert may_expand is True, clause[:60]
        assert conf == 0.7, clause[:60]
        assert reason == "class_definition", clause[:60]
