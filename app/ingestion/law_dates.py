"""Best-effort enactment-DATE derivation for curated foreign / EU laws — the single source of truth.

Foreign & EU source adapters rarely expose a clean status_date, but the enactment YEAR is almost always
recoverable from the law's identifier (a CELEX id encodes it) or its official title ("…Act 2002"). This
module centralizes that derivation so it is applied CONSISTENTLY by:
  - the forward ingest path — app/ingestion/foreign.sync_foreign + eurlex.sync_eurlex — so every newly
    ingested foreign/EU law (incl. future regions) lands with a status_date; and
  - the one-time scripts/backfill_foreign_dates.py — so backfilled and freshly-ingested dates AGREE.

We store the derived value as status_date = Jan 1 of the year (year-only precision) and leave
last_action_date NULL: the UI renders last_action_date as a precise date, while status_date only buckets
year charts, so a Jan-1 status_date is an honest representation of a year-only signal. An adapter that
obtains a REAL, precise date should set it explicitly (ForeignLaw.status_date) to override this fallback.

See memory foreign-bill-dates.
"""
from __future__ import annotations

import datetime
import re

# Below this a 4-digit token is not a plausible modern statute year (and blocks e.g. "1055/2022" -> 1055).
MIN_LAW_YEAR = 1950

# EU CELEX: sector digit + 4-digit year + document-type letter — 32023R1542 -> 2023. Specific enough
# that it does not false-match observed non-EU ids (JP "424AC…", AU "C2004A…", "2015/366" all fail it).
_CELEX_YEAR_RE = re.compile(r"^\d(\d{4})[A-Z]")
# A standalone 4-digit token (word-bounded so it won't match inside a longer number).
_YEAR_TOKEN_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def _current_year() -> int:
    return datetime.date.today().year


def derive_law_year(
    source_id: str | None, title: str | None, *, max_year: int | None = None
) -> tuple[int, str] | None:
    """Return (year, basis) where basis is 'celex' | 'title' | 'source_id', or None if nothing derivable.

    Priority: CELEX id year -> first in-range 4-digit token in the title (the name/enactment year) ->
    first in-range token in the id. Range-guarded to [MIN_LAW_YEAR, max_year] so a future TARGET year
    ("…by 2035") can never win; title/id scanning takes the FIRST in-range token because the enactment
    year normally precedes any target year in a statute's name. `basis` feeds the backfill's report; the
    ingest path only needs the year.
    """
    max_year = max_year or _current_year()

    def _ok(y: int) -> bool:
        return MIN_LAW_YEAR <= y <= max_year

    sid = (source_id or "").strip()
    m = _CELEX_YEAR_RE.match(sid)
    if m and _ok(int(m.group(1))):
        return int(m.group(1)), "celex"
    for text, basis in ((title, "title"), (sid, "source_id")):
        for mm in _YEAR_TOKEN_RE.finditer(text or ""):
            y = int(mm.group(1))
            if _ok(y):
                return y, basis
    return None


def derive_status_date(
    source_id: str | None, title: str | None, *, max_year: int | None = None
) -> datetime.date | None:
    """The derived enactment date (Jan 1 of the derived year), or None. What the ingest path stores."""
    got = derive_law_year(source_id, title, max_year=max_year)
    return datetime.date(got[0], 1, 1) if got else None
