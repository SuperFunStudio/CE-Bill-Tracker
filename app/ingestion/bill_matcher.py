"""
Bill-to-litigation case matching.

Links LitigationCase records to Bill records by combining:
  1. State inference from court_id (hard filter — must match)
  2. Token overlap between case text and bill title/number/description
  3. Known EPR law keyword aliases (e.g. "SB 54" → CA, "WRAP Act" → OR)

Returns the best-matching bill ID and match confidence (0.0–1.0).
Only accepts matches >= MIN_CONFIDENCE (0.35 by default) to avoid false links.

Usage:
    from app.ingestion.bill_matcher import match_case_to_bill
    bill_id, state, confidence = await match_case_to_bill(db, case)
"""

import re
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

MIN_CONFIDENCE = 0.35

# Map court_id prefixes to US state codes.
# Federal district courts are named by state; we extract state from them.
COURT_STATE_MAP: dict[str, str] = {
    # California
    "cacd": "CA", "cand": "CA", "caed": "CA", "casd": "CA",
    # Oregon
    "ord": "OR",
    # Washington
    "wawd": "WA", "wad": "WA", "waed": "WA",
    # Maine
    "med": "ME",
    # Minnesota
    "mnd": "MN",
    # Colorado
    "cod": "CO",
    # New York
    "nyd": "NY", "nynd": "NY", "nyed": "NY", "nysd": "NY",
    # Maryland
    "mdd": "MD",
    # New Jersey
    "njd": "NJ",
    # Connecticut
    "ctd": "CT",
    # Illinois
    "ilnd": "IL", "ilcd": "IL", "ilsd": "IL",
    # Texas
    "txnd": "TX", "txsd": "TX", "txed": "TX", "txwd": "TX",
    # Virginia
    "vaed": "VA", "vawd": "VA",
    # DC (treat as federal/US)
    "dcd": "US",
}

# Known EPR laws / bill aliases → (state, keywords that appear in case names/descriptions)
# Add entries as new bills are enacted. Keywords are lowercased.
EPR_LAW_ALIASES: list[tuple[str, list[str]]] = [
    # California
    ("CA", ["sb 54", "sb54", "plastic pollution prevention", "california plastic"]),
    ("CA", ["ab 1201", "ab1201", "california packaging"]),
    ("CA", ["sb 1383", "sb1383", "short-lived climate pollutants", "california organics"]),
    # Oregon
    ("OR", ["sb 543", "sb543", "oregon packaging", "oregon epr", "wrap act", "oregon recycling"]),
    ("OR", ["hb 2200", "hb2200"]),
    # Colorado
    ("CO", ["sb 22-253", "colorado epr", "producer responsibility program", "colorado packaging"]),
    # Maine
    ("ME", ["sp 532", "maine epr", "maine packaging", "maine producer responsibility"]),
    # Minnesota
    ("MN", ["sf 3", "mn epr", "minnesota packaging", "minnesota producer responsibility"]),
    # Washington
    ("WA", ["essb 5154", "washington packaging", "washington epr"]),
    # Maryland
    ("MD", ["hb 700", "maryland packaging", "maryland epr"]),
    # New Jersey
    ("NJ", ["a 4454", "new jersey packaging", "new jersey epr"]),
    # Connecticut
    ("CT", ["hb 5004", "connecticut packaging", "connecticut epr"]),
    # Federal
    ("US", ["pack act", "packaging accountability", "federal epr", "federal preemption"]),
]


def infer_state_from_court(court_id: str) -> Optional[str]:
    """Return 2-char state code from a CourtListener court_id, or None."""
    if not court_id:
        return None
    return COURT_STATE_MAP.get(court_id.lower())


def _tokenize(text: str) -> set[str]:
    """Lowercase alpha-numeric tokens, length >= 2, excluding stop words."""
    _STOP = {
        "the", "of", "in", "for", "and", "to", "a", "an", "is", "by", "or",
        "on", "at", "v", "vs", "et", "al", "inc", "llc", "corp",
    }
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    return tokens - _STOP


def _bill_tokens(bill) -> set[str]:
    """Build a token set from all searchable bill fields."""
    parts = [
        bill.bill_number or "",
        bill.title or "",
        bill.description or "",
    ]
    return _tokenize(" ".join(parts))


def _case_tokens(case_name: str, cause: str = "") -> set[str]:
    return _tokenize(f"{case_name} {cause}")


def score_token_overlap(case_tokens: set[str], bill_tokens: set[str]) -> float:
    """Jaccard-style overlap — intersection / min(|A|, |B|) to reward specificity."""
    if not case_tokens or not bill_tokens:
        return 0.0
    intersection = len(case_tokens & bill_tokens)
    return intersection / min(len(case_tokens), len(bill_tokens))


def alias_bonus(state: str, case_text: str) -> float:
    """Return +0.5 if any known EPR alias for the state appears in case_text."""
    text_lower = case_text.lower()
    for alias_state, keywords in EPR_LAW_ALIASES:
        if alias_state != state:
            continue
        if any(kw in text_lower for kw in keywords):
            return 0.5
    return 0.0


async def match_case_to_bill(
    db: AsyncSession,
    case,  # LitigationCase ORM instance
    cause: str = "",
    min_confidence: float = MIN_CONFIDENCE,
) -> tuple[Optional[int], Optional[str], float]:
    """Find the best-matching Bill for a LitigationCase.

    Returns (bill_id, state_code, confidence).
    Returns (None, inferred_state, 0.0) when no bill clears min_confidence.

    Steps:
      1. Infer state from court_id.
      2. Load all ce_relevant bills for that state.
      3. Score each bill by token overlap + alias bonus.
      4. Return best match above threshold.
    """
    from app.models import Bill

    state = infer_state_from_court(getattr(case, "court_id", "") or "")

    # Also check if the case itself already has a related_state hint
    if not state and getattr(case, "related_state", None):
        state = case.related_state

    if not state:
        log.debug("bill_matcher_no_state", case_name=case.case_name, court_id=case.court_id)
        return None, None, 0.0

    # Load candidate bills for this state (only EPR-relevant)
    result = await db.execute(
        select(Bill).where(
            Bill.state == state,
            Bill.ce_relevant == True,  # noqa: E712
        )
    )
    candidates = result.scalars().all()

    if not candidates:
        log.debug("bill_matcher_no_candidates", state=state, case_name=case.case_name)
        return None, state, 0.0

    case_text = f"{case.case_name} {cause}"
    case_tok = _case_tokens(case.case_name, cause)

    best_bill_id: Optional[int] = None
    best_score = 0.0

    for bill in candidates:
        bill_tok = _bill_tokens(bill)
        overlap = score_token_overlap(case_tok, bill_tok)
        bonus = alias_bonus(state, case_text)
        # Bill number exact-match is a strong signal
        bill_num = (bill.bill_number or "").lower().replace(" ", "")
        case_text_compact = case_text.lower().replace(" ", "")
        num_hit = 0.4 if bill_num and bill_num in case_text_compact else 0.0

        score = min(1.0, overlap + bonus + num_hit)

        log.debug(
            "bill_matcher_score",
            bill_id=bill.id,
            bill_number=bill.bill_number,
            overlap=round(overlap, 3),
            bonus=bonus,
            num_hit=num_hit,
            score=round(score, 3),
        )

        if score > best_score:
            best_score = score
            best_bill_id = bill.id

    if best_score < min_confidence:
        log.info(
            "bill_matcher_no_match",
            case_name=case.case_name,
            state=state,
            best_score=round(best_score, 3),
        )
        return None, state, best_score

    log.info(
        "bill_matcher_matched",
        case_name=case.case_name,
        state=state,
        bill_id=best_bill_id,
        confidence=round(best_score, 3),
    )
    return best_bill_id, state, best_score


async def run_bill_matching_pass(db: AsyncSession) -> dict:
    """Match all unlinked litigation cases to bills in a single pass.

    Intended for: seed script post-processing, nightly reconciliation job.
    Returns summary dict: {matched, already_linked, no_state, no_match, errors}.
    """
    from app.models import LitigationCase

    result = await db.execute(select(LitigationCase))
    cases = result.scalars().all()

    stats = {"matched": 0, "already_linked": 0, "no_state": 0, "no_match": 0, "errors": 0}

    for case in cases:
        try:
            if case.related_law_id is not None:
                stats["already_linked"] += 1
                continue

            bill_id, state, confidence = await match_case_to_bill(db, case)

            # Always persist the inferred state even if no bill matched
            if state and case.related_state != state:
                case.related_state = state

            if bill_id is not None:
                case.related_law_id = bill_id
                stats["matched"] += 1
            elif state is None:
                stats["no_state"] += 1
            else:
                stats["no_match"] += 1

        except Exception as e:
            log.error("bill_matcher_case_error", case_id=case.id, error=str(e))
            stats["errors"] += 1

    await db.commit()
    log.info("bill_matching_pass_complete", **stats)
    return stats
