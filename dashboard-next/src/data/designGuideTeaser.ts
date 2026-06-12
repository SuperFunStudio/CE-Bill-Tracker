// AUTO-GENERATED from tmp/design_principles.json. Do not edit by hand.
// The Free teaser: per-lever headline + direction + one bill-evidence quote (loss-framed).

export interface TeaserLever {
  lever: string;
  name: string;
  headline: string;
  obligation: string;
  direction: string;
  billCount: number;
  states: string[];
  evidence: { state: string; bill: string; quote: string } | null;
}

export const GUIDE_COVERAGE = { bills: 74, states: 12, levers: 9 };

export const TEASER_LEVERS: TeaserLever[] = [
  {
    "lever": "design_for_recycling",
    "name": "Design for Recycling",
    "headline": "Design packaging to be recyclable in available systems",
    "obligation": "Required",
    "direction": "Ensure beverage containers are recyclable in certified recycling systems.",
    "billCount": 36,
    "states": [
      "CA",
      "CO",
      "CT",
      "MD",
      "ME",
      "MN",
      "NY",
      "OR",
      "RI",
      "VT"
    ],
    "evidence": {
      "state": "CA",
      "bill": "AB-1311",
      "quote": "Certified recycling centers must accept and pay at least the refund value for all empty beverage containers, regardless of type, unless exempted"
    }
  },
  {
    "lever": "recycled_content",
    "name": "Recycled Content",
    "headline": "Incorporate post-consumer recycled content",
    "obligation": "Required",
    "direction": "Incorporate minimum postconsumer recycled content percentages.",
    "billCount": 15,
    "states": [
      "CA",
      "CO",
      "ME",
      "NY",
      "OR",
      "VT"
    ],
    "evidence": {
      "state": "CA",
      "bill": "AB-661",
      "quote": "Products in revised SABRC product categories with minimum recycled content percentages (effective January 1, 2023)"
    }
  },
  {
    "lever": "source_reduction",
    "name": "Source Reduction",
    "headline": "Reduce packaging material per unit (lightweight, right-size)",
    "obligation": "Required",
    "direction": "Achieve source reduction targets for covered plastic packaging.",
    "billCount": 11,
    "states": [
      "CA",
      "CO",
      "ME",
      "OR",
      "VT"
    ],
    "evidence": {
      "state": "CA",
      "bill": "SB-303",
      "quote": "Achieve source reduction targets for covered plastic packaging"
    }
  },
  {
    "lever": "reuse_refill",
    "name": "Reuse & Refill",
    "headline": "Shift to reusable / refillable formats",
    "obligation": "Required",
    "direction": "Design glass beverage containers for washing and refill cycles.",
    "billCount": 8,
    "states": [
      "CA",
      "CO",
      "CT",
      "ME",
      "NY",
      "OR"
    ],
    "evidence": {
      "state": "CA",
      "bill": "AB-962",
      "quote": "Beverage manufacturers must have their reusable glass beverage containers processed by a certified processor for subsequent washing for refill and sale"
    }
  },
  {
    "lever": "toxics_elimination",
    "name": "Toxics Elimination",
    "headline": "Eliminate restricted substances (PFAS, heavy metals, etc.)",
    "obligation": "Required",
    "direction": "Eliminate mercury from thermostat designs; transition to mercury-free alternatives.",
    "billCount": 18,
    "states": [
      "CA",
      "CO",
      "CT",
      "KY",
      "MD",
      "ME",
      "MN",
      "NY",
      "OR",
      "VT"
    ],
    "evidence": {
      "state": "CA",
      "bill": "AB-732",
      "quote": "mercury-added thermostats"
    }
  },
  {
    "lever": "material_restriction",
    "name": "Material Restrictions",
    "headline": "Avoid banned / restricted materials and formats",
    "obligation": "Required",
    "direction": "Eliminate or reduce problematic or unnecessary plastic packaging.",
    "billCount": 8,
    "states": [
      "CA",
      "CO",
      "ME",
      "VT"
    ],
    "evidence": {
      "state": "CA",
      "bill": "SB-303",
      "quote": "Eliminate or reduce problematic or unnecessary plastic packaging"
    }
  },
  {
    "lever": "labeling_marking",
    "name": "Labeling & Marking",
    "headline": "Apply required recyclability / disposal labeling",
    "obligation": "Required",
    "direction": "Mark containers with refund value indicator per Section 14560 requirements.",
    "billCount": 25,
    "states": [
      "CA",
      "CT",
      "KY",
      "MD",
      "ME",
      "MI",
      "MN",
      "NY",
      "OR",
      "RI",
      "VT"
    ],
    "evidence": {
      "state": "CA",
      "bill": "AB-1311",
      "quote": "Operators must not pay a refund value for any food or drink packaging material or beverage container that does not have a refund value established pursuant to Section 14560"
    }
  },
  {
    "lever": "compostability",
    "name": "Compostability",
    "headline": "Use certified-compostable materials where specified",
    "obligation": "Required",
    "direction": "Make covered material compostable as alternative to recyclable.",
    "billCount": 3,
    "states": [
      "CA"
    ],
    "evidence": {
      "state": "CA",
      "bill": "SB-54",
      "quote": "Ensure covered material offered for sale, distributed, or imported in or into the state on or after January 1, 2032, is recyclable or compostable"
    }
  },
  {
    "lever": "repairability_durability",
    "name": "Repairability & Durability",
    "headline": "Design for repairability, spare-parts access, and longevity",
    "obligation": "Required",
    "direction": "Make replacement parts available to independent repair providers and owners.",
    "billCount": 28,
    "states": [
      "CA",
      "CO",
      "CT",
      "KY",
      "ME",
      "MN",
      "NY",
      "OR",
      "RI",
      "VT"
    ],
    "evidence": {
      "state": "CA",
      "bill": "SB-1384",
      "quote": "Make available to independent repair providers and owners, on fair and reasonable terms and costs, all documentation, parts, embedded software, firmware, and tools intended for use with the equipment or covered parts, including updates"
    }
  }
];
