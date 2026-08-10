"""Best-effort enactment-DATE derivation for curated foreign / EU laws — the single source of truth.

Foreign & EU source adapters rarely expose a clean status_date, but the enactment YEAR is almost always
recoverable from the law's identifier (a CELEX id encodes it) or its official title ("…Act 2002"). This
module centralizes that derivation so it is applied CONSISTENTLY by:
  - the forward ingest path — app/ingestion/foreign.sync_foreign + eurlex.sync_eurlex — so every newly
    ingested foreign/EU law (incl. future regions) lands with a status_date; and
  - the one-time scripts/backfill_foreign_dates.py — so backfilled and freshly-ingested dates AGREE.

Many official titles carry a FULL adoption date, not just a year, because the date is part of the law's
formal name: EU acts are always styled "… of 5 June 2019 on the reduction of …", and the same convention
holds in most civil-law jurisdictions ("Décret n° 2025-73 du 28 janvier 2025", "Ustawa z dnia 6 grudnia
2024 r.", "Verordnung vom 19. Dezember 2024"). So we look for a day-precision date in the title FIRST and
fall back to the year heuristics only when there isn't one. That matters beyond precision: for EU acts the
CELEX year is the OJ numbering year, which is NOT always the adoption year — CELEX 32025R0040 (the PPWR)
was adopted 19 December 2024, so the CELEX-year fallback dates it a year late and lands it in the wrong
bucket on every year chart. The title date is the authoritative signal wherever it exists.

We store a derived YEAR as status_date = Jan 1 (year-only precision) and leave last_action_date NULL: the
UI renders last_action_date as a precise date, while status_date only buckets year charts, so a Jan-1
status_date is an honest representation of a year-only signal (Bill.date_precision keys off exactly that,
so a title-derived precise date automatically starts rendering as day precision). An adapter that obtains
a REAL, precise date should set it explicitly (ForeignLaw.status_date) to override this fallback.

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

# Month names across the corpus's languages, including the genitive/inflected forms that actually appear
# in date phrases (PL "grudnia", CS "prosince", FI "joulukuuta", LT "gruodžio", SK "decembra"). European
# month names are conveniently unambiguous across languages — every spelling below maps to one month, so a
# single flat table can be matched without knowing the document's language.
# Accent-stripped variants are included alongside the correct spelling because curated titles are not
# consistently accented ("fevrier", "zari").
_MONTH_NAMES: tuple[tuple[tuple[str, ...], int], ...] = (
    (("january", "januar", "januari", "janvier", "jänner", "gennaio", "enero", "janeiro", "jaanuar",
      "stycznia", "ledna", "januára", "januara", "januarja", "sausio", "tammikuuta"), 1),
    (("february", "februar", "februari", "février", "fevrier", "febbraio", "febrero", "fevereiro",
      "veebruar", "lutego", "února", "unora", "februára", "februarja", "vasario", "helmikuuta"), 2),
    (("march", "märz", "marz", "maart", "mars", "marts", "märts", "marts", "marzo", "março", "marco",
      "marca", "března", "brezna", "marec", "kovo", "maaliskuuta"), 3),
    (("april", "avril", "aprile", "abril", "aprill", "kwietnia", "dubna", "aprila", "aprilja",
      "balandžio", "balandzio", "huhtikuuta"), 4),
    (("may", "mai", "mei", "maj", "maggio", "mayo", "maio", "maja", "května", "kvetna", "mája",
      "gegužės", "geguzes", "toukokuuta"), 5),
    (("june", "juni", "juin", "giugno", "junio", "junho", "juuni", "czerwca", "června", "cervna",
      "júna", "juna", "junija", "birželio", "birzelio", "kesäkuuta", "kesakuuta"), 6),
    (("july", "juli", "juillet", "luglio", "julio", "julho", "juuli", "lipca", "července", "cervence",
      "júla", "jula", "julija", "liepos", "heinäkuuta", "heinakuuta"), 7),
    (("august", "augustus", "augusti", "août", "aout", "agosto", "sierpnia", "srpna", "avgusta",
      "rugpjūčio", "rugpjucio", "elokuuta"), 8),
    (("september", "septembre", "settembre", "septiembre", "setiembre", "setembro", "września",
      "wrzesnia", "září", "zari", "septembra", "rugsėjo", "rugsejo", "syyskuuta"), 9),
    (("october", "oktober", "oktoober", "octobre", "ottobre", "octubre", "outubro", "października",
      "pazdziernika", "října", "rijna", "októbra", "oktobra", "spalio", "lokakuuta"), 10),
    (("november", "novembre", "noviembre", "novembro", "listopada", "listopadu", "novembra",
      "lapkričio", "lapkricio", "marraskuuta"), 11),
    (("december", "dezember", "décembre", "decembre", "dicembre", "diciembre", "dezembro",
      "detsember", "grudnia", "prosince", "decembra", "gruodžio", "gruodzio", "joulukuuta"), 12),
)
_MONTHS: dict[str, int] = {}
for _names, _num in _MONTH_NAMES:
    for _n in _names:
        # A spelling that meant two different months would silently mis-date rows in one of the two
        # languages, so the table is asserted collision-free at import.
        assert _MONTHS.get(_n, _num) == _num, f"month spelling {_n!r} maps to two months"
        _MONTHS[_n] = _num
del _names, _num, _n

# Longest-first so "septembre" is preferred over a hypothetical prefix match.
_MONTH_ALT = "|".join(sorted((re.escape(m) for m in _MONTHS), key=len, reverse=True))

# Day-Month-Year, the dominant order. Absorbs the connectives and ordinal decorations the phrase carries
# in different languages: "of 5 June 2019", "du 1er février 2020", "vom 19. Dezember 2024",
# "z dnia 6 grudnia 2024 r.", "de 16 de diciembre de 2022", "af 5. juni 2019", "5. kesäkuuta 2019".
_DMY_RE = re.compile(
    rf"(?<![\d.])(\d{{1,2}})\s*(?:º|°|er|st|nd|rd|th|\.)?\s+(?:de\s+|d[’']\s*)?({_MONTH_ALT})\b\.?"
    rf"(?:\s+de)?,?\s+(?:r\.\s+)?(\d{{4}})(?!\d)",
    re.IGNORECASE | re.UNICODE,
)
# Year-Month-Day, used by Lithuanian ("2024 m. gruodžio 6 d.") and Hungarian ("2024. december 6.").
_YMD_RE = re.compile(
    rf"(?<!\d)(\d{{4}})\s*\.?\s*(?:m\.|g\.|gada)?\s*({_MONTH_ALT})\b\.?\s*(\d{{1,2}})(?!\d)",
    re.IGNORECASE | re.UNICODE,
)

# A date phrase introduced by one of these is a COMPLIANCE/EFFECTIVE deadline the title happens to name
# ("banned from 3 July 2021", "à compter du 1er janvier 2030"), not the act's own adoption date, so such a
# phrase is skipped rather than trusted. Checked against the two words immediately preceding the match.
# Deliberately EXCLUDES the ordinary adoption connectives ("of", "du", "vom", "z dnia", "den", "af") —
# those introduce exactly the date we want.
_DEADLINE_CUES = frozenset({
    "by", "from", "until", "till", "before", "after", "since", "effective", "starting", "beginning",
    "commencing", "later", "than", "partir", "compter", "ab", "vanaf", "desde", "entro", "beginnend",
})


def _current_year() -> int:
    return datetime.date.today().year


_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _preceded_by_deadline_cue(text: str, start: int) -> bool:
    """True if the two words before position `start` mark the match as a forward-looking deadline."""
    words = _WORD_RE.findall(text[max(0, start - 24):start].lower())
    return any(w in _DEADLINE_CUES for w in words[-2:])


def derive_title_date(title: str | None, *, max_year: int | None = None) -> datetime.date | None:
    """The day-precision adoption date named in an official title, or None.

    Handles both word orders present in the corpus — Day-Month-Year ("of 5 June 2019", "du 28 janvier
    2025", "vom 19. Dezember 2024", "z dnia 6 grudnia 2024 r.") and Year-Month-Day ("2024 m. gruodžio
    6 d.") — across the languages in _MONTHS. Deliberately matches only WORD months: a numeric date in a
    title is nearly always an Official Journal citation ("OJ L 285, 31.10.2009"), i.e. a publication date
    for a DIFFERENT act, so parsing those would silently mis-date the row.

    Takes the FIRST in-range, calendar-valid match: a statute's own date precedes any date it goes on to
    cite or impose. Range-guarded to [MIN_LAW_YEAR, max_year], which also drops future compliance targets.
    """
    text = title or ""
    if not text:
        return None
    max_year = max_year or _current_year()
    for pattern, order in ((_DMY_RE, "dmy"), (_YMD_RE, "ymd")):
        for m in pattern.finditer(text):
            if order == "dmy":
                day, month_name, year = m.group(1), m.group(2), m.group(3)
            else:
                year, month_name, day = m.group(1), m.group(2), m.group(3)
            y = int(year)
            if not (MIN_LAW_YEAR <= y <= max_year):
                continue
            if _preceded_by_deadline_cue(text, m.start()):
                continue
            try:
                return datetime.date(y, _MONTHS[month_name.lower()], int(day))
            except (KeyError, ValueError):
                continue  # e.g. "31 February" — not a real date, keep scanning
    return None


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
    """The derived enactment date, or None. What the ingest path stores.

    A day-precision date named in the title wins outright (it is the act's real adoption date, and it
    overrides the CELEX numbering year, which can be a year off). Otherwise we fall back to a derived
    year, stored as Jan 1 to signal year-only precision.
    """
    precise = derive_title_date(title, max_year=max_year)
    if precise is not None:
        return precise
    got = derive_law_year(source_id, title, max_year=max_year)
    return datetime.date(got[0], 1, 1) if got else None


def ensure_status_date(bill) -> bool:
    """Give a dateless non-US bill a derived status_date. Returns True if one was set.

    PROMOTION HOOK. scripts/backfill_foreign_dates.py only walks rows that are ce_relevant AT THE TIME
    IT RUNS, so any later promotion (a reclassify, scripts/backfill_adjacency.py) pulls fresh foreign
    rows into scope that nothing ever dates — they show up as "N bills carry no date" in the /research
    year aggregate. That is exactly how 19 dated-able EU/CELEX rows sat undated for six weeks after the
    transboundary promotion. So every path that flips ce_relevant True calls this on the way through.

    Duck-typed on anything carrying .region/.bill_number/.title/.status_date (an ORM Bill, an asyncpg
    Record wrapper) so the ORM and raw-SQL promoters can share one rule. US rows are skipped: their
    status_date means "date of last action", not "enacted year", and is owned by the source feed.
    """
    if (bill.region or "US") == "US" or bill.status_date is not None:
        return False
    derived = derive_status_date(bill.bill_number, bill.title)
    if derived is None:
        return False
    bill.status_date = derived
    return True
