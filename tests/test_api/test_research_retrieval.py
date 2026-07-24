"""Pure-function guards for the RULE 1 -> RULE 2 (dimension) escalation decision.

Regression coverage for the remanufacturing divergence follow-up: a thin full-text match is escalated
to a compliance dimension's curated set ONLY for a bare "what does the corpus have on <topic>" ask —
never for a specific query that merely contains a dimension keyword (which would otherwise get swallowed
into the whole dimension, e.g. "civil penalty of $10,000 per day" -> all 639 penalty bills). The DB-bound
escalation lives in _relevant_bills; this covers the deterministic gate that governs it.
"""
from types import SimpleNamespace as NS

import app.api.research as research
from app.api.research import _balance_read_set, _dim_is_dominant


def test_bare_topic_is_dominant():
    # Only the dimension topic survives → escalation is the right, phrasing-independent answer.
    assert _dim_is_dominant(["remanufacturing"], "remanufactur") is True
    # A synonym trigger phrase whose tokens are the only terms is still bare.
    assert _dim_is_dominant(["industrial", "symbiosis"], "industrial symbiosis") is True


def test_specific_query_is_not_dominant():
    # Extra narrowing terms present → keep the precise text match; do NOT swallow into the dimension.
    assert _dim_is_dominant(["mention", "civil", "penalty", "000", "per", "day"], "penalt") is False
    assert _dim_is_dominant(["recycled", "content", "minimum", "percent"], "recycled content") is False


def test_no_trigger_is_not_dominant():
    assert _dim_is_dominant(["remanufacturing"], None) is False
    assert _dim_is_dominant([], "penalt") is True  # nothing left is trivially bare (n==0 guard fires upstream)


# --- Region-balanced deep read (relevance-gated) -----------------------------------------------------
# The deep-read set's English full-text ranking buries genuinely-relevant foreign law under US/EU volume.
# _balance_read_set reserves a slice of slots for under-represented COUNTRIES, but only for bills that
# clear a relevance floor — so buried-but-on-topic law surfaces while off-topic law never does. The pool
# arrives rank-ordered (the SQL ORDER BY rank DESC); these mimic that contract.

def _row(bill_id, rank, country):
    return NS(Bill=NS(id=bill_id), balance_rank=rank, balance_country=country)


def _ranked(rows):
    return sorted(rows, key=lambda r: (-r.balance_rank, r.Bill.id))  # mirrors the SQL ordering


def _ids(rows):
    return [r.Bill.id for r in rows]


def _standard_knobs(monkeypatch):
    monkeypatch.setattr(research, "_BALANCE_BUDGET", 0.30)
    monkeypatch.setattr(research, "_BALANCE_FLOOR_RATIO", 0.5)
    monkeypatch.setattr(research, "_BALANCE_PER_COUNTRY", 4)
    monkeypatch.setattr(research, "_BALANCE_CORE_TARGET", 2)


def test_balance_surfaces_buried_foreign_but_gates_off_topic(monkeypatch):
    # 7 US bills flood the core (weakest core rank 0.60 → floor 0.30). JP(0.45)/CN(0.42) clear the floor
    # and are promoted; KR(0.20) is below it and must NOT be — the overcompensation guard.
    _standard_knobs(monkeypatch)
    pool = _ranked([_row(i, 0.90 - 0.05 * i, "us") for i in range(7)]
                   + [_row(100, 0.45, "jp"), _row(101, 0.42, "cn"), _row(102, 0.20, "kr"),
                      _row(103, 0.55, "us"), _row(104, 0.50, "eu")])
    out = _ids(_balance_read_set(pool, 10))
    assert 100 in out and 101 in out           # buried-but-relevant foreign law surfaces
    assert 102 not in out                        # off-topic (below-floor) foreign law is rejected


def test_balance_no_qualifiers_is_pure_relevance(monkeypatch):
    # Every non-core candidate is either the core's own country (well-represented) or below the floor →
    # nothing qualifies → the set is byte-identical to pure relevance. No overcompensation, ever.
    _standard_knobs(monkeypatch)
    pool = _ranked([_row(i, 0.90 - 0.05 * i, "us") for i in range(7)]
                   + [_row(200, 0.10, "jp"), _row(201, 0.05, "cn"),
                      _row(202, 0.58, "us"), _row(203, 0.57, "us"), _row(204, 0.56, "us")])
    assert _ids(_balance_read_set(pool, 10)) == _ids(pool[:10])


def test_balance_per_country_cap(monkeypatch):
    # Ten above-floor JP bills can't monopolize the diversity budget — capped at _BALANCE_PER_COUNTRY.
    _standard_knobs(monkeypatch)
    pool = _ranked([_row(i, 0.90 - 0.05 * i, "us") for i in range(7)]
                   + [_row(300 + i, 0.45 - 0.001 * i, "jp") for i in range(10)])
    out = _balance_read_set(pool, 10)
    assert sum(1 for r in out if r.balance_country == "jp") <= research._BALANCE_PER_COUNTRY


def test_balance_keeps_set_full_via_relevance_backfill(monkeypatch):
    # One legit foreign promotion; the unused budget backfills with the next best pure-relevance bills,
    # so the read set never shrinks below page_size.
    _standard_knobs(monkeypatch)
    pool = _ranked([_row(i, 0.90 - 0.05 * i, "us") for i in range(7)]
                   + [_row(400, 0.45, "jp")] + [_row(410 + i, 0.44 - 0.01 * i, "us") for i in range(6)])
    out = _balance_read_set(pool, 10)
    assert len(out) == 10 and 400 in _ids(out)


def test_balance_forward_compatible_new_region(monkeypatch):
    # A brand-new region ('in') participates with zero code change (country is read from the path), and its
    # below-floor bill is still gated out. Pool padded so it exceeds page_size and balancing engages.
    _standard_knobs(monkeypatch)
    pool = _ranked([_row(i, 0.90 - 0.05 * i, "us") for i in range(7)]
                   + [_row(500, 0.44, "in"), _row(501, 0.15, "in")]
                   + [_row(510 + i, 0.58 - 0.01 * i, "us") for i in range(5)])
    out = _ids(_balance_read_set(pool, 10))
    assert 500 in out and 501 not in out


def test_balance_small_pool_unchanged(monkeypatch):
    _standard_knobs(monkeypatch)
    pool = _ranked([_row(i, 0.9 - 0.1 * i, "us") for i in range(5)])
    assert _balance_read_set(pool, 10) == pool
