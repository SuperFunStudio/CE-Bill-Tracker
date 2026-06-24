"""Heuristic "nearest chain of responsibility" extractor for EPR / product-stewardship bills.

What it answers
---------------
Most framework EPR bills don't name a resin or even a concrete obligation — they delegate the
specifics downstream. For a producer the useful question is *"who is next responsible, and
what links exist between the statute and me?"* The canonical chain is:

    Producer → (joins/forms a) PRO → files a Stewardship Plan → Agency approves (by rule)
             → informed by a Needs Assessment → Advisory body reviews → Agency enforces

This module detects which links a bill contains (robust, drafting language is consistent) and
names the **implementing agency** from a curated per-state map (far more reliable than scraping
the text, which collides with bill-drafting "Legislative Commission" / "Law Revision
Commission"). The agency is marked ``confirmed_in_text`` when its name/abbr also appears in the
bill. Advisory-body names are pulled from the text when present (best-effort).

This is Tier 1: cheap, no LLM, full-corpus coverage. Precise ordered chains with exact named
entities are a Tier-2 SonnetExtractor job. See [[polymer-resin-extraction]].
"""
from __future__ import annotations

import re
from collections import Counter

# Implementing agency for product-stewardship / recycling programs, per state. This is the body
# that runs EPR programs (adopts rules, approves stewardship plans) — overwhelmingly the state
# environmental agency regardless of product type. (name, abbr, text-confirmation regex).
STATE_EPR_AGENCY: dict[str, tuple[str, str, str]] = {
    "CA": ("Department of Resources Recycling and Recovery", "CalRecycle",
           r"CalRecycle|Resources Recycling and Recovery"),
    "OR": ("Oregon Department of Environmental Quality", "DEQ",
           r"Department of Environmental Quality|\bDEQ\b|Environmental Quality Commission"),
    "CO": ("Colorado Department of Public Health and Environment", "CDPHE",
           r"Public Health and Environment|\bCDPHE\b"),
    "ME": ("Maine Department of Environmental Protection", "DEP",
           r"Department of Environmental Protection|\bDEP\b"),
    "MN": ("Minnesota Pollution Control Agency", "MPCA",
           r"Pollution Control Agency|\bMPCA\b|\bPCA\b"),
    "WA": ("Washington Department of Ecology", "Ecology",
           r"Department of Ecology|\bEcology\b"),
    "MD": ("Maryland Department of the Environment", "MDE",
           r"Department of the Environment|\bMDE\b"),
    "NJ": ("New Jersey Department of Environmental Protection", "NJDEP",
           r"Department of Environmental Protection|\bDEP\b"),
    "NY": ("New York Department of Environmental Conservation", "DEC",
           r"Department of Environmental Conservation|\bDEC\b"),
    "IL": ("Illinois Environmental Protection Agency", "IEPA",
           r"Environmental Protection Agency|\bIEPA\b|\bEPA\b"),
    "CT": ("Connecticut Department of Energy and Environmental Protection", "DEEP",
           r"Energy and Environmental Protection|\bDEEP\b"),
    "VT": ("Vermont Agency of Natural Resources", "ANR",
           r"Agency of Natural Resources|Department of Environmental Conservation|\bANR\b"),
    "RI": ("Rhode Island Department of Environmental Management", "DEM",
           r"Department of Environmental Management|\bDEM\b"),
    "MA": ("Massachusetts Department of Environmental Protection", "MassDEP",
           r"Department of Environmental Protection|MassDEP|\bDEP\b"),
    "TX": ("Texas Commission on Environmental Quality", "TCEQ",
           r"Commission on Environmental Quality|\bTCEQ\b"),
    "VA": ("Virginia Department of Environmental Quality", "DEQ",
           r"Department of Environmental Quality|\bDEQ\b"),
    "US": ("U.S. Environmental Protection Agency", "EPA",
           r"Environmental Protection Agency|\bEPA\b"),
    "HI": ("Hawaii Department of Health", "DOH",
           r"Department of Health|\bDOH\b|Solid and Hazardous Waste"),
    "FL": ("Florida Department of Environmental Protection", "FDEP",
           r"Department of Environmental Protection|\bFDEP\b|\bDEP\b"),
    "MO": ("Missouri Department of Natural Resources", "MoDNR",
           r"Department of Natural Resources|\bDNR\b"),
    "IA": ("Iowa Department of Natural Resources", "Iowa DNR",
           r"Department of Natural Resources|\bDNR\b"),
    "MT": ("Montana Department of Environmental Quality", "DEQ",
           r"Department of Environmental Quality|\bDEQ\b"),
    "WI": ("Wisconsin Department of Natural Resources", "WDNR",
           r"Department of Natural Resources|\bDNR\b"),
    "MI": ("Michigan Department of Environment, Great Lakes, and Energy", "EGLE",
           r"Great Lakes,? and Energy|\bEGLE\b|Department of Environmental Quality"),
    "NH": ("New Hampshire Department of Environmental Services", "NHDES",
           r"Department of Environmental Services|\bDES\b"),
    "OK": ("Oklahoma Department of Environmental Quality", "ODEQ",
           r"Department of Environmental Quality|\bDEQ\b"),
    "WV": ("West Virginia Department of Environmental Protection", "WVDEP",
           r"Department of Environmental Protection|\bDEP\b"),
    "PA": ("Pennsylvania Department of Environmental Protection", "PADEP",
           r"Department of Environmental Protection|\bDEP\b"),
    "AR": ("Arkansas Division of Environmental Quality", "ADEQ",
           r"Division of Environmental Quality|Energy and Environment|\bDEQ\b"),
    "KY": ("Kentucky Energy and Environment Cabinet", "EEC",
           r"Energy and Environment Cabinet|Division of Waste Management"),
    "DC": ("District Department of Energy and Environment", "DOEE",
           r"Department of Energy and Environment|\bDOEE\b"),
    "SC": ("South Carolina Department of Environmental Services", "SCDES",
           r"Department of Environmental Services|Health and Environmental Control|\bDHEC\b|\bDES\b"),
    "NC": ("North Carolina Department of Environmental Quality", "NCDEQ",
           r"Department of Environmental Quality|\bDEQ\b"),
    "UT": ("Utah Department of Environmental Quality", "UDEQ",
           r"Department of Environmental Quality|\bDEQ\b"),
    "IN": ("Indiana Department of Environmental Management", "IDEM",
           r"Department of Environmental Management|\bIDEM\b"),
    "TN": ("Tennessee Department of Environment and Conservation", "TDEC",
           r"Environment and Conservation|\bTDEC\b"),
    "KS": ("Kansas Department of Health and Environment", "KDHE",
           r"Health and Environment|\bKDHE\b"),
    "OH": ("Ohio Environmental Protection Agency", "Ohio EPA",
           r"Environmental Protection Agency|\bEPA\b"),
    "DE": ("Delaware Department of Natural Resources and Environmental Control", "DNREC",
           r"Natural Resources and Environmental Control|\bDNREC\b"),
    "AK": ("Alaska Department of Environmental Conservation", "ADEC",
           r"Department of Environmental Conservation|\bDEC\b"),
    "GA": ("Georgia Environmental Protection Division", "EPD",
           r"Environmental Protection Division|\bEPD\b"),
    "NV": ("Nevada Division of Environmental Protection", "NDEP",
           r"Division of Environmental Protection|\bNDEP\b"),
    "ID": ("Idaho Department of Environmental Quality", "IDEQ",
           r"Department of Environmental Quality|\bDEQ\b"),
    "SD": ("South Dakota Department of Agriculture and Natural Resources", "DANR",
           r"Agriculture and Natural Resources|\bDANR\b"),
    "NM": ("New Mexico Environment Department", "NMED",
           r"Environment Department|\bNMED\b"),
    "AL": ("Alabama Department of Environmental Management", "ADEM",
           r"Department of Environmental Management|\bADEM\b"),
    "NE": ("Nebraska Department of Environment and Energy", "NDEE",
           r"Environment and Energy|\bNDEE\b"),
    "WY": ("Wyoming Department of Environmental Quality", "WDEQ",
           r"Department of Environmental Quality|\bDEQ\b"),
    "MS": ("Mississippi Department of Environmental Quality", "MDEQ",
           r"Department of Environmental Quality|\bMDEQ\b|\bDEQ\b"),
}

# Chain-link detectors. Each (key, regex). Order = chain order (producer → … → enforcement).
_LINKS: list[tuple[str, re.Pattern]] = [
    ("producer", re.compile(r'"?producer"?\s+means|\bproducer\b\s+(?:is\s+)?(?:obligat|responsib)|'
                            r'obligated\s+producer', re.I)),
    ("pro", re.compile(r"producer responsibility organization|stewardship organization|"
                       r"\bPRO\b(?!\w)", re.I)),
    ("stewardship_plan", re.compile(r"stewardship plan|program plan|product stewardship program|"
                                    r"management plan|plan proposal", re.I)),
    ("agency_rule", re.compile(r"\bby rule\b|\bby regulation\b|adopt(?:\s+\w+){0,2}\s+rules?\b|"
                               r"promulgat\w+|rulemaking|adopt regulations", re.I)),
    ("needs_assessment", re.compile(r"needs assessment", re.I)),
    ("advisory_review", re.compile(r"advisory (?:council|board|committee)", re.I)),
    ("enforcement", re.compile(r"civil penalt|administrative penalt|\benforcement\b|"
                               r"\bpenalt(?:y|ies)\b", re.I)),
]

# Advisory-body NAME: "[Words] Advisory (Council|Board|Committee)". Case-insensitive so it also
# catches lowercase/OCR renderings; the captured name is title-cased for display.
_ADVISORY_NAME = re.compile(
    r"([A-Za-z][A-Za-z]+(?:\s+[A-Za-z]+){0,4}?\s+advisory\s+(?:council|board|committee))", re.I)
_GENERIC_ADVISORY = re.compile(r"^(the\s+)?advisory\s+(council|board|committee)$", re.I)
# Verbs/prepositions/articles the capture may have swept up before the real proper noun
# (e.g. "consult with the ... advisory board", "members of the ... advisory board"). Stripped
# from the front before keeping the name.
_LEAD_NOISE = {"the", "a", "an", "to", "by", "with", "from", "for", "of", "and", "consult",
               "established", "created", "designated", "convene", "appoint", "existing",
               "convened", "appointed", "such", "said", "this", "any", "new", "shall",
               "members", "membership", "after", "consultation", "recommendation",
               "recommendations", "including", "establishing", "establish", "create",
               "creates", "creating", "advice", "advise", "review", "reviewed"}


def _title(name: str) -> str:
    small = {"of", "and", "the", "for", "on"}
    out = []
    for i, w in enumerate(name.split()):
        out.append(w if w.isupper() else (w.lower() if (w.lower() in small and i) else w.capitalize()))
    return " ".join(out)


def _advisory_body(text: str) -> str | None:
    names = Counter()
    for m in _ADVISORY_NAME.finditer(text):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        # Drop leading verbs/prepositions/articles swept in before the proper noun.
        words = name.split()
        while words and words[0].lower() in _LEAD_NOISE:
            words.pop(0)
        name = " ".join(words)
        if not name or _GENERIC_ADVISORY.match(name):
            continue
        names[_title(name)] += 1
    return names.most_common(1)[0][0] if names else None


def extract_chain(state: str, full_text: str) -> dict:
    """Return the responsibility chain for one bill. Empty ``links`` ⇒ no delegation structure
    found (likely a short amendment, a non-framework bill, or unusable text)."""
    text = re.sub(r"[ \t]+", " ", full_text or "")
    links = [key for key, rx in _LINKS if rx.search(text)]

    agency = None
    info = STATE_EPR_AGENCY.get((state or "").upper())
    if info:
        name, abbr, confirm = info
        agency = {
            "name": name,
            "abbr": abbr,
            "confirmed_in_text": bool(re.search(confirm, text)),
            "source": "curated",
        }

    advisory = _advisory_body(text) if "advisory_review" in links else None

    # Nearest actionable node for a producer: the PRO if one is required (join it / file the
    # plan), else the agency rulemaking to watch, else whoever enforces.
    if "pro" in links:
        next_responsible = "pro"
    elif "agency_rule" in links:
        next_responsible = "agency_rule"
    elif "enforcement" in links:
        next_responsible = "agency_enforcement"
    else:
        next_responsible = None

    return {
        "links": links,
        "agency": agency,
        "advisory_body": advisory,
        "by_rule": "agency_rule" in links,
        "needs_assessment": "needs_assessment" in links,
        "next_responsible": next_responsible,
    }
