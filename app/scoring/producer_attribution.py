"""Producer attribution — WHO owes the obligation, per jurisdiction and per regime.

WHY THIS EXISTS
---------------
Every packaging-EPR tool on the market prices materials. They all assume you already
know you are the obligated party. For a franchised restaurant chain that assumption is
wrong often enough to invert the answer:

  * Oregon  — the producer of FOOD SERVICEWARE is "the person that first sells the food
              serviceware in or into this state" (ORS 459A.866(3)). That is the SUPPLIER,
              even for cups carrying the chain's logo. The chain may owe nothing.
  * Colorado, Maine, Minnesota, Maryland, Washington — the producer is expressly the
              FRANCHISOR where franchisees operate in the state.
  * California — reaches the franchisor too, but through the regulations, not the statute.
  * UK       — sub-threshold franchisees are swept into the FRANCHISOR's return
              (reg. 102 -> Schedule 10 Part 1).

So the same chain, for the identical cup, is liable in five US states and (probably) not
liable in Oregon. A model that prices tonnage without resolving attribution first will
invoice a customer for fees they do not legally owe, and miss ones they do.

Attribution is also SOURCING-SENSITIVE in Europe: buying from a domestic supplier can
discharge the obligation entirely (Italy's *prima cessione*, Spain art. 28.1, Germany's
pre-12-Aug-2026 §7(2) route), while importing or own-branding the same item makes the
chain the producer. The input is entity structure + sourcing route, not volume.

DISCIPLINE
----------
This module is CURATED LEGAL REFERENCE DATA, in the same spirit as ca_sb54_fees.py.
Rules of the road, all deliberate:

  1. Every rule carries an article-level `citation`. Where a verbatim `quote` was captured
     from the primary source it is stored; where it wasn't, `quote` is None rather than a
     paraphrase dressed up as a quotation.
  2. `confidence` records WHERE the rule lives — statutory / regulatory / guidance — because
     a regulation can be amended far more easily than a statute, and guidance binds nobody.
  3. Where the answer is genuinely unresolved it is `unresolved` with the question recorded
     in `open_questions`. A confident wrong answer here is worse than an admission of doubt.
  4. Penalty and threshold figures are NEVER transplanted from an adjacent subtitle of the
     same act. (Trade coverage widely misreports the Colorado and Maryland PFAS penalties
     by quoting the firefighting-foam and rug-and-carpet provisions of those bills.)

See docs/EXPOSURE_CALCULATOR_SPEC.md §3. Research date for all entries: 2026-08-11.
"""
from __future__ import annotations

from typing import Any, Literal

# --- Vocabulary ------------------------------------------------------------------

# How the obligation attaches. These are the six mechanisms actually observed; they are
# not interchangeable synonyms for "producer".
AttributionRule = Literal[
    "franchisor",           # the brand licensor answers for its franchisees' packaging
    "first_seller",         # whoever first sells the item into the jurisdiction (OR foodserviceware)
    "brand_owner",          # the party whose brand the packaging carries
    "packer_filler",        # whoever puts the product into the packaging (often the outlet)
    "importer",             # importer / intra-EU acquirer / first UK owner
    "supplier_discharged",  # a domestic supplier discharges it upstream; the buyer files nothing
]

# Where the rule lives. Drives how much weight the UI puts on it.
Confidence = Literal["statutory", "regulatory", "guidance", "unresolved"]

# Regimes are separate because attribution differs BY REGIME within one jurisdiction.
# California exempts restaurants from its carryout-bag law ("store" under PRC 42280(f)
# means grocers, large retail with a pharmacy, or Type 20/21 licensees) while covering
# restaurant foodservice ware under SB 54. Same state, opposite answers.
Regime = Literal[
    "packaging_epr",
    "plastic_tax",
    "sup_levy",
    "drs",
    "carryout_bag",
]

# How a chain sources the item — flips the answer in DE / IT / ES.
SourcingRoute = Literal["domestic_supplier", "self_import", "own_brand"]

# Threshold models. US states exempt you for falling BELOW any one test; the UK sorts
# producers into tiers; Ireland obligates only when BOTH limbs are met.
ThresholdModel = Literal["exempt_below_any", "obligated_above_all", "tiered"]


# --- The dataset -----------------------------------------------------------------
# Keyed (jurisdiction, regime). Jurisdiction codes match feeSchedule.ts: 'US-OR', 'UK', 'FR'.

ATTRIBUTION: dict[tuple[str, str], dict[str, Any]] = {
    # ---------------------------------------------------------------- UNITED STATES
    ("US-CA", "packaging_epr"): {
        "jurisdiction_label": "California (SB 54)",
        "rule": "franchisor",
        "confidence": "regulatory",  # in the regs, NOT the statute — amendable more easily
        "citation": "14 CCR §18980.2(d)(3)(C); §18980.2(e)(1) (food service ware brand test)",
        "quote": (
            "is not the producer if it acquired the right to use the brand… under an agreement, "
            "such as a sublicense or franchise agreement… That other person… is the producer."
        ),
        "franchised_chain_liable_party": "franchisor",
        "sourcing_sensitive": False,
        "covers_food_service_ware": True,
        "food_service_ware_note": (
            "Plastic food service ware is its own covered-material class. Fiber-only FSW with no "
            "plastic component is not covered."
        ),
        "thresholds": {
            "model": "exempt_below_any",
            "tests": [
                {
                    "kind": "turnover",
                    "amount": 1_000_000,
                    "currency": "USD",
                    "basis": "in_jurisdiction",  # California sales only — unusually narrow
                    "citation": "PRC §42060(a)(5)(A)",
                    "note": "Application-based exemption, 2-year validity; CalRecycle may deny.",
                },
            ],
            "no_tonnage_de_minimis": True,
        },
        "exemptions": [],
        "reporting_note": (
            "Reports total WEIGHT supplied and TOTAL NUMBER OF PLASTIC COMPONENTS per covered "
            "material category (14 CCR §18980.10.2(a)) — piece count is a required field, not "
            "an optional one."
        ),
        "source_url": "https://calrecycle.ca.gov/",
        "open_questions": [
            "Whether CalRecycle required a 2023 baseline report in addition to the annual due 1 Jul 2026 — "
            "law-firm alerts say yes, the regulation text says 'previous calendar year'.",
        ],
    },
    ("US-OR", "packaging_epr"): {
        "jurisdiction_label": "Oregon (RMA / SB 582)",
        # The single most consequential entry in this table.
        "rule": "first_seller",
        "confidence": "statutory",
        "citation": "ORS 459A.866(3)",
        "quote": (
            "The producer of food serviceware is the person that first sells the food serviceware "
            "in or into this state."
        ),
        "franchised_chain_liable_party": "supplier",
        "sourcing_sensitive": True,
        "covers_food_service_ware": True,
        "food_service_ware_note": (
            "Broadest FSW definition of the seven states — a standalone covered-product class "
            "covering paper OR plastic plates, wraps, cups, bowls, pizza boxes, cutlery, straws, "
            "lids, bags, foil and clamshells. But the obligation sits on the first seller, so a "
            "restaurant chain buying branded cups from a distributor is NOT the producer of them."
        ),
        "thresholds": {
            "model": "exempt_below_any",
            "tests": [
                {"kind": "turnover", "amount": 5_000_000, "currency": "USD", "basis": "global",
                 "citation": "OAR 340-090-0860", "note": "Affiliates are aggregated (OAR 340-090-0860(5))."},
                {"kind": "tonnage", "amount": 1, "unit": "metric_tonne", "basis": "in_jurisdiction",
                 "citation": "OAR 340-090-0860"},
            ],
        },
        "exemptions": [
            {
                "kind": "restaurant",
                "applies_to_chain": False,
                "quote": (
                    "a restaurant, food cart or similar business establishment… and is not a producer "
                    "of food serviceware."
                ),
                "note": (
                    "Oregon DEQ guidance: 'DEQ presumes that many fast food franchisors would NOT be "
                    "exempt because they do not operate restaurants directly.' The carve-out is aimed "
                    "at the operator, not the brand."
                ),
                "confidence": "guidance",
            },
            {
                "kind": "single_store",
                "applies_to_chain": False,
                "note": "A single store that is not part of a franchise or a chain — expressly excludes chains.",
            },
        ],
        "orphaning": (
            "Where the first seller is itself a small producer, Oregon DEQ describes the products as "
            "'orphaned' — no fees are paid by anyone, and the obligation is neither pushed up nor down "
            "the chain. 'Nobody owes this' is a real and correct answer here."
        ),
        "source_url": "https://www.oregon.gov/deq/",
        "open_questions": [
            "Oregon's RMA is under constitutional challenge (filed July 2025, dormant Commerce Clause / "
            "First Amendment, still pending as of Aug 2026). Obligations are NOT suspended.",
        ],
    },
    ("US-CO", "packaging_epr"): {
        "jurisdiction_label": "Colorado (HB22-1355)",
        "rule": "franchisor",
        "confidence": "regulatory",
        "citation": "6 CCR 1007-2 §18.2.2(D)(3)",
        "quote": (
            "Where the producer is a business operated wholly or in part as a franchise, the producer "
            "is the franchisor, if that franchisor has franchisees that operate in Colorado"
        ),
        "franchised_chain_liable_party": "franchisor",
        "sourcing_sensitive": False,
        "covers_food_service_ware": True,
        "food_service_ware_note": (
            "Expressly covered — 'products supplied to or purchased by consumers for the express "
            "purpose of facilitating food or beverage consumption'; rule defines service packaging "
            "including cups, plates and containers."
        ),
        "thresholds": {
            "model": "exempt_below_any",
            "tests": [
                {"kind": "turnover", "amount": 5_000_000, "currency": "USD", "basis": "global",
                 "citation": "C.R.S. 25-17-703",
                 "note": "Realized gross total revenue excluding on-premises alcohol. CPI-adjusted "
                         "annually from July 2023 — the CURRENT adjusted figure is unverified."},
                {"kind": "tonnage", "amount": 1, "unit": "short_ton", "basis": "in_jurisdiction",
                 "citation": "C.R.S. 25-17-703"},
            ],
        },
        "exemptions": [
            {
                "kind": "restaurant",
                "applies_to_chain": False,
                "note": (
                    "Exempts 'an individual business operating a retail food establishment' — aimed at "
                    "the single licensed store, not a franchisor."
                ),
            },
        ],
        "source_url": "https://cdphe.colorado.gov/",
        "open_questions": [
            "Current CPI-adjusted revenue threshold (base $5M, adjusted annually from July 2023).",
        ],
    },
    ("US-ME", "packaging_epr"): {
        "jurisdiction_label": "Maine (38 M.R.S. §2146)",
        "rule": "franchisor",
        "confidence": "statutory",
        "citation": "38 M.R.S. §2146",
        "quote": None,
        "franchised_chain_liable_party": "franchisor",
        "sourcing_sensitive": False,
        "covers_food_service_ware": True,
        "reassignment_permitted": (
            "§2146 permits reassignment of the obligation by signed agreement — one of only two states "
            "that do (cf. Washington)."
        ),
        "thresholds": {
            "model": "exempt_below_any",
            "tests": [
                {"kind": "turnover", "amount": 2_000_000, "currency": "USD", "basis": "global",
                 "citation": "38 M.R.S. §2146",
                 "note": "$5,000,000 for the first three program years."},
                {"kind": "tonnage", "amount": 1, "unit": "short_ton", "basis": "in_jurisdiction",
                 "citation": "38 M.R.S. §2146"},
            ],
        },
        "exemptions": [
            {
                "kind": "perishable_food_packaging",
                "applies_to_chain": True,
                "note": "First 15 tons/yr of perishable-food packaging is exempt — genuinely useful to a chain.",
            },
        ],
        "fee_caps": "Low-volume producers capped at $500/ton and $7,500/yr total.",
        "source_url": "https://www.maine.gov/dep/",
        "open_questions": [
            "Maine has not contracted a Stewardship Organization (none as of May 2026) and it is NOT "
            "CAA. Every Maine clock — registration, reporting, first fees — runs from contract execution, "
            "so no date can be quoted yet.",
        ],
    },
    ("US-MN", "packaging_epr"): {
        "jurisdiction_label": "Minnesota (Minn. Stat. 115A.1441)",
        "rule": "franchisor",
        "confidence": "statutory",
        "citation": "Minn. Stat. §115A.1441",
        "quote": (
            "If the producer… is a business operated wholly or in part as a franchise, the producer is "
            "the franchisor if that franchisor has franchisees that have a commercial presence within "
            "the state"
        ),
        "franchised_chain_liable_party": "franchisor",
        "sourcing_sensitive": False,
        "covers_food_service_ware": True,
        "food_service_ware_note": (
            "'Packaging'… includes food packaging; incorporates Minn. Stat. 325F.075 (cups, plates, "
            "bowls, wrappers, bags, tubs)."
        ),
        "thresholds": {
            "model": "exempt_below_any",
            "tests": [
                {"kind": "turnover", "amount": 2_000_000, "currency": "USD", "basis": "global",
                 "citation": "Minn. Stat. §115A.1441"},
                {"kind": "tonnage", "amount": 1, "unit": "short_ton", "basis": "in_jurisdiction",
                 "citation": "Minn. Stat. §115A.1441"},
            ],
        },
        "exemptions": [],  # no restaurant carve-out
        "source_url": "https://www.pca.state.mn.us/",
        "open_questions": [],
    },
    ("US-MD", "packaging_epr"): {
        "jurisdiction_label": "Maryland (Md. Env't §§9-2501–2512)",
        "rule": "franchisor",
        "confidence": "statutory",
        "citation": "Md. Env't §9-2501(p)(1)(vi)",
        "quote": None,
        "franchised_chain_liable_party": "franchisor",
        "sourcing_sensitive": False,
        "covers_food_service_ware": True,
        "food_service_ware_note": (
            "Enumerated: 'service packaging designed and intended to be filled at the point of sale, "
            "including carry-out bags… take-out and home delivery food service packaging'."
        ),
        "thresholds": {
            "model": "exempt_below_any",
            "tests": [
                {"kind": "turnover", "amount": 2_000_000, "currency": "USD", "basis": "global",
                 "citation": "Md. Env't §9-2501", "note": "Lowest revenue threshold in the US, tied with Minnesota."},
                {"kind": "tonnage", "amount": 1, "unit": "short_ton", "basis": "in_jurisdiction",
                 "citation": "Md. Env't §9-2501"},
            ],
        },
        "exemptions": [
            {
                "kind": "restaurant",
                "applies_to_chain": False,
                "note": (
                    "Requires MARYLAND HEADQUARTERS and that the business is not a producer of food "
                    "service ware. Also excludes single stores 'not… part of a franchise or a chain' — "
                    "being a chain is itself disqualifying."
                ),
            },
        ],
        "source_url": "https://mde.maryland.gov/",
        "open_questions": [],
    },
    ("US-WA", "packaging_epr"): {
        "jurisdiction_label": "Washington (ch. 70A.208 RCW)",
        "rule": "franchisor",
        "confidence": "statutory",
        "citation": "RCW 70A.208.020(29)(a)(vi)(B)",
        "quote": None,
        "franchised_chain_liable_party": "franchisor",
        "sourcing_sensitive": False,
        "covers_food_service_ware": True,
        "food_service_ware_note": (
            "Covered by the general definition ('serve'… sold or supplied with the product); no "
            "enumeration and no FSW carve-out."
        ),
        "reassignment_permitted": (
            "RCW 70A.208.020(29)(a)(vi)(A) allows contractual reassignment if the assignee joins the "
            "PRO and the producer certifies the arrangement in writing."
        ),
        "thresholds": {
            "model": "exempt_below_any",
            "tests": [
                {"kind": "turnover", "amount": 5_000_000, "currency": "USD", "basis": "global",
                 "citation": "RCW 70A.208", "note": "Excludes on-premises alcohol sales."},
                {"kind": "tonnage", "amount": 1, "unit": "short_ton", "basis": "in_jurisdiction",
                 "citation": "RCW 70A.208"},
            ],
        },
        "exemptions": [],  # no restaurant carve-out
        "source_url": "https://ecology.wa.gov/",
        "open_questions": [],
    },
    # ------------------------------------------------------------------ UNITED KINGDOM
    ("UK", "packaging_epr"): {
        "jurisdiction_label": "United Kingdom (pEPR, SI 2024/1332)",
        # Two activities usually bite at once for a QSR: brand owner (branded cups) and
        # packer/filler (the outlet fills them). For branded product the brand owner leads.
        "rule": "brand_owner",
        "confidence": "statutory",
        "citation": "SI 2024/1332 regs. 16 (brand owners), 17 (packer/fillers); reg. 102 → Sch. 10 Pt. 1 (licensors)",
        "quote": "(1) Part 1 of Schedule 10 applies to licensors. (2) Part 2 of Schedule 10 applies to pub operating businesses.",
        "franchised_chain_liable_party": "both_split_by_threshold",
        "sourcing_sensitive": False,
        "covers_food_service_ware": True,
        "franchise_mechanism": (
            "Schedule 10 Part 1 is an anti-fragmentation sweep-up, not a simple assignment. A franchisee "
            "that independently exceeds BOTH thresholds registers and reports in its own right. "
            "Sub-threshold franchisees are pulled into the FRANCHISOR's return in two defined cases. "
            "Franchisor duties: collect Schedule 4 para. 11 data for packaging bearing its trade mark and "
            "for goods franchisees must buy from it or its nominated suppliers; 'use its best endeavours "
            "to obtain from its licensees the data'; document estimates where actuals are unobtainable; "
            "retain records for at least 7 YEARS. The reporting file carries an explicit "
            "`franchisee_licensee_tenant` flag."
        ),
        "thresholds": {
            "model": "tiered",
            "tiers": [
                {"tier": "large", "turnover_gte": 2_000_000, "currency": "GBP", "tonnage_gt": 50,
                 "unit": "tonne", "combinator": "and",
                 "obligations": ["register", "report half-yearly", "pay waste disposal fees",
                                 "pay scheme admin costs", "obtain PRNs/PERNs", "report nation data",
                                 "carry out RAM assessments"]},
                {"tier": "small", "turnover_gte": 1_000_000, "currency": "GBP", "tonnage_gt": 25,
                 "unit": "tonne", "combinator": "and",
                 "obligations": ["register", "report annually"],
                 "note": "No disposal fees, no PRNs, no RAM."},
                {"tier": "none", "note": "Below £1m turnover or below 25t."},
            ],
            "aggregation": (
                "Turnover and tonnage are summed across all members of a corporate GROUP; the tonnage "
                "sweep-up under Sch. 10 is NETWORK-level. So an entity-level test alone is wrong for a "
                "franchised estate."
            ),
        },
        "classification_note": (
            "Waste disposal fees are charged only on HOUSEHOLD packaging. gov.uk's worked Example 5 is "
            "fast food and is explicit: 'As the consumer is the final user of the packaging not a "
            "business… all of the primary packaging, used by both the dine in and takeaway customers "
            "must be classified as household packaging.' There is no dine-in discount."
        ),
        "source_url": "https://www.legislation.gov.uk/uksi/2024/1332/contents/made",
        "open_questions": [
            "DECISIVE AND UNRESOLVED: whether a franchisor PAYS disposal fees on swept-up franchisee "
            "tonnage or merely REPORTS it. Determines whether the franchise estate's tonnage lands on "
            "the franchisor's P&L. The regulator position is in the NPWD 'Agreed positions and technical "
            "interpretations' document, an image-based PDF requiring OCR or a direct request.",
        ],
    },
    ("UK", "plastic_tax"): {
        "jurisdiction_label": "United Kingdom (Plastic Packaging Tax)",
        "rule": "importer",
        "confidence": "statutory",
        "citation": "HMRC — Plastic Packaging Tax (registration threshold and rate guidance)",
        "quote": None,
        "franchised_chain_liable_party": "whoever_imports_or_manufactures",
        "sourcing_sensitive": True,
        "covers_food_service_ware": True,
        "thresholds": {
            "model": "obligated_above_all",
            "tests": [
                {"kind": "tonnage", "amount": 10, "unit": "tonne", "basis": "in_jurisdiction",
                 "citation": "HMRC PPT guidance",
                 "note": "Finished plastic packaging components manufactured in or imported into the UK, "
                         "expected in the next 30 days or actual in the last 12 months (rolling). "
                         "NO turnover test."},
            ],
        },
        "rate": {"amount": 228.82, "currency": "GBP", "unit": "tonne", "from": "2026-04-01",
                 "basis": "components containing <30% recycled plastic by weight"},
        "trap": (
            "'We don't make packaging, so PPT doesn't apply' is the classic error. A chain importing its "
            "own-brand cups directly from an overseas supplier IS an importer and hits the 10t test far "
            "below its pEPR thresholds. Buying from a UK converter still carries supply-chain due-diligence "
            "obligations. PPT and pEPR are CUMULATIVE, not alternative — different regulator, different "
            "trigger, different basis."
        ),
        "source_url": "https://www.gov.uk/guidance/check-if-you-need-to-register-for-plastic-packaging-tax",
        "open_questions": [],
    },
    # ------------------------------------------------------------------------- EUROPE
    ("FR", "packaging_epr"): {
        "jurisdiction_label": "France (REP emballages ménagers / Citeo)",
        "rule": "brand_owner",
        "confidence": "regulatory",
        "citation": "C. env. arts. L541-10-13, L541-10-10; loi AGEC 2020-105 art. 62",
        "quote": None,
        "franchised_chain_liable_party": "brand_owner",
        "sourcing_sensitive": True,
        "covers_food_service_ware": True,
        "food_service_ware_note": (
            "Packaging handed to a consumer for takeaway or delivery is HOUSEHOLD packaging "
            "(emballages ménagers), not the professional stream — and the household stream bills per "
            "consumer sales unit (UVC) and per delivered ORDER, not per tonne."
        ),
        "ppwr_shift": (
            "Citeo confirms that from 2026 'les donneurs d'ordre sont systématiquement considérés comme "
            "les producteurs', ending the French exception under which the manufacturer declared "
            "private-label packaging. A chain that relied on suppliers declaring its branded packaging "
            "now declares it itself — a step change in declared volume, not a rate change."
        ),
        "registration_identifier": {
            "name": "IDU (identifiant unique)",
            "format": "15 characters, issued via the éco-organisme, ~5 days from adhesion",
            "scope": "ONE PER FILIÈRE — a chain holds several (ménagers, EPRO, papiers graphiques, "
                     "DEA furniture, DEEE kitchen equipment, TSUU)",
            "display_duty": "Must appear in CGV, contractual documents and on the website.",
            "penalty": "Administrative fine up to €30,000 (art. L541-9-5) plus astreinte up to €20,000/day.",
        },
        "authorised_representative": {
            "required": True,
            "since": "2026-07-10",
            "citation": "C. env. art. L541-10-9-1",
            "note": "Any producer not established in France — EU or third country — must appoint a "
                    "French-established mandataire, subrogated into ALL EPR obligations across all "
                    "filières. A French operating subsidiary that places the packaging is itself the "
                    "producer and needs none.",
        },
        "source_url": "https://filieres-rep.ademe.fr/",
        "open_questions": [
            "Whether H2-2026 EPRO (professional stream) contributions are actually payable — the Ministry "
            "says obligations run from 1 Jan 2027, while Citeo Pro's June 2026 material is already "
            "invoicing 'Éco-contribution 2026 = S2 2026'.",
        ],
    },
    ("DE", "packaging_epr"): {
        "jurisdiction_label": "Germany (VerpackDG, from 12 Aug 2026)",
        "rule": "brand_owner",
        "confidence": "guidance",  # ZSVR PPWR guidance; VerpackDG in force 12 Aug 2026
        "citation": "VerpackDG (BGBl 17 Jul 2026, in force 12 Aug 2026); ZSVR PPWR guidance on Serviceverpackungen",
        "quote": None,
        "franchised_chain_liable_party": "brand_owner",
        "sourcing_sensitive": True,
        "covers_food_service_ware": True,
        "regime_change": (
            "THE BIGGEST RECENT CHANGE IN THIS TABLE. Until 11 Aug 2026 the §7(2) Vorvertreiber route let "
            "a restaurant require its SUPPLIER to take over system participation for Serviceverpackungen "
            "(packaging first filled at the outlet) — though the restaurant still registered in LUCID "
            "itself. From 12 Aug 2026, if the packaging carries the company name, logo or brand, the chain "
            "is BOTH Erzeuger and Hersteller: it must organise system participation itself, register and "
            "report volumes in LUCID, obtain material/weight data from suppliers, and hold the conformity "
            "documentation. NO transition period; non-compliance is a distribution ban. Any model treating "
            "German service packaging as supplier-borne is now wrong for a branded QSR."
        ),
        "registration_identifier": {
            "name": "LUCID (ZSVR packaging register)",
            "cost": "free",
            "note": "Requires all brand names appearing on packaging; the register is public.",
            "penalty": "Up to €100,000 for failure to register; up to €200,000 for failure to participate "
                       "in a system (§36 VerpackG).",
        },
        "authorised_representative": {
            "required": True,
            "since": "2026-08-12",
            "citation": "PPWR Art. 45(3); §5(2) VerpackDG",
            "note": "Existing registrants have until 12 Nov 2026 to notify ZSVR. The AR takes on everything "
                    "EXCEPT the registration itself, which stays personal to the producer. A German GmbH "
                    "means no AR is needed — VAT registration alone is insufficient; a subsidiary does not "
                    "cover the parent.",
            "volatility": "The Commission proposed in December 2025 SUSPENDING the Art. 45 AR obligation "
                          "(models limit it to non-EU firms, or above 50 employees / €10m turnover, possibly "
                          "to 2034). Undecided — treat as a flag, not a constant.",
        },
        "thresholds": {
            "model": "obligated_above_all",
            "tests": [],
            "note": "System participation has no de-minimis. The Vollständigkeitserklärung (audited, due "
                    "15 May, non-extendable) is triggered at 80t glass / 50t paper / 30t ALL OTHER "
                    "MATERIALS COMBINED (§11 VerpackG).",
        },
        "source_url": "https://www.verpackungsregister.org/",
        "open_questions": [
            "Whether VerpackDG carries §§33–34 (Mehrwegangebotspflicht) forward verbatim.",
        ],
    },
    ("ES", "packaging_epr"): {
        "jurisdiction_label": "Spain (RD 1055/2022 / Ecoembes)",
        "rule": "packer_filler",
        "confidence": "regulatory",
        "citation": "RD 1055/2022 arts. 2(e) (envasador), 2(j) (envases de servicio), 28.1",
        "quote": None,
        "franchised_chain_liable_party": "packer_filler",
        "sourcing_sensitive": True,
        "covers_food_service_ware": True,
        "food_service_ware_note": (
            "Takeaway clamshells, cups, bags and trays are 'envases de servicio' (art. 2.j expressly names "
            "bandejas, platos, vasos); the restaurant is the envasador and they sit in the doméstico stream. "
            "Packaging the restaurant consumes internally is 'envase comercial'."
        ),
        "supplier_discharge": (
            "Art. 28.1 sub-2 lets suppliers VOLUNTARILY discharge the obligation in the producer's name, "
            "and most Spanish foodservice suppliers do. So the chain's liability depends on what its "
            "suppliers have agreed to — a contract question, not a volume question."
        ),
        "registration_identifier": {
            "name": "Registro de Productores de Producto, packaging section (MITECO)",
            "format": "ENV/[year]/XXXXXXXXX",
            "display_duty": "Must appear on invoices and all commercial documentation.",
        },
        "authorised_representative": {
            "required": True,
            "citation": "RD 1055/2022 art. 17.2",
            "quote": "deberán designar a una persona física o jurídica en territorio español como "
                     "representante autorizado.",
            "note": "FALLBACK IF NONE APPOINTED: the first Spanish-established distributor becomes "
                    "subsidiarily liable — a clause Spanish suppliers will eventually invoke. A Spanish "
                    "operating subsidiary that hands packaging to consumers is itself the producer.",
        },
        "source_url": "https://www.boe.es/buscar/act.php?id=BOE-A-2022-22690",
        "open_questions": [],
    },
    ("IT", "packaging_epr"): {
        "jurisdiction_label": "Italy (CONAI)",
        "rule": "supplier_discharged",
        "confidence": "guidance",  # CONAI Guide §4.1 prima cessione
        "citation": "CONAI Guida al Contributo Ambientale 2026 §4.1 (prima cessione)",
        "quote": None,
        "franchised_chain_liable_party": "supplier_if_domestic_else_chain",
        "sourcing_sensitive": True,
        "covers_food_service_ware": True,
        "sourcing_matrix": {
            "domestic_supplier": "Supplier declares and pays; the CAC is embedded in the invoice price "
                                 "with mandatory CONAI wording. The restaurant files nothing.",
            "self_import": "Importing EMPTY packaging → the restaurant declares on modulo 6.1. Importing "
                           "PACKAGED GOODS → modulo 6.2.",
            "own_brand": "Own-branding alone does not shift the obligation — prima cessione does. There is "
                         "exactly one first transfer per item on Italian territory.",
        },
        "authorised_representative": {
            "required": False,
            "note": "No mandatory representative. Foreign companies join CONAI voluntarily (fixed quota "
                    "€5.16); non-EU firms without stable Italian representation must post guarantees "
                    "covering ~12 months of expected CAC. If the foreign supplier does not join, the CAC "
                    "falls on the Italian party effecting immissione al consumo.",
        },
        "source_url": "https://www.conai.org/",
        "open_questions": [
            "Arrangements hold until RENAP (art. 178-ter(8) D.Lgs. 152/2006) becomes operational at MASE.",
        ],
    },
    ("IE", "packaging_epr"): {
        "jurisdiction_label": "Ireland (S.I. 282/2014 / Repak)",
        "rule": "brand_owner",
        "confidence": "statutory",
        "citation": "S.I. No. 282/2014 reg. 4(3)(a)",
        "quote": None,
        "franchised_chain_liable_party": "brand_owner",
        "sourcing_sensitive": True,
        "covers_food_service_ware": True,
        "thresholds": {
            "model": "obligated_above_all",  # BOTH limbs, unlike the US states
            "tests": [
                {"kind": "tonnage", "amount": 10, "unit": "tonne", "basis": "in_jurisdiction",
                 "citation": "S.I. 282/2014 reg. 4(3)(a)"},
                {"kind": "turnover", "amount": 1_000_000, "currency": "EUR", "basis": "in_jurisdiction",
                 "citation": "S.I. 282/2014 reg. 4(3)(a)"},
            ],
            "note": "Both limbs cumulative, both measured on activities within the State. CRITICALLY, for "
                    "hospitality ALL products consumed on-site count toward the 10t test — it is not "
                    "limited to takeaway.",
        },
        "membership_trap": (
            "Repak 'Scheduled Membership' (flat fee) is only for a pub/restaurant/hotel that is NEITHER "
            "brandholder NOR importer. A QSR with branded cups and bags, or importing its own packaging, "
            "is a Regular Member on full weight-based fees. Chains get this wrong routinely."
        ),
        "enforcement": "Back fees run up to SIX YEARS; Local Authorities prosecute. Self-compliance was "
                       "removed, so Repak is the only route.",
        "source_url": "https://www.irishstatutebook.ie/eli/2014/si/282/made/en/print",
        "open_questions": [
            "The S.I. that removed self-compliance (reported effective 1 Jan 2023) is unverified.",
        ],
    },
    ("NL", "packaging_epr"): {
        "jurisdiction_label": "Netherlands (Besluit beheer verpakkingen 2014 / Verpact)",
        "rule": "brand_owner",
        "confidence": "statutory",
        "citation": "Besluit beheer verpakkingen 2014, art. 1(g)",
        "quote": None,
        "franchised_chain_liable_party": "brand_owner",
        "sourcing_sensitive": True,
        "covers_food_service_ware": True,
        "thresholds": {
            "model": "exempt_below_any",
            "tests": [
                {"kind": "tonnage", "amount": 50_000, "unit": "kg", "basis": "in_jurisdiction",
                 "citation": "Verpact / Besluit beheer verpakkingen 2014",
                 "note": "50,000 kg is a COMBINED total across all materials, not per material."},
            ],
            "carve_outs": (
                "Two carve-outs put a QSR in scope regardless of tonnage: (a) deposit-bearing bottles and "
                "cans, and (b) ALL single-use plastic packaging — reportable FROM THE FIRST UNIT. SUP is "
                "reported by weight AND item count, and a container with a loose lid counts as TWO items."
            ),
        },
        "authorised_representative": {
            "required": False,
            "note": "Dutch law codifies only the outbound mirror duty. Inbound, a foreign company without "
                    "a Dutch establishment registers directly with Verpact. PPWR Art. 45 from 12 Aug 2026 "
                    "bites only on cross-border distance selling into NL, not on a chain running "
                    "NL-established outlets.",
        },
        "source_url": "https://www.verpact.nl/",
        "open_questions": [],
    },
}


# --- Resolver --------------------------------------------------------------------

def _threshold_summary(thresholds: dict[str, Any] | None) -> str | None:
    """One-line human summary of the threshold model, for UI subtitles."""
    if not thresholds:
        return None
    model = thresholds.get("model")
    if model == "exempt_below_any":
        parts = []
        for t in thresholds.get("tests", []):
            if t["kind"] == "turnover":
                parts.append(f"turnover under {t['amount']:,} {t['currency']} ({t['basis'].replace('_', ' ')})")
            else:
                parts.append(f"under {t['amount']:,} {t.get('unit', 'tonne')} into the jurisdiction")
        return "Exempt if " + " OR ".join(parts) if parts else None
    if model == "obligated_above_all":
        parts = []
        for t in thresholds.get("tests", []):
            unit = t["currency"] if t["kind"] == "turnover" else t.get("unit", "tonne")
            parts.append(f"{t['amount']:,} {unit}")
        return "Obligated only above " + " AND ".join(parts) if parts else None
    if model == "tiered":
        return "Tiered: " + ", ".join(t.get("tier", "?") for t in thresholds.get("tiers", []))
    return None


def resolve_attribution(
    jurisdiction: str,
    regime: str = "packaging_epr",
    *,
    franchised: bool = False,
    sourcing: str | None = None,
) -> dict[str, Any] | None:
    """Who owes the obligation in `jurisdiction` under `regime`, for this business shape.

    `franchised` and `sourcing` do not change the LAW — they select which branch of it
    applies, and they are surfaced in `because` so the answer is auditable rather than
    oracular. Returns None when we hold no cited rule for that pair, which the caller
    must render as "unknown — check this yourself", never as "not obligated".
    """
    entry = ATTRIBUTION.get((jurisdiction, regime))
    if entry is None:
        return None

    rule = entry["rule"]
    liable = entry.get("franchised_chain_liable_party")

    # Build the prose answer. The Oregon branch is the one that inverts.
    if rule == "first_seller":
        because = (
            f"{entry['jurisdiction_label']} attaches the obligation to the first seller into the "
            "jurisdiction, not to the brand. A chain buying this item from a distributor is most "
            "likely NOT the producer — even for own-branded packaging."
        )
    elif rule == "franchisor" and franchised:
        because = (
            f"{entry['jurisdiction_label']} names the franchisor as the producer where franchisees "
            "operate in the jurisdiction, so the whole network's packaging rolls up to the brand."
        )
    elif rule == "supplier_discharged":
        matrix = entry.get("sourcing_matrix", {})
        because = matrix.get(sourcing or "domestic_supplier", entry.get("supplier_discharge", ""))
    else:
        because = entry.get("regime_change") or entry.get("ppwr_shift") or (
            f"{entry['jurisdiction_label']} attaches the obligation via the '{rule}' test."
        )

    return {
        "jurisdiction": jurisdiction,
        "jurisdiction_label": entry["jurisdiction_label"],
        "regime": regime,
        "rule": rule,
        "liable_party": liable,
        "because": because,
        "citation": entry["citation"],
        "quote": entry.get("quote"),
        "confidence": entry["confidence"],
        "sourcing_sensitive": entry.get("sourcing_sensitive", False),
        "covers_food_service_ware": entry.get("covers_food_service_ware"),
        "threshold_summary": _threshold_summary(entry.get("thresholds")),
        "thresholds": entry.get("thresholds"),
        "exemptions": entry.get("exemptions", []),
        "authorised_representative": entry.get("authorised_representative"),
        "registration_identifier": entry.get("registration_identifier"),
        "open_questions": entry.get("open_questions", []),
        "source_url": entry.get("source_url"),
        "notes": {
            k: entry[k]
            for k in (
                "food_service_ware_note", "franchise_mechanism", "classification_note",
                "orphaning", "regime_change", "ppwr_shift", "supplier_discharge",
                "membership_trap", "reassignment_permitted", "reporting_note", "trap",
                "enforcement", "fee_caps",
            )
            if entry.get(k)
        },
    }


def jurisdictions_for_regime(regime: str = "packaging_epr") -> list[str]:
    """Jurisdiction codes for which we hold a cited attribution rule under `regime`."""
    return sorted(j for (j, r) in ATTRIBUTION if r == regime)


def coverage() -> dict[str, Any]:
    """What this table does and does not cover — the honest breadth statement.

    Deliberately reports `unresolved_questions` alongside the counts: a table that hides
    its own gaps invites exactly the false confidence this module exists to prevent.
    """
    regimes: dict[str, list[str]] = {}
    for (j, r) in ATTRIBUTION:
        regimes.setdefault(r, []).append(j)
    return {
        "entries": len(ATTRIBUTION),
        "regimes": {r: sorted(js) for r, js in sorted(regimes.items())},
        "by_confidence": {
            c: sum(1 for e in ATTRIBUTION.values() if e["confidence"] == c)
            for c in ("statutory", "regulatory", "guidance", "unresolved")
        },
        "unresolved_questions": sum(len(e.get("open_questions", [])) for e in ATTRIBUTION.values()),
        "researched": "2026-08-11",
    }
