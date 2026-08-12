# US Packaging EPR & Related Obligations — Major Franchised QSR Chain

**Research pass:** 2026-08-11 · **Method:** primary-source research (state agency pages, statutes,
CAA fee-schedule PDFs parsed with `pypdf`). The 200-call web-search cap was exhausted during this
pass. · **Status:** point-in-time snapshot, not maintained.

> **How to use this.** "Unverified" means exactly that — nothing was invented. The three CAA fee
> schedules were parsed from source PDFs, not summarised. Encoded into
> `app/scoring/producer_attribution.py` (all seven states) and `dashboard-next/src/lib/feeSchedule.ts`
> (Oregon + Colorado PY2026 tables). See `docs/EXPOSURE_CALCULATOR_SPEC.md`.

---

## 0. Headline findings

1. **The producer question is not the same question in every state, and in Oregon the answer is "not
   you."** Five of seven states (CO, ME, MN, MD, WA) have an explicit *franchisor* attribution clause.
   California reaches the franchisor via the **regulations**, not the statute. **Oregon uses a
   completely different mechanism** — the producer of food serviceware is "the person that first sells
   the food serviceware in or into this state," i.e. the *supplier*, even for logo-branded cups.
2. **Three states have real published rate tables, not two.** Oregon PY2026 and Colorado PY2026 are
   binding, published and currently being invoiced. California's are illustrative until October 2026.
3. **Most registration and reporting deadlines have already passed** in CA, CO, OR, MD, MN and WA.
4. **California's PPMF component fee is charged per plastic *unit*, not per pound.** Every lid, straw,
   sauce cup and cutlery piece is a separate chargeable component. For a QSR this may exceed the
   weight-based fee. No tonne-based model can express it.

---

## 1–4. Per-state table

| | **California** | **Oregon** | **Colorado** | **Maine** | **Minnesota** | **Maryland** | **Washington** |
|---|---|---|---|---|---|---|---|
| **Statute** | SB 54 / PRC 42040 ff.; regs eff. **1 May 2026** | SB 582 / ORS 459A.860–.975 | HB22-1355 / C.R.S. 25-17-701 ff. | 38 M.R.S. §2146 | Minn. Stat. 115A.1441 ff. | Md. Env't §§9-2501–2512 | Ch. 70A.208 RCW |
| **Food-service ware covered?** | **Yes — plastic FSW is its own covered-material class.** Fiber-only FSW with no plastic is *not* covered | **Yes — broadest.** "Food serviceware" is a standalone covered-product class: *paper or plastic* plates, wraps, cups, bowls, pizza boxes, cutlery, straws, lids, bags, foil, clamshells | **Yes, expressly** — "products supplied to or purchased by consumers for the express purpose of facilitating food or beverage consumption" | Yes, via broad "packaging material"; no FSW carve-out found | Yes — "'Packaging'… **includes food packaging**"; incorporates 325F.075 | **Yes, enumerated** — "service packaging designed and intended to be filled at the point of sale, including carry-out bags… **take-out and home delivery food service packaging**" | Yes, by general definition ("**serve**… sold or supplied with the product"); no enumeration |
| **Cutlery / straws** | **In** — regs name "utensils, stirrers… straws" | **In** — statute names cutlery, straws | In substance; not itemized — *unverified* | *Unverified* | *Unverified* | *Unverified* | *Unverified* |
| **Producer for a franchised chain** | **Franchisor.** 14 CCR §18980.2(d)(3)(C): a person "is not the producer if it acquired the right to use the brand… under an agreement, such as a sublicense or **franchise agreement**… That other person… is the producer." §18980.2(e)(1): for FSW the designated brand is "the brand… directly associated with food or food service" | **The supplier/distributor.** ORS 459A.866(3): "The producer of food serviceware is **the person that first sells the food serviceware in or into this state**." CAA's worked example: branded bowls made for a restaurant → the *packaging company* (or its distributor) is obligated | **Franchisor.** 6 CCR 1007-2 §18.2.2(D)(3): "Where the producer is a business operated wholly or in part as a franchise, the producer is the **franchisor**, if that franchisor has franchisees that operate in Colorado" | **Franchisor** if franchisees operate in Maine. §2146 also permits **reassignment by signed agreement** | **Franchisor.** "If the producer… is a business operated wholly or in part as a franchise, the producer is the franchisor if that franchisor has franchisees that have a **commercial presence within the state**" | **Franchisor.** §9-2501(p)(1)(vi), same "commercial presence in the State" trigger | **Franchisor.** RCW 70A.208.020(29)(a)(vi)(B), identical wording. **(A) allows contractual reassignment** if the assignee joins the PRO and you certify in writing |
| **Restaurant carve-out?** | Franchisee is *not* the producer (rolls up). No restaurant exemption for the brand owner | **Yes, and it's the crux.** Small producer includes "a restaurant, food cart or similar business establishment… **and** is not a producer of food serviceware." DEQ: "DEQ presumes that **many fast food franchisors would NOT be exempt** because they do not operate restaurants directly" | Exempts "an **individual business** operating a retail food establishment" — aimed at the single licensed store | *Unverified* | **None** | Yes, but requires **Maryland headquarters** + not a producer of food serviceware. Also excludes single stores "not… part of a franchise or a chain" | **None** |
| **Small-producer / de-minimis** | **<$1,000,000 gross sales *in California***, most recent CY (PRC 42060(a)(5)(A)). **No tonnage de minimis.** Application-based, 2-yr validity | **<$5M gross *GLOBAL* revenue** *or* <1 metric tonne into OR *or* restaurant test *or* single non-franchise store. **Affiliates aggregated** (OAR 340-090-0860(5)) | **<$5M realized gross total revenue** (excl. on-premises alcohol) *or* **<1 ton** into CO. CPI-adjusted annually — **current figure unverified** | **<$2M/yr** (<$5M for first 3 yrs) *or* **<1 ton**. Plus **first 15 tons/yr of perishable-food packaging exempt** | **<1 ton into MN** *or* **<$2,000,000 global gross revenue** | **<1 ton into MD** *or* **<$2,000,000 global gross revenue** — lowest in the US | **<1 ton** *or* **<$5,000,000 global gross revenue, excluding on-premises alcohol** |
| **Registration** | **1 Jun 2026 — PASSED** | **31 Mar 2025 — PASSED** | **1 Oct 2024 — PASSED** | Not open (no SO contracted) | **1 Jul 2025 — PASSED** | **31 May / 1 Jul 2026 — PASSED** | **1 Jan 2026 (statute) / 1 Jul 2026 (CAA) — PASSED** |
| **First report** | **1 Jul 2026 — PASSED** | 31 Mar 2025; annual **31 May — PASSED** | **31 Jul 2025 — PASSED** | May 31 (post-contract) | 2029 | 31 May 2026 — PASSED | 31 May 2026 interim |
| **First fees** | Mar 2027 (PPMF) / Jul 2027 (admin); full program 2027 | **1 Jul 2025 — LIVE.** PY2026 instalments: 50% at +45 days, **50% by 30 Jul 2026** | **1 Jan 2026 — LIVE** | 180 days after SO contract | **2029** | **1 Jul 2028** (≥50% cost/ton) | **2030** (≥90%) |
| **Published rate table?** | **No — illustrative only** | **YES — binding** | **YES — binding** | No | No | No | No |
| **Report to** | CalRecycle (PRO reports for members) | CAA | CAA | DEP-procured Stewardship Organization (**not CAA**) | CAA | CAA | CAA |

**Enforcement is already live in two states.** Oregon DEQ flagged ~250 producers for RMA non-compliance
in April 2026. Colorado registration closed October 2024 — a chain that missed it is non-compliant
*now*, not merely late.

---

## 5. Fee schedules — what is actually published

Only three exist. All three parsed from the source PDFs.

- **Oregon PY2026** — CAA, published 29 Oct 2025, `circularactionalliance.org/s/OR-2026-Fee-Schedule-Public.pdf`
  (302-redirects to Squarespace). Binding. `Base + SIM = Final`; SIM is 0.0¢/lb on every row this year.
- **Colorado PY2026** — CAA, published 13 Oct 2025, `.../CO-2026-Dues-Schedule-Public.pdf`. Binding.
  Columns: Base Dues, Detriments Malus, Not-on-MRL Malus, High-Recycling-Rate Bonus, Final Dues —
  passive eco-modulation **already baked into the published Final**.
- **California 2027** — CAA "California Illustrative Fees" v1.0, 1 May 2026. Explicitly *"not final
  fees… good faith, non-binding."* Final rates arrive with the program plan in **October 2026**.

### The QSR SKUs, side by side (¢/lb)

| Food-service item | **OR 2026 final** | **CO 2026 final** | **CA 2027 illustrative base (low → high)** |
|---|---|---|---|
| Poly-coated paperboard — hot/cold paper cups | **48.0** (on neither list) | **20.0** (AML) | **6 → 16** |
| Plain paperboard / folding carton | 8.0 | 8.0 | 1–2 → 5 |
| Corrugated | 8.0 (0.0 non-consumer transport) | 8.0 | 2 → 6 |
| Kraft paper (bags, wraps) | 8.0 | 8.0 | 2–3 → 7 |
| Molded fiber / pulp foodservice | — | **26.0** (own line) | 2–6 → 17 |
| PET rigid cups/lids/trays | **57.0** thermoform / **60.0** lids | 17.0 clear / **50.0** pigmented | 12 → 36 |
| PP rigid cups/lids/trays | **62.0** containers / **29.0** lids | 20.0 | 11 → 24 |
| **PS foam containers/cups/trays** | **138.0** | **172.0** | **47 → 127** |
| PP/PS utensils | 28.0 (small format) | 52.0 (small format) | **29 → 78/79** |
| HDPE/LDPE film & bags | 43.0 | 48.0 | 28–29 → 74–76 |
| PP film / laminate wrappers | **102.0** | 64.0 / 74.0 | 31–58 → 80–148 |
| Aluminum foil & molded containers | 24.0 | 34.0 | 7–10 → 17–24 |
| **Compostable (PLA/PHA) rigid** | **97.0** | **27.0** (D6400) | 18 → 53 |
| **Compostable flexible** | **102.0** | **31.0** (D6400) | 49 → 120 |
| Glass bottles/jars | 10.0 | 4.0 | 1 → ~3 |
| Aluminum cans | 6.0 | 2.0 | 4–5 → ~12 |

**Plus, in California only**, on every plastic-component pound and unit:

- Reuse Investment Fee **4¢/lb (low) → 10¢/lb (high)**
- PPMF Weight-Based **17¢/lb → 25¢/lb** (80% of the $500M/yr fund, allocated by plastic weight)
- **PPMF Component-Based `$0.0010 → $0.0012` per plastic component *unit*** (20% of the fund, by piece count)

**Flat-fee options** (define the small-producer floor): Oregon $1,200 / $2,500 / $4,100 / $5,800 for
1–2.5 / 2.5–5 / 5–7.5 / 7.5–10 MT. Colorado $800 / $1,600 / $2,600 / $3,600 for the same short-ton
bands. Maine caps low-volume producers at **$500/ton and $7,500/yr total**.

### Three design signals the numbers give you

- **Foam is punished everywhere** — 138¢/lb OR, 172¢/lb CO, 127¢/lb CA-high. In Colorado that is 8.6×
  the clear-PET cup.
- **The paper hot cup is priced completely differently in each state.** Oregon puts poly-coated
  paperboard on *neither* acceptance list at 48¢/lb; Colorado has it on the AML at 20¢/lb; California
  illustratively at 6¢/lb. Same cup, 8× spread, driven by each state's collection lists — not the cup.
- **"Switch to compostable" is not a universal saving.** Oregon penalises PLA at 97–102¢/lb (accepted
  nowhere); Colorado prices certified compostables at 26–32¢/lb, *cheaper* than foam but *more* than
  PP/PET. A national compostables strategy raises Oregon fees.

---

## 6. What must be reported

- **California** (14 CCR §18980.10.2(a)), per covered material category: total **weight** supplied;
  **total number of plastic components**; weight disposed; weight recycled. Annually by 1 July, to
  CalRecycle, certified; the PRO reports for its members; errors correctable within 14 days.
- **Oregon**: weight by covered-product type and CAA material category, to **CAA** by 31 May. Fee years
  lag the data year — 2024 supply data set both PY2025 *and* PY2026 fees (OAR 340-090-0700(3)).
- **Colorado**: types and quantities of packaging, paper and food serviceware supplied into CO, to CAA,
  in the dues-schedule taxonomy.
- **Maryland / Washington**: registration + brand lists now; detailed categories not finalised (MD is on
  **eight broad categories** for the 2026 interim report). MD's PRO must file "a list of the **brands**
  of each producer."
- **Minnesota / Maine**: producer-level fields not yet fixed; both await plan approval / rulemaking.

**Common denominator: weight × material category × brand × state.** Build the data model to that grain
now — the categories will harden state-by-state and retrofitting is worse than over-collecting.

---

## 7. Beyond EPR — what else hits a restaurant chain

### Real, near-term money

- **CA SB 343 truth-in-labeling — compliance date 4 October 2026.** A chasing-arrows mark or
  recyclability claim is lawful only if the material is collected by programs covering ≥60% of the CA
  population *and* sorted by facilities serving ≥60% of programs. Keys to **date of manufacture**, not
  sale, so pre-Oct-4 stock remains sellable — a genuine pre-buy window. Statutory fines are small
  ($500/$1,000/$2,000) but **private UCL enforcement at $2,500/violation** is the real exposure.
- **PFAS-in-food-packaging bans.** Twelve states enacted (CA, CO, CT, HI, ME, MD, MN, NY, OR, RI, VT,
  WA). Verified directly: **Oregon SB 543 §4 bans intentionally added PFAS in foodware from 1 Jan 2025**
  (seller penalty up to $500/day) — *the same act and same date as its foam ban*. CA caps
  compostable-labeled products and recyclability-claimed plastic at **100 ppm total organic fluorine**.
  See the companion PFAS brief for the full state-by-state detail.
- **EPS/foam foodservice bans, in force:** MD (2020), ME (2021), NY (2022, cold storage added 2026), NJ
  (2022; raw-meat carve-out **already expired** May 2024), WA (2024), CO (2024), OR (2025), **CA (1 Jan
  2025 — triggered, not dated:** CalRecycle found the 25% EPS recycling rate unmet, AG enforcement
  advisory 2 Dec 2025; **$50,000/day** under PRC 42081), VA (20+ locations Jul 2025, all Jul 2026), DE
  (penalties from Jul 2026), VT.
- **NJ recycled-content: the food-package exemption expires January 2027.**
- **Carryout bags.** CA SB 1053 from **1 Jan 2026** bans *all* plastic film carryout bags regardless of
  thickness; paper must be 40% PCR now, **50% from 1 Jan 2028**; ≥$0.10/bag, retained by the store. CA's
  "store" definition does **not** clearly reach restaurants. **Oregon already bans single-use checkout
  bags at restaurants** (ORS 459A.757), tightened by **SB 551 from 1 Jan 2027**. See the companion
  carryout-bag brief.

### Operationally annoying, financially small

- **Accessory-on-request.** CA AB 1276 (PRC 42271, in force 1 Jan 2022) bars providing utensils, straws,
  stirrers, splash sticks, condiment cups **and packets** unless requested; drive-thru and airport
  walk-through may proactively ask; third-party delivery menus must itemise. The **anti-bundling rule
  kills pre-wrapped cutlery kits**. Penalty: two notices then **$25/day capped at $300/year** — trivial.
  **Washington (RCW 70A.245.080) is the one that bites: $150–$2,000 per day.** NYC "Skip the Stuff"
  enforced from Jul 2024 at $50/$150/$250.

### Mostly indirect

- **Bottle bills** (CA, CT, HI, IA, ME, MA, MI, NY, OR, VT + Guam). Usually a pass-through in wholesale
  price. But **Connecticut (10¢ since 1/1/2024) and Massachusetts have no restaurant carve-out** — a
  dine-in QSR may owe redemption. California expressly excludes "any lodging, eating, or drinking
  establishment… for consumption onsite" (PRC 14510). Iowa's exemption carries an affirmative **signage**
  duty; Michigan's evaporates if a franchisee itemises a deposit on a to-go can. **No new deposit state
  was added — WA HB 1607 died in committee 30 Jan 2026**, contrary to several circulating summaries.
- **PCR mandates** bind suppliers/brand owners, not restaurants: CA AB 793 beverage containers
  15%→**25% (from 1/1/2025)**→50% (2030), $0.20/lb shortfall penalty; WA RCW 70A.245.020 beverage
  containers **25% in force since 1/1/2026**→50% (2031); NJ rigid 10% / beverage 15% / glass 35%; CT 25%
  from 1/1/2027 with **registration due 1 Apr 2026**.

**One structural point:** the *franchised, multi-unit* character of the chain is precisely what
disqualifies it from nearly every hardship waiver. New York's foam waiver says "non-franchised" in terms;
Maryland's and Oregon's single-store exemptions say "not… part of a franchise or a chain."

---

## 8. What a naive "EPR fee per tonne" calculator gets materially wrong

1. **It assumes you are the producer.** In Oregon you probably are not. A tonne-based calculator would
   bill a QSR chain for Oregon fees it does not owe, while missing that the *same* chain owes CA/CO/MD/WA
   fees at franchisor level for the identical cup.
2. **It has no franchise layer.** Five states aggregate the whole franchise system's tonnage at the
   franchisor, so thresholds are tested at system level. A per-store model exempts everyone.
3. **It ignores piece count.** California's PPMF component fee is **per plastic component unit**. At a
   billion lids/straws/sauce cups a year that is $1.0–1.2M before a single pound is weighed.
4. **It treats "plastic" as one rate.** PET clear vs pigmented is 17¢ vs 50¢ in Colorado; PP lids vs PP
   containers is 29¢ vs 62¢ in Oregon. **The lid is often a different rate from the cup it fits.**
5. **It prices the same SKU identically across states.** The driver is the **state's collection list**,
   not the packaging.
6. **It assumes the fee schedule exists.** Four of seven states have no rate table at all.
7. **It misses flat-fee and tiered alternatives**, the Maine caps and the 15-ton perishable exemption.
8. **It ignores fee-year lag.** Oregon set both PY2025 and PY2026 fees off 2024 supply data.
9. **It ignores exemption orphaning.** Oregon DEQ: if the first seller is a small producer, the products
   are "**orphaned** — no fees are paid." Neither pushed up nor down. A naive model invents a liability
   that legally does not exist.
10. **It prices only EPR.** PFAS substitution, foam replacement and SB 343 artwork rework are plausibly
    larger line items — and a foam→grease-proof-paper switch can create a *second* violation in Oregon,
    where foam and PFAS were banned by the same act on the same day.
11. **It omits eco-modulation shape.** Colorado bakes passive modulation into published Final Dues (+5%
    detriments, −5% high recycling rate, AML ≥20% above MRL) and offers four *active* incentives;
    Oregon's SIM column is 0.0 this year but is a live mechanism; California's plastic adders are
    flat-rate. Three different arithmetic shapes.

---

## 9. Where the repo had fallen behind reality (as found)

- **`scheduleForMarket()` in `feeSchedule.ts` routed every US state to the CA flagship** on the stated
  grounds that CA is the only detailed US schedule. False — **Oregon and Colorado both have binding
  published tables**, both *more* authoritative than California's. **Fixed 2026-08-11.**
- **`ca_sb54_fees.py` and `FALLBACK_PALETTE` numbers are stale and one is mislabelled.** The `98`
  described as "PP bottle / PS foam" corresponds to *Other/Mixed Plastics — Textiles*. Published
  low-scenario reads: PET clear bottles 11, HDPE bottles 13, PP other rigid cups/lids 11, PET other
  rigid cups/lids 12, PS foam 47, PP/PS utensils 29, cardboard 2, paperboard 1, aluminum non-aerosol
  4–5, poly-coated paperboard 6. `HIGH_SCENARIO_MULTIPLIER = 2.5` is low; observed ratios ~2.7–3.0×.
  **NOT fixed** — the CAA source PDF could not be retrieved to verify, and a rate is never taken from a
  summary.
- **No per-unit fee dimension.** The PPMF component-based fee has no home in a model that never carries
  a piece count on the input side. **Still open.**
- **No producer-attribution layer.** **Built 2026-08-11** as `app/scoring/producer_attribution.py`.

**One thing `docs/PRO_TARIFF_INGESTION_PLAN.md` got right and should be kept:** the
`status: illustrative | confirmed` distinction, and "a rate is never LLM-extracted." Both proved
load-bearing — CA is illustrative, OR and CO are confirmed, and the difference is the whole story.

---

## 10. Open items

- **PFAS effective dates for nine states** (WA, ME, MN, NY, VT, CT, RI, MD, CO) — largest cost driver.
- **Carryout-bag rules for the 12 non-CA states**, specifically *whether restaurants are covered*.
- **Cutlery/straw coverage in CO, ME, MN, MD, WA** — not resolved on any statute's face.
- **Colorado's current CPI-adjusted revenue threshold** (base $5M, adjusted annually from July 2023).
- **Maine's Stewardship Organization RFP status** — no contract as of May 2026; all Maine clocks run
  from contract execution.
- **Oregon PY2025 per-material rates** — portal-gated, `OR-2025-Fee-Schedule-Public.pdf` 404s.
- **Whether CalRecycle required a 2023 baseline report** in addition to the 1 Jul 2026 annual — law-firm
  alerts say yes, the regulation text says "previous calendar year."
- **Oregon's RMA is under constitutional challenge** (filed July 2025, dormant Commerce Clause / First
  Amendment, still pending). Obligations are not suspended.
