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
    "bio-based": "biobased",
    "biobased": "biobased",
    "biopolymer": "biobased",
    "bioplastic": "biobased",
    "compost": "organics",
    "soil": "agriculture",
    "regenerative": "agriculture",
    "cover crop": "agriculture",
    # Water (cross-cycle leakage) + biodiversity (biological-cycle regenerative outcome).
    "microplastic": "water",
    "microfiber": "water",
    "marine debris": "water",
    "marine litter": "water",
    "biosolids": "water",
    "water reuse": "water",
    "reclaimed water": "water",
    "biodiversity": "biodiversity",
    "deforestation-free": "biodiversity",
    "pollinator": "biodiversity",
    "nature-positive": "biodiversity",
}


class KeywordFilter:
    def __init__(self, keywords_path: Path = KEYWORDS_PATH):
        with open(keywords_path) as f:
            kw = json.load(f)

        # Tier 1 — near-certain relevance signals
        self._tier1 = self._compile(kw["primary_keywords"])

        # Tier 2 — strong domain signals with some ambiguity. The biomaterials/regen-ag terms
        # are the biological cycle of the circular economy (bio-based materials, soil health);
        # they're specific enough that a single match should clear the threshold, like materials.
        # Generic economic terms from those domains (e.g. "feedstock", "biomass", "investment
        # tax credit", "economic development", "innovation grant") were deliberately NOT added —
        # they'd swamp the filter with false positives and waste a Haiku call per passing bill.
        tier2_keys = [
            "material_keywords",
            "biomaterials_keywords",
            "soil_health_and_regenerative_ag_keywords",
            # Water is a cross-cycle LEAKAGE subject; its terms (microplastics, marine litter,
            # water reuse, biosolids) are specific + circular by nature, so a single match clears
            # the threshold like the material/bio-cycle terms. General water-quality / drinking-water
            # / water-rights terms are deliberately absent — see the tight boundary in the classifier
            # prompt (haiku_classifier "Water & biodiversity" paragraph).
            "water_and_waterways_keywords",
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
            # Biodiversity is the hardest subject to bound (general conservation law dwarfs the
            # circular slice), so it sits at tier 3: a match alone (0.4) does NOT clear the 0.6
            # threshold — it needs a co-signal (a material/procurement/circular term), which is
            # exactly the "biodiversity as a material/sourcing OUTCOME" boundary. Bump to tier 2 to
            # widen. The classifier prompt makes the final keep/reject call.
            "biodiversity_keywords",
        ]
        self._tier3 = self._compile([term for k in tier3_keys for term in kw[k]])

        # Tier 4 — preemption signals (only meaningful in combination)
        self._preemption = self._compile(kw["federal_preemption_keywords"])

        # Exclusions — hard disqualifiers
        self._exclusions = self._compile(kw["exclusion_keywords"])

        # Rescue set — high-precision, definitionally in-scope phrases used by strong_signal() to
        # keep a bill the LLM would have dropped (see ClassificationPipeline). Tier-1 (EPR program
        # terms) plus the definitional instrument tiers (right-to-repair / deposit-return / recycled-
        # content / organics, which map to circular-economy policy by definition) plus a curated set
        # of unambiguous circular-economy phrases that aren't already covered. Multi-word and
        # specific on purpose so the rescue stays high precision — it must NOT fire on out-of-scope
        # titles (clemency, ground leases, highway emissions).
        rescue_keys = [
            "primary_keywords",
            "right_to_repair_keywords",
            "deposit_return_keywords",
            "recycled_content_keywords",
            "organics_and_food_waste_keywords",
        ]
        rescue_terms = [term for k in rescue_keys for term in kw[k]]
        rescue_terms += [
            "circular economy",
            "single-use plastic",
            "single use plastic",
            "packaging reduction",
            "packaging waste",
            "plastic packaging",
            "organic waste",
        ]
        self._rescue = self._compile(rescue_terms)

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

    def strong_signal(
        self, title: str, description: str = "", text_excerpt: str = ""
    ) -> bool:
        """Near-certain in-scope signal: a high-precision rescue-set phrase and no exclusion.

        Used as a rescue net in the classification pipeline — if the LLM would drop a bill (often
        because it was starved of bill text and bailed to is_ce_relevant=false), but the title/
        description carries an unambiguous definitional term (e.g. "extended producer responsibility",
        "bottle bill", "right to repair", "circular economy", "packaging waste"), we keep it in scope
        and flag it for review rather than silently shedding it. Uses the curated `_rescue` set (not
        the looser `passes` threshold) so the rescue stays high-precision.
        """
        corpus = " ".join([title, description, text_excerpt[:2000]])
        if self._search_text(corpus, self._exclusions):
            return False
        return bool(self._search_text(corpus, self._rescue))
