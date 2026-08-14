"""Is this row an AMENDING act, or a law that stands on its own?

A body of law is not the sum of the documents that edit it. "Commission Regulation (EU) No 733/2014
amending Regulation (EC) No 1418/2007" is not a second export-control regime next to the 2007 one — it
is a patch to it. The same holds for "The Producer Responsibility Obligations (Packaging Waste)
(Amendment) Regulations 2008" and "Décret n° 2016-794 modifiant le décret n° 2015-1826". Counting each
as a law on the books inflates every cumulative total, and the inflation is uneven across regions: the
EU and UK legislate heavily by amendment (56 and 52 rows here), so a naive count overstates them
against jurisdictions that re-enact instead.

This module centralizes the test so the ingest path and scripts/backfill_act_role.py agree, exactly as
app/ingestion/law_dates.py does for dates.

IT IS A TITLE HEURISTIC AND IT IS DELIBERATELY CONSERVATIVE. The signal it reads is structural, not
semantic: an amending act names the instrument it amends, in a fixed grammatical frame that legislative
drafting conventions make very stable ("amending <cite>", "(Amendment) Act 2020", "modifiant le décret
n° …"). Where a jurisdiction's naming convention breaks that link between form and function, we do NOT
guess — see _CONVENTION_EXEMPT below. A false positive silently deletes a real law from the count,
which is worse than the over-count we are fixing, so every rule here errs toward leaving rows alone.

Consumers must treat is_amending=True as "this row edits another law we may or may not also hold", NOT
as "ignore this row". Amending acts carry real obligations and stay fully in the corpus, searchable and
citable; they are only excluded from headline *counts of distinct laws*.
"""
from __future__ import annotations

import re

# Regions whose drafting convention makes the title test uninformative, checked against `region`.
#
# The WHOLE OF THE US is exempt, and this is not caution — it is that the signal genuinely does not
# exist there. US legislatures enact substantive law BY amending a code, so "amends" in a title says
# nothing about whether the act is a standalone regime. Two rows proved it directly: Pennsylvania's
# "An Act amending Title 27 … providing for decommissioning of solar energy facilities" CREATES a
# decommissioning regime, and Tennessee's "makes revisions to the law relative to wheelchair repair —
# Amends TCA Title 4; …" IS that state's wheelchair right-to-repair law. Both would have been deleted
# from the law count by a rule that reads the American convention as a European one. DC is the extreme
# case ("… Amendment Act of YYYY" for nearly every enactment) but it is a difference of degree.
#
# The Westminster and EU conventions are the opposite: an amending instrument is a distinct document
# type, named as such precisely so it is not mistaken for the principal act.
_CONVENTION_EXEMPT_REGIONS = frozenset({"US"})

# A coordinating conjunction immediately before the amending participle marks the amendment as the
# act's SECONDARY function: "…relatif au barème de la contribution … ET modifiant le décret n° 2006-239"
# sets a fee schedule and amends as a consequence, and "Regulation … on market surveillance … AND
# amending Directive 2004/42/EC" is a market-surveillance regime. Both are principal acts. Only an
# amendment announced as the act's whole purpose ("Directive (EU) 2018/851 amending Directive
# 2008/98/EC") makes the row a patch. Same shape as _DEADLINE_CUES in app/ingestion/law_dates.py.
_SECONDARY_CUES = frozenset({
    "and", "et", "e", "y", "i", "und", "en", "oraz", "ed", "a", "samt", "och", "og", "sekä",
})
_TRAILING_WORD_RE = re.compile(r"[^\W\d_]+(?=\W*$)", re.UNICODE)

# A parenthesized "(Amendment)" / "(Amendment No. 2)" / "(Consequential Amendments)" qualifier — the
# Westminster-family convention (UK, AU, IN, IE, NZ). Extremely reliable: the qualifier exists purely
# to distinguish an amending instrument from the principal one it amends.
_PAREN_AMENDMENT = re.compile(
    r"\(\s*(?:consequential\s+|minor\s+|miscellaneous\s+|technical\s+)?amendments?"
    r"(?:\s*(?:no\.?\s*\d+|\(\d+\)))?\s*\)",
    re.IGNORECASE,
)

# "…Amendment Act 2020", "…Legislation Amendment Act (No. 1) 2003", and the form that carries a
# parenthetical subject between the two words — "Excise Tariff Amendment (Product Stewardship for Oil)
# Act 2014", which amends the Excise Tariff Act. Requires the instrument noun to follow, so a title
# merely discussing amendment ("…on the amendment of packaging targets") does not match.
_AMENDMENT_ACT = re.compile(
    r"\bamendment\s+(?:\([^)]{0,60}\)\s*)?(?:act|regulations?|rules?|order|ordinance|decree|bill)\b",
    re.IGNORECASE,
)

# "amending Regulation (EC) No 1418/2007", "amending Directive 2009/33/EC", "amending Annex XVII to …"
# — the EU convention. Requires a following instrument CITATION so that "an Act establishing X and
# amending unrelated provisions" is not caught by the bare verb.
_AMENDING_CITE = re.compile(
    r"\bamend(?:ing|s)\b[^,;.]{0,40}?\b(?:regulation|directive|decision|annex|act|law|rules?|"
    r"resolution|ordinance|code|title)\b",
    re.IGNORECASE,
)

# Same frame in the other drafting languages present in the corpus. Each requires the instrument noun
# to follow the participle, mirroring _AMENDING_CITE.
_AMENDING_CITE_INTL = re.compile(
    r"\b(?:"
    r"modifiant|modifie|modificando|modifica(?:ndo)?|modificación\s+de|"      # FR / ES / IT / PT
    r"zmieniaj\w*|zmiana|"                                                    # PL
    r"ändring(?:s\w*)?\s+(?:av|i)|ändrar|"                                    # SE
    r"änderung\s+(?:der|des)|zur\s+änderung|"                                 # DE
    r"wijziging\s+van|"                                                       # NL
    r"altera(?:ção)?\s+(?:a|à|da|do)"                                         # PT-BR
    r")\b[^,;.]{0,50}?"
    r"\b(?:regulation|directive|decision|r[eè]glement|d[ée]cret|arr[êe]t[ée]|loi|ley|decreto|"
    r"resoluci[óo]n|legge|verordnung|richtlinie|gesetz|ustaw\w*|rozporz\w*|f[öo]rordning|lag|"
    r"wet|besluit|lei|no\.?|n[°º]|nr\.?)\b",
    re.IGNORECASE | re.UNICODE,
)

_PATTERNS = (
    ("paren_amendment", _PAREN_AMENDMENT),
    ("amendment_act", _AMENDMENT_ACT),
    ("amending_cite", _AMENDING_CITE),
    ("amending_cite_intl", _AMENDING_CITE_INTL),
)


# legislation.gov.uk appends a status marker to instruments no longer in force, and the UK adapter
# carries it through into the title verbatim: "The Packaging Waste (Data Collection and Reporting)
# (Wales) Regulations 2023 (revoked)". Those rows sit in the corpus as status='enacted', so a law the
# UK has already withdrawn still counts as one on the books.
#
# This catches only what a source states outright in the title. It is NOT repeal tracking: the corpus
# holds acts that later law repealed without saying so in their own name (EU directives are routinely
# recast this way), and finding those needs the repeal relations in CELLAR or legislation.gov.uk, not a
# regex. So a clean result here means "no row ADMITS to being revoked", never "everything else is in
# force". Treat the number this returns as a floor.
_REVOKED_MARKER = re.compile(r"\((?:revoked|repealed|spent|rescinded)\)\s*$", re.IGNORECASE)


def is_revoked(title: str | None) -> bool:
    """True if the title itself declares the instrument no longer in force. A floor, not a census."""
    return bool(_REVOKED_MARKER.search((title or "").strip()))


def _is_secondary(text: str, start: int) -> bool:
    """True if the match at `start` is introduced by a coordinating conjunction — see _SECONDARY_CUES."""
    m = _TRAILING_WORD_RE.search(text[max(0, start - 16):start])
    return m is not None and m.group(0).lower() in _SECONDARY_CUES


def classify_act_role(
    title: str | None, *, region: str | None = None, state: str | None = None
) -> tuple[bool, str | None]:
    """Return (is_amending, rule) for a law title. `rule` names the pattern that fired, for audit.

    `region` opts a jurisdiction out via _CONVENTION_EXEMPT_REGIONS; `state` is accepted so callers can
    pass the whole row, and today only narrows within an already-exempt region. Returns (False, None)
    when nothing matches, the title is empty, or every match is secondary — the safe default, since an
    unflagged amending act merely leaves today's over-count in place while a wrongly-flagged principal
    act deletes a real law from the count.
    """
    text = (title or "").strip()
    if not text:
        return False, None
    if (region or "US").upper() in _CONVENTION_EXEMPT_REGIONS:
        return False, None
    for rule, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            # An "…and amending X" clause is the act's secondary function; keep scanning in case the
            # title also carries a primary amending frame.
            if not _is_secondary(text, m.start()):
                return True, rule
    return False, None


def is_amending(title: str | None, *, region: str | None = None, state: str | None = None) -> bool:
    return classify_act_role(title, region=region, state=state)[0]
