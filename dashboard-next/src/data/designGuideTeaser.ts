// AUTO-GENERATED from tmp/design_principles.json. Do not edit by hand.
// The Free teaser: per-lever headline + direction + material/product focus (front face),
// plus the grounded source bills behind the principle (back face -- each opens the bill modal).

export interface TeaserBill {
  state: string;
  billNumber: string;
  billId: number;
}

export interface TeaserLever {
  lever: string;
  name: string;
  headline: string;
  direction: string;
  focus: string[];
  billCount: number;
  states: string[];
  evidence: { state: string; bill: string; quote: string } | null;
  bills: TeaserBill[];
}

export const GUIDE_COVERAGE = { bills: 90, states: 17, levers: 9 };

export const TEASER_LEVERS: TeaserLever[] = [
  {
    "lever": "design_for_recycling",
    "name": "Design for Recycling",
    "headline": "Design packaging to be recyclable in available systems",
    "direction": "Ensure beverage containers are recyclable in certified recycling systems.",
    "focus": [
      "Packaging",
      "Beverage containers",
      "Batteries",
      "Textiles"
    ],
    "billCount": 44,
    "states": [
      "CA",
      "CO",
      "CT",
      "DC",
      "MD",
      "ME",
      "MN",
      "NJ",
      "NY",
      "OR",
      "RI",
      "VT",
      "WA"
    ],
    "evidence": {
      "state": "CA",
      "bill": "AB-1311",
      "quote": "Certified recycling centers must accept and pay at least the refund value for all empty beverage containers, regardless of type, unless exempted"
    },
    "bills": [
      {
        "state": "CA",
        "billNumber": "AB-1311",
        "billId": 81168
      },
      {
        "state": "CA",
        "billNumber": "AB-1857",
        "billId": 82616
      },
      {
        "state": "CA",
        "billNumber": "AB-2440",
        "billId": 80777
      },
      {
        "state": "CA",
        "billNumber": "SB-303",
        "billId": 733
      },
      {
        "state": "CA",
        "billNumber": "SB-343",
        "billId": 81917
      },
      {
        "state": "CA",
        "billNumber": "SB-54",
        "billId": 865
      },
      {
        "state": "CA",
        "billNumber": "SB-707",
        "billId": 620
      },
      {
        "state": "CO",
        "billNumber": "HB-22-1355",
        "billId": 72416
      },
      {
        "state": "CO",
        "billNumber": "HB22-1355",
        "billId": 104215
      },
      {
        "state": "CO",
        "billNumber": "SB-25-163",
        "billId": 82272
      },
      {
        "state": "CT",
        "billNumber": "HB-5142",
        "billId": 82844
      },
      {
        "state": "CT",
        "billNumber": "HB-5352",
        "billId": 82680
      },
      {
        "state": "CT",
        "billNumber": "HB-6486",
        "billId": 82796
      },
      {
        "state": "DC",
        "billNumber": "D.C. Law 24-320",
        "billId": 104190
      },
      {
        "state": "MD",
        "billNumber": "SB-686",
        "billId": 72278
      },
      {
        "state": "ME",
        "billNumber": "LD-1519",
        "billId": 81678
      },
      {
        "state": "MN",
        "billNumber": "HF-3320",
        "billId": 82543
      },
      {
        "state": "NJ",
        "billNumber": "S-3399",
        "billId": 104171
      },
      {
        "state": "NY",
        "billNumber": "A-1209",
        "billId": 1444
      },
      {
        "state": "NY",
        "billNumber": "A-8195",
        "billId": 60357
      },
      {
        "state": "NY",
        "billNumber": "S-10168",
        "billId": 79613
      },
      {
        "state": "NY",
        "billNumber": "S-1460",
        "billId": 81668
      },
      {
        "state": "NY",
        "billNumber": "S-1463",
        "billId": 1424
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 104184
      },
      {
        "state": "NY",
        "billNumber": "S-5663",
        "billId": 72875
      },
      {
        "state": "NY",
        "billNumber": "S-7552",
        "billId": 60359
      },
      {
        "state": "NY",
        "billNumber": "S-7553",
        "billId": 1162
      },
      {
        "state": "OR",
        "billNumber": "HB-3220",
        "billId": 80376
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 72412
      },
      {
        "state": "OR",
        "billNumber": "SB-582",
        "billId": 72452
      },
      {
        "state": "VT",
        "billNumber": "H-915",
        "billId": 1213
      },
      {
        "state": "WA",
        "billNumber": "SB-5144",
        "billId": 104189
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 104217
      },
      {
        "state": "ME",
        "billNumber": "LD-1541",
        "billId": 79534
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      },
      {
        "state": "MN",
        "billNumber": "HF-4565",
        "billId": 1221
      },
      {
        "state": "NY",
        "billNumber": "A-6193",
        "billId": 60356
      },
      {
        "state": "VT",
        "billNumber": "H-142",
        "billId": 72481
      },
      {
        "state": "VT",
        "billNumber": "S-217",
        "billId": 72345
      },
      {
        "state": "ME",
        "billNumber": "LD-1423",
        "billId": 80310
      },
      {
        "state": "VT",
        "billNumber": "S-254",
        "billId": 81811
      },
      {
        "state": "RI",
        "billNumber": "HB-6207",
        "billId": 82640
      },
      {
        "state": "RI",
        "billNumber": "SB-996",
        "billId": 79521
      },
      {
        "state": "MN",
        "billNumber": "SF-4679",
        "billId": 1222
      }
    ]
  },
  {
    "lever": "recycled_content",
    "name": "Recycled Content",
    "headline": "Incorporate post-consumer recycled content",
    "direction": "Incorporate minimum postconsumer recycled content percentages.",
    "focus": [
      "Packaging",
      "Plastic products",
      "Textiles"
    ],
    "billCount": 15,
    "states": [
      "CA",
      "CO",
      "ME",
      "MN",
      "NY",
      "OR",
      "VT"
    ],
    "evidence": {
      "state": "CA",
      "bill": "AB-661",
      "quote": "Products in revised SABRC product categories with minimum recycled content percentages (effective January 1, 2023)"
    },
    "bills": [
      {
        "state": "CA",
        "billNumber": "AB-661",
        "billId": 83365
      },
      {
        "state": "CA",
        "billNumber": "SB-1013",
        "billId": 851
      },
      {
        "state": "CA",
        "billNumber": "SB-303",
        "billId": 733
      },
      {
        "state": "CA",
        "billNumber": "SB-38",
        "billId": 82353
      },
      {
        "state": "CA",
        "billNumber": "SB-54",
        "billId": 865
      },
      {
        "state": "ME",
        "billNumber": "LD-1467",
        "billId": 72366
      },
      {
        "state": "NY",
        "billNumber": "S-10168",
        "billId": 79613
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 104184
      },
      {
        "state": "ME",
        "billNumber": "LD-1541",
        "billId": 79534
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      },
      {
        "state": "NY",
        "billNumber": "A-6193",
        "billId": 60356
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 72412
      },
      {
        "state": "VT",
        "billNumber": "H-142",
        "billId": 72481
      },
      {
        "state": "VT",
        "billNumber": "H-915",
        "billId": 1213
      },
      {
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433
      }
    ]
  },
  {
    "lever": "source_reduction",
    "name": "Source Reduction",
    "headline": "Reduce packaging material per unit (lightweight, right-size)",
    "direction": "Achieve source reduction targets for covered plastic packaging.",
    "focus": [
      "Plastic packaging"
    ],
    "billCount": 12,
    "states": [
      "CA",
      "CO",
      "ME",
      "MN",
      "OR",
      "VT",
      "WA"
    ],
    "evidence": {
      "state": "CA",
      "bill": "SB-303",
      "quote": "Achieve source reduction targets for covered plastic packaging"
    },
    "bills": [
      {
        "state": "CA",
        "billNumber": "AB-1857",
        "billId": 82616
      },
      {
        "state": "CA",
        "billNumber": "SB-303",
        "billId": 733
      },
      {
        "state": "CA",
        "billNumber": "SB-54",
        "billId": 865
      },
      {
        "state": "CO",
        "billNumber": "HB-22-1355",
        "billId": 72416
      },
      {
        "state": "CA",
        "billNumber": "AB-863",
        "billId": 79950
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 72412
      },
      {
        "state": "VT",
        "billNumber": "H-142",
        "billId": 72481
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 104217
      },
      {
        "state": "ME",
        "billNumber": "LD-1541",
        "billId": 79534
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      },
      {
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433
      },
      {
        "state": "OR",
        "billNumber": "SB-582",
        "billId": 72452
      }
    ]
  },
  {
    "lever": "reuse_refill",
    "name": "Reuse & Refill",
    "headline": "Shift to reusable / refillable formats",
    "direction": "Design glass beverage containers for washing and refill cycles.",
    "focus": [
      "Beverage containers",
      "Foodware"
    ],
    "billCount": 10,
    "states": [
      "CA",
      "CO",
      "CT",
      "ME",
      "MN",
      "NY",
      "OR",
      "WA"
    ],
    "evidence": {
      "state": "CA",
      "bill": "AB-962",
      "quote": "Beverage manufacturers must have their reusable glass beverage containers processed by a certified processor for subsequent washing for refill and sale"
    },
    "bills": [
      {
        "state": "CA",
        "billNumber": "AB-962",
        "billId": 79926
      },
      {
        "state": "CA",
        "billNumber": "SB-1143",
        "billId": 83174
      },
      {
        "state": "CA",
        "billNumber": "SB-560",
        "billId": 720
      },
      {
        "state": "CT",
        "billNumber": "HB-5142",
        "billId": 82844
      },
      {
        "state": "NY",
        "billNumber": "A-8195",
        "billId": 60357
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 104217
      },
      {
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433
      },
      {
        "state": "OR",
        "billNumber": "SB-582",
        "billId": 72452
      },
      {
        "state": "ME",
        "billNumber": "LD-1909",
        "billId": 83470
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      }
    ]
  },
  {
    "lever": "toxics_elimination",
    "name": "Toxics Elimination",
    "headline": "Eliminate restricted substances (PFAS, heavy metals, etc.)",
    "direction": "Eliminate mercury from thermostat designs; transition to mercury-free alternatives.",
    "focus": [
      "Packaging",
      "Electronics",
      "Textiles"
    ],
    "billCount": 20,
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
      "VT",
      "WA"
    ],
    "evidence": {
      "state": "CA",
      "bill": "AB-732",
      "quote": "mercury-added thermostats"
    },
    "bills": [
      {
        "state": "CO",
        "billNumber": "SB-25-163",
        "billId": 82272
      },
      {
        "state": "KY",
        "billNumber": "SB-49",
        "billId": 80507
      },
      {
        "state": "ME",
        "billNumber": "LD-474",
        "billId": 104191
      },
      {
        "state": "MN",
        "billNumber": "HF-4565",
        "billId": 1221
      },
      {
        "state": "MN",
        "billNumber": "SF-4679",
        "billId": 1222
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 104184
      },
      {
        "state": "OR",
        "billNumber": "HB-4144",
        "billId": 82947
      },
      {
        "state": "WA",
        "billNumber": "SB-5144",
        "billId": 104189
      },
      {
        "state": "ME",
        "billNumber": "LD-1541",
        "billId": 79534
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      },
      {
        "state": "OR",
        "billNumber": "HB-3780",
        "billId": 72412
      },
      {
        "state": "VT",
        "billNumber": "H-142",
        "billId": 72481
      },
      {
        "state": "CA",
        "billNumber": "AB-707",
        "billId": 80248
      },
      {
        "state": "MD",
        "billNumber": "SB-686",
        "billId": 72278
      },
      {
        "state": "NY",
        "billNumber": "A-10284",
        "billId": 80208
      },
      {
        "state": "OR",
        "billNumber": "HB-3220",
        "billId": 80376
      },
      {
        "state": "CA",
        "billNumber": "AB-732",
        "billId": 80259
      },
      {
        "state": "NY",
        "billNumber": "S-10168",
        "billId": 79613
      },
      {
        "state": "CT",
        "billNumber": "HB-5019",
        "billId": 81565
      },
      {
        "state": "VT",
        "billNumber": "S-254",
        "billId": 81811
      }
    ]
  },
  {
    "lever": "material_restriction",
    "name": "Material Restrictions",
    "headline": "Avoid banned / restricted materials and formats",
    "direction": "Eliminate or reduce problematic or unnecessary plastic packaging.",
    "focus": [
      "Plastic packaging",
      "Textiles"
    ],
    "billCount": 15,
    "states": [
      "CA",
      "CO",
      "ME",
      "MN",
      "NY",
      "RI",
      "SC",
      "VT",
      "WA"
    ],
    "evidence": {
      "state": "CA",
      "bill": "SB-303",
      "quote": "Eliminate or reduce problematic or unnecessary plastic packaging"
    },
    "bills": [
      {
        "state": "CA",
        "billNumber": "SB-279",
        "billId": 103008
      },
      {
        "state": "CO",
        "billNumber": "HB-21-1162",
        "billId": 72433
      },
      {
        "state": "ME",
        "billNumber": "LD-754",
        "billId": 72241
      },
      {
        "state": "NY",
        "billNumber": "A-7912",
        "billId": 83358
      },
      {
        "state": "VT",
        "billNumber": "H-142",
        "billId": 72481
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 104217
      },
      {
        "state": "CO",
        "billNumber": "HB-22-1355",
        "billId": 72416
      },
      {
        "state": "ME",
        "billNumber": "LD-1467",
        "billId": 72366
      },
      {
        "state": "SC",
        "billNumber": "S-171",
        "billId": 104219
      },
      {
        "state": "CA",
        "billNumber": "SB-303",
        "billId": 733
      },
      {
        "state": "MN",
        "billNumber": "HF-3911",
        "billId": 104216
      },
      {
        "state": "RI",
        "billNumber": "SB-996",
        "billId": 79521
      },
      {
        "state": "CA",
        "billNumber": "AB-962",
        "billId": 79926
      },
      {
        "state": "CO",
        "billNumber": "HB22-1355",
        "billId": 104215
      },
      {
        "state": "VT",
        "billNumber": "H-915",
        "billId": 1213
      }
    ]
  },
  {
    "lever": "labeling_marking",
    "name": "Labeling & Marking",
    "headline": "Apply required recyclability / disposal labeling",
    "direction": "Mark containers with refund value indicator per Section 14560 requirements.",
    "focus": [
      "Packaging",
      "Beverage containers",
      "Textiles"
    ],
    "billCount": 27,
    "states": [
      "CA",
      "CT",
      "DC",
      "IL",
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
    },
    "bills": [
      {
        "state": "CA",
        "billNumber": "AB-1311",
        "billId": 81168
      },
      {
        "state": "CA",
        "billNumber": "AB-1478",
        "billId": 80300
      },
      {
        "state": "CA",
        "billNumber": "SB-1013",
        "billId": 851
      },
      {
        "state": "CA",
        "billNumber": "SB-1215",
        "billId": 797
      },
      {
        "state": "CA",
        "billNumber": "SB-343",
        "billId": 81917
      },
      {
        "state": "CA",
        "billNumber": "SB-814",
        "billId": 742
      },
      {
        "state": "CT",
        "billNumber": "HB-5019",
        "billId": 81565
      },
      {
        "state": "DC",
        "billNumber": "D.C. Law 24-320",
        "billId": 104190
      },
      {
        "state": "IL",
        "billNumber": "SB-294",
        "billId": 81244
      },
      {
        "state": "KY",
        "billNumber": "SB-49",
        "billId": 80507
      },
      {
        "state": "MD",
        "billNumber": "SB-686",
        "billId": 72278
      },
      {
        "state": "ME",
        "billNumber": "LD-1564",
        "billId": 83401
      },
      {
        "state": "ME",
        "billNumber": "LD-1909",
        "billId": 83470
      },
      {
        "state": "MI",
        "billNumber": "SB-416",
        "billId": 73159
      },
      {
        "state": "MN",
        "billNumber": "HF-4565",
        "billId": 1221
      },
      {
        "state": "MN",
        "billNumber": "SF-4679",
        "billId": 1222
      },
      {
        "state": "NY",
        "billNumber": "A-7912",
        "billId": 83358
      },
      {
        "state": "NY",
        "billNumber": "A-8195",
        "billId": 60357
      },
      {
        "state": "NY",
        "billNumber": "S-10168",
        "billId": 79613
      },
      {
        "state": "NY",
        "billNumber": "S-7552",
        "billId": 60359
      },
      {
        "state": "OR",
        "billNumber": "SB-123",
        "billId": 82818
      },
      {
        "state": "OR",
        "billNumber": "SB-1520",
        "billId": 83268
      },
      {
        "state": "RI",
        "billNumber": "HB-5017",
        "billId": 80689
      },
      {
        "state": "VT",
        "billNumber": "H-175",
        "billId": 72450
      },
      {
        "state": "VT",
        "billNumber": "H-915",
        "billId": 1213
      },
      {
        "state": "CA",
        "billNumber": "SB-560",
        "billId": 720
      },
      {
        "state": "NY",
        "billNumber": "S-5663",
        "billId": 72875
      }
    ]
  },
  {
    "lever": "compostability",
    "name": "Compostability",
    "headline": "Use certified-compostable materials where specified",
    "direction": "Make covered material compostable as alternative to recyclable.",
    "focus": [
      "Foodware",
      "Packaging"
    ],
    "billCount": 5,
    "states": [
      "CA",
      "WA"
    ],
    "evidence": {
      "state": "CA",
      "bill": "SB-54",
      "quote": "Ensure covered material offered for sale, distributed, or imported in or into the state on or after January 1, 2032, is recyclable or compostable"
    },
    "bills": [
      {
        "state": "CA",
        "billNumber": "AB-1857",
        "billId": 82616
      },
      {
        "state": "CA",
        "billNumber": "SB-54",
        "billId": 865
      },
      {
        "state": "WA",
        "billNumber": "SB-5284",
        "billId": 104217
      },
      {
        "state": "CA",
        "billNumber": "AB-863",
        "billId": 79950
      },
      {
        "state": "CA",
        "billNumber": "SB-279",
        "billId": 103008
      }
    ]
  },
  {
    "lever": "repairability_durability",
    "name": "Repairability & Durability",
    "headline": "Design for repairability, spare-parts access, and longevity",
    "direction": "Make replacement parts available to independent repair providers and owners.",
    "focus": [
      "Electronics",
      "Appliances",
      "Textiles"
    ],
    "billCount": 32,
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
      "SC",
      "VT",
      "WA"
    ],
    "evidence": {
      "state": "CA",
      "bill": "SB-1384",
      "quote": "Make available to independent repair providers and owners, on fair and reasonable terms and costs, all documentation, parts, embedded software, firmware, and tools intended for use with the equipment or covered parts, including updates"
    },
    "bills": [
      {
        "state": "CA",
        "billNumber": "SB-1384",
        "billId": 82737
      },
      {
        "state": "CA",
        "billNumber": "SB-244",
        "billId": 82438
      },
      {
        "state": "CA",
        "billNumber": "SB-707",
        "billId": 620
      },
      {
        "state": "CO",
        "billNumber": "HB-22-1031",
        "billId": 82800
      },
      {
        "state": "CO",
        "billNumber": "HB-23-1011",
        "billId": 79666
      },
      {
        "state": "CO",
        "billNumber": "HB-24-1121",
        "billId": 81480
      },
      {
        "state": "CT",
        "billNumber": "HB-6512",
        "billId": 72465
      },
      {
        "state": "CT",
        "billNumber": "SB-308",
        "billId": 81673
      },
      {
        "state": "ME",
        "billNumber": "LD-1487",
        "billId": 72511
      },
      {
        "state": "ME",
        "billNumber": "LD-2211",
        "billId": 72480
      },
      {
        "state": "MN",
        "billNumber": "SF-1598",
        "billId": 81821
      },
      {
        "state": "NY",
        "billNumber": "S-4104",
        "billId": 81072
      },
      {
        "state": "NY",
        "billNumber": "S-5027C",
        "billId": 104184
      },
      {
        "state": "OR",
        "billNumber": "SB-1596",
        "billId": 72344
      },
      {
        "state": "OR",
        "billNumber": "SB-550",
        "billId": 83232
      },
      {
        "state": "RI",
        "billNumber": "HB-5017",
        "billId": 80689
      },
      {
        "state": "RI",
        "billNumber": "SB-884",
        "billId": 80226
      },
      {
        "state": "CO",
        "billNumber": "HB-22-1355",
        "billId": 72416
      },
      {
        "state": "CO",
        "billNumber": "SB-25-163",
        "billId": 82272
      },
      {
        "state": "CT",
        "billNumber": "HB-5019",
        "billId": 81565
      },
      {
        "state": "KY",
        "billNumber": "SB-49",
        "billId": 80507
      },
      {
        "state": "ME",
        "billNumber": "LD-1423",
        "billId": 80310
      },
      {
        "state": "ME",
        "billNumber": "LD-1541",
        "billId": 79534
      },
      {
        "state": "OR",
        "billNumber": "HB-4144",
        "billId": 82947
      },
      {
        "state": "VT",
        "billNumber": "S-254",
        "billId": 81811
      },
      {
        "state": "WA",
        "billNumber": "SB-5144",
        "billId": 104189
      },
      {
        "state": "ME",
        "billNumber": "LD-1519",
        "billId": 81678
      },
      {
        "state": "ME",
        "billNumber": "LD-2289",
        "billId": 72520
      },
      {
        "state": "ME",
        "billNumber": "LD-474",
        "billId": 104191
      },
      {
        "state": "NY",
        "billNumber": "A-6193",
        "billId": 60356
      },
      {
        "state": "SC",
        "billNumber": "S-171",
        "billId": 104219
      },
      {
        "state": "MN",
        "billNumber": "HF-4565",
        "billId": 1221
      }
    ]
  }
];
