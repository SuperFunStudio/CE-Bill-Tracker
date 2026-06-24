"""Controlled polymer / resin vocabulary + a precision-tuned detector for bill text.

Why this exists
---------------
`bills.material_categories` is deliberately category-level (``plastic_packaging``,
``plastic_products`` …). It can't tell you *which* resin a bill names — EVA vs HDPE vs
expanded polystyrene — because the resin is almost never in the short summaries we store
(title / description / ai_summary). The detail only lives in the full bill text.

This module is the resin-level "material list": one entry per polymer, each with its
ASTM/SPI Resin Identification Code (RIC, 1–7) where one exists, human aliases, and a
detection regex. ``detect_polymers(full_text)`` runs the whole list over a bill's full text
and returns the resin codes found.

False-positive defense
----------------------
Bare two/three-letter abbreviations are landmines in legislative text: ``PP`` → NY budget
"Part PP", ``PET`` → "pet dealers", ``PLA`` → "project labor agreements", ``ABS`` →
"absent". So every entry separates:
  * ``spelled`` — high-precision full names ("polypropylene", "expanded polystyrene").
    Always trusted.
  * ``abbrev``  — the bare code. Trusted ONLY when a plastics-context word
    (plastic / resin / polymer / packaging / container / recycl…) sits within
    ``_CONTEXT_WINDOW`` characters. Full bill text nearly always writes
    "polypropylene (PP)", so the spelled form carries the signal and the abbrev is just
    confirmation — but the gate lets us catch the rare abbrev-only mention safely.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Plastics-context cue. An ambiguous abbreviation only counts as a polymer hit when one of
# these appears near it. Kept broad enough to cover EPR phrasing, tight enough to exclude
# unrelated bills (budget "parts", pet shops, labor agreements).
_CONTEXT = re.compile(
    r"\b(plastic|resin|polymer|packaging|container|bottle|foam|recycl|"
    r"single.?use|post.?consumer|beverage|film|pellet|nurdle|microplastic)\w*",
    re.I,
)
_CONTEXT_WINDOW = 120  # chars on each side of an abbrev match


@dataclass(frozen=True)
class Polymer:
    code: str               # canonical short code we store, e.g. "HDPE"
    name: str               # display name
    ric: int | None         # SPI/ASTM resin identification code 1–7, or None
    spelled: list[str]      # high-precision regex fragments (full names); always trusted
    abbrev: list[str] = field(default_factory=list)  # bare codes; gated on plastics context

    @property
    def spelled_re(self) -> re.Pattern:
        return re.compile("|".join(self.spelled), re.I)

    @property
    def abbrev_re(self) -> re.Pattern | None:
        # Case-SENSITIVE on purpose: real resin abbreviations are written uppercase ("PLA",
        # "HDPE", "PET"). Matching case-insensitively catches lowercase fragments like the
        # "pla" in an OCR-split "pla stics", or "pet"/"pp" inside ordinary words.
        if not self.abbrev:
            return None
        return re.compile("|".join(rf"\b{a}\b" for a in self.abbrev))


# Order matters for human display only; detection is independent per entry. HDPE/LDPE are
# listed before generic PE so a reader scanning results sees the specific grade first.
POLYMERS: list[Polymer] = [
    Polymer("PET", "Polyethylene terephthalate", 1,
            spelled=[r"polyethylene\s+terephthalate", r"\bPETE\b"],
            abbrev=["PET"]),
    Polymer("HDPE", "High-density polyethylene", 2,
            spelled=[r"high[\s-]?density\s+polyethylene"],
            abbrev=["HDPE"]),
    Polymer("PVC", "Polyvinyl chloride", 3,
            spelled=[r"polyvinyl\s+chloride", r"vinyl\s+chloride"],
            abbrev=["PVC"]),
    Polymer("LDPE", "Low-density polyethylene", 4,
            spelled=[r"low[\s-]?density\s+polyethylene", r"linear\s+low[\s-]?density\s+polyethylene"],
            abbrev=["LDPE", "LLDPE"]),
    Polymer("PP", "Polypropylene", 5,
            spelled=[r"polypropylene"],
            abbrev=["PP"]),
    Polymer("PS", "Polystyrene", 6,
            spelled=[r"polystyrene", r"expanded\s+polystyrene", r"extruded\s+polystyrene", r"styrofoam"],
            abbrev=["PS", "EPS", "XPS"]),
    # RIC 7 "other" / specialty resins below.
    Polymer("PLA", "Polylactic acid (bioplastic)", 7,
            spelled=[r"polylactic\s+acid", r"polylactide"],
            abbrev=["PLA"]),
    Polymer("PC", "Polycarbonate", 7,
            spelled=[r"polycarbonate"],
            abbrev=[]),
    Polymer("ABS", "Acrylonitrile butadiene styrene", 7,
            spelled=[r"acrylonitrile[\s-]?butadiene[\s-]?styrene"],
            # No "ABS" abbrev: it collides with automotive Anti-lock Braking System, which
            # appears (with recycling context) in end-of-life-vehicle / mercury-switch bills.
            abbrev=[]),
    Polymer("EVA", "Ethylene-vinyl acetate", None,
            spelled=[r"ethylene[\s-]?vinyl\s+acetate"],
            abbrev=["EVA"]),
    Polymer("PUR", "Polyurethane", None,
            spelled=[r"polyurethane"],
            abbrev=["PUR", "PU"]),
    Polymer("PA", "Polyamide / nylon", None,
            spelled=[r"polyamide", r"\bnylon\b"],
            abbrev=[]),
    Polymer("PE", "Polyethylene (unspecified grade)", None,
            # Generic PE: only the spelled form, and only when NOT already qualified as
            # high/low-density (those are caught by HDPE/LDPE). The detector strips
            # qualified mentions before testing this entry — see detect_polymers().
            spelled=[r"polyethylene"],
            abbrev=[]),
]

CODES: list[str] = [p.code for p in POLYMERS]
BY_CODE: dict[str, Polymer] = {p.code: p for p in POLYMERS}

# Stripped before testing generic PE so "high-density polyethylene" doesn't also fire "PE".
_QUALIFIED_PE = re.compile(r"(?:high|low|linear\s+low)[\s-]?density\s+polyethylene|"
                           r"polyethylene\s+terephthalate", re.I)


def _abbrev_in_context(text: str, abbrev_re: re.Pattern) -> bool:
    for m in abbrev_re.finditer(text):
        a = max(0, m.start() - _CONTEXT_WINDOW)
        b = min(len(text), m.end() + _CONTEXT_WINDOW)
        if _CONTEXT.search(text[a:b]):
            return True
    return False


def detect_polymers(full_text: str) -> list[str]:
    """Return the sorted resin codes named in ``full_text`` (high precision).

    A polymer is detected when its spelled-out name appears, OR its bare abbreviation
    appears within a plastics-context window. Generic PE only fires on a ``polyethylene``
    mention that isn't part of a more specific grade (HDPE/LDPE/PET).
    """
    if not full_text:
        return []
    found: set[str] = set()
    pe_test_text = _QUALIFIED_PE.sub(" ", full_text)
    for p in POLYMERS:
        text = pe_test_text if p.code == "PE" else full_text
        if p.spelled_re.search(text):
            found.add(p.code)
            continue
        ar = p.abbrev_re
        if ar and _abbrev_in_context(full_text, ar):
            found.add(p.code)
    return sorted(found, key=CODES.index)
