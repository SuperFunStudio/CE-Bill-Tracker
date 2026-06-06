import json
import re
from dataclasses import dataclass, field
from pathlib import Path

KEYWORDS_PATH = Path(__file__).parent.parent.parent / "data" / "seed" / "epr_keywords.json"


@dataclass
class KeywordScore:
    matched_tier1: list[str] = field(default_factory=list)       # primary — near-certain signals
    matched_tier2: list[str] = field(default_factory=list)       # strong domain signals
    matched_tier3: list[str] = field(default_factory=list)       # moderate/ambiguous signals
    matched_preemption: list[str] = field(default_factory=list)  # federal preemption (special)
    matched_exclusions: list[str] = field(default_factory=list)
    material_hints: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        s = 0.0
        s += len(self.matched_tier1) * 1.0
        s += len(self.matched_tier2) * 0.7
        s += len(self.matched_tier3) * 0.4
        s += len(self.matched_preemption) * 0.6
        s -= len(self.matched_exclusions) * 2.0
        return max(0.0, s)

    @property
    def passes(self) -> bool:
        if self.matched_exclusions:
            return False
        if self.matched_tier1:
            return True
        return self.score >= 0.6


MATERIAL_HINT_MAP = {
    "plastic": "plastic_packaging",
    "packaging": "plastic_packaging",
    "e-waste": "electronics",
    "ewaste": "electronics",
    "electronic": "electronics",
    "battery": "batteries",
    "batteries": "batteries",
    "paint": "paint",
    "carpet": "carpet",
    "mattress": "mattresses",
    "tire": "tires",
    "pharmaceutical": "pharmaceuticals",
    "drug": "pharmaceuticals",
    "sharps": "pharmaceuticals",
    "solar": "solar_panels",
    "textile": "textiles",
    "clothing": "textiles",
    "apparel": "textiles",
    "deposit": "deposit_return",
    "bottle bill": "deposit_return",
    "right to repair": "right_to_repair",
    "repair": "right_to_repair",
}


class KeywordFilter:
    def __init__(self, keywords_path: Path = KEYWORDS_PATH):
        with open(keywords_path) as f:
            kw = json.load(f)

        # Tier 1 — near-certain relevance signals
        self._tier1 = self._compile(kw["primary_keywords"])

        # Tier 2 — strong domain signals with some ambiguity
        tier2_keys = [
            "material_keywords",
            "recycled_content_keywords",
            "deposit_return_keywords",
            "right_to_repair_keywords",
            "pfas_and_chemicals_keywords",
        ]
        self._tier2 = self._compile([term for k in tier2_keys for term in kw[k]])

        # Tier 3 — moderate signals, high ambiguity
        tier3_keys = [
            "reuse_and_refill_keywords",
            "resale_and_secondhand_keywords",
            "organics_and_food_waste_keywords",
            "repairability_and_durability_keywords",
            "digital_product_passport_keywords",
            "remanufacturing_keywords",
            "procurement_and_incentives_keywords",
            "policy_mechanism_keywords",
        ]
        self._tier3 = self._compile([term for k in tier3_keys for term in kw[k]])

        # Tier 4 — preemption signals (only meaningful in combination)
        self._preemption = self._compile(kw["federal_preemption_keywords"])

        # Exclusions — hard disqualifiers
        self._exclusions = self._compile(kw["exclusion_keywords"])

        self._hint_patterns = [
            (re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE), v)
            for k, v in MATERIAL_HINT_MAP.items()
        ]

    @staticmethod
    def _compile(keywords: list[str]) -> list[re.Pattern]:
        return [
            re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            for kw in keywords
        ]

    def _search_text(self, text: str, patterns: list[re.Pattern]) -> list[str]:
        return [p.pattern for p in patterns if p.search(text)]

    def score(self, title: str, description: str = "", text_excerpt: str = "") -> KeywordScore:
        corpus = " ".join([title, description, text_excerpt[:2000]])
        matched_hints: list[str] = []
        for pattern, hint in self._hint_patterns:
            if pattern.search(corpus) and hint not in matched_hints:
                matched_hints.append(hint)
        return KeywordScore(
            matched_tier1=self._search_text(corpus, self._tier1),
            matched_tier2=self._search_text(corpus, self._tier2),
            matched_tier3=self._search_text(corpus, self._tier3),
            matched_preemption=self._search_text(corpus, self._preemption),
            matched_exclusions=self._search_text(corpus, self._exclusions),
            material_hints=matched_hints,
        )

    def passes_threshold(
        self, title: str, description: str = "", text_excerpt: str = ""
    ) -> bool:
        return self.score(title, description, text_excerpt).passes
