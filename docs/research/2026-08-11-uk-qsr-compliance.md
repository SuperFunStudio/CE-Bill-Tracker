# UK Packaging Compliance — Major Restaurant / QSR Chain

**Research pass:** 2026-08-11 · **Method:** primary-source research (gov.uk, legislation.gov.uk,
HMRC, PackUK). The session's 200-call web-search cap was hit partway; the remainder was completed by
direct fetch of primary sources. · **Status:** point-in-time snapshot, not maintained.

> **How to use this.** Every figure is tagged **[CONFIRMED]**, **[ILLUSTRATIVE]**, **[PROPOSED]** or
> **[UNVERIFIED]**. Unverified means it was *not* confirmed against a primary source — a lead, not a
> fact. Encoded into `app/scoring/producer_attribution.py` (UK pEPR + PPT entries) and
> `dashboard-next/src/lib/feeSchedule.ts` (RAM escalator). See `docs/EXPOSURE_CALCULATOR_SPEC.md`.

---

## 1. Who is the obligated producer in a franchised chain

### The general test

A business is an obligated **producer** if it carries out one of the statutory producer activities,
defined as separate classes at regs. 15–22: **Brand owners (16), Packer/fillers (17), Importers and
first UK owners (18), Distributors (19), Online marketplace operators (20), Service providers (21),
Sellers (22)** ([SI 2024/1332 contents](https://www.legislation.gov.uk/uksi/2024/1332/contents/made)).
Guidance frames these as: supplying packaged goods under your own brand, placing goods into
packaging, importing packaged products, owning an online marketplace, hiring/loaning reusable
packaging, supplying empty packaging
([gov.uk: who is affected](https://www.gov.uk/guidance/extended-producer-responsibility-for-packaging-who-is-affected-and-what-to-do)).

For a QSR chain **two activities usually bite at once**: brand owner (branded cups, clamshells, bags)
and packer/filler (the outlet physically fills the cup and box). Only one entity carries the financial
obligation per item; for branded product the brand owner is normally liable
([RPC](https://www.rpclegal.com/thinking/consumer-brands-and-retail/what-if-the-ceo-asks-me-about-our-exposure-to-packaging-fees-under-epr/)).

### The franchise-specific rule — the part calculators miss

**Regulation 102** states: *"(1) Part 1 of Schedule 10 applies to licensors. (2) Part 2 of Schedule 10
applies to pub operating businesses."*
([reg. 102](https://www.legislation.gov.uk/uksi/2024/1332/regulation/102/made))

**Schedule 10 Part 1** ([text](https://www.legislation.gov.uk/uksi/2024/1332/schedule/10/made)) defines
a **licence agreement** as one permitting a licensee to use the licensor's trade mark as a business
name, including an obligation relating to *the presentation of those premises* — a classic franchise
agreement. It creates two "cases" in which the **licensor (franchisor)** must collect and report data
on its licensees' packaging:

- **Case 1:** franchisor meets the turnover threshold but not the tonnage threshold on its own; its
  franchisees are producers without obligations; **combined** packaging meets the tonnage threshold.
- **Case 2:** franchisor already has producer responsibility obligations; its franchisees are producers
  **below** threshold; the franchisees' packaging in aggregate meets the threshold.

Duties on the franchisor: collect the Schedule 4 para. 11 data for packaging bearing its trade mark
**and** for goods franchisees are required by agreement to buy from the franchisor or its nominated
suppliers; **"use its best endeavours to obtain from its licensees the data"**; document estimates
where actuals are unobtainable; **retain records for at least 7 years**; report annually to the
appropriate agency (plus EA reporting for plastic/paper bags supplied in England).

**Practical answer for a 200+ outlet chain: both, but not for the same tonnage.**

- A franchisee independently exceeding £2m turnover **and** 50t is a **large producer in its own
  right** and registers and reports itself.
- Sub-threshold franchisees are **swept up into the franchisor's return** under Schedule 10 Part 1 —
  a deliberate anti-fragmentation device. A chain cannot escape pEPR by having 200 small franchise
  companies.
- Company-owned outlets sit in the corporate group: **add up turnover and packaging weight for all
  group members**; if the group crosses thresholds, each member carrying out packaging activities must
  comply.
- Franchise relationships are flagged explicitly in the reporting file: the groups/subsidiaries spec
  has a **`franchisee_licensee_tenant`** column — *"Enter 'Y' if the child entity is a franchisee,
  licensee or tenant"*
  ([gov.uk](https://www.gov.uk/government/publications/groups-and-subsidiaries-how-to-create-your-file-for-extended-producer-responsibility)).

> **[UNVERIFIED] — the single most important open question in this brief.** Whether the franchisor also
> *pays disposal fees* on swept-up licensee tonnage, or merely *reports* it, is not stated explicitly in
> the Schedule 10 text retrieved. The detailed regulator position lives in the *"Agreed positions and
> technical interpretations"* document on the National Packaging Waste Database
> ([NPWD guidance](https://npwd.environment-agency.gov.uk/public/Guidance.aspx?CategoryId=41fc1dbb-47a2-47fd-bb82-4938d83729e0))
> — the PDF is image-based and could not be extracted. **This must be resolved before any exposure
> model is trusted**, because it decides whether franchisee tonnage lands on the franchisor's P&L.

### Thresholds **[CONFIRMED]**

Turnover is based on your most recent annual accounts up to 7 April; tonnage on the previous calendar
year. Both tests must be met.

| Class | Turnover | Tonnage | Obligations |
|---|---|---|---|
| **Large producer** | ≥ £2m | > 50t | Register, report **half-yearly**, pay waste disposal fees, pay scheme admin costs, obtain PRNs/PERNs, report nation data, **do RAM assessments** |
| **Small producer** | £1m–£2m **or** > £1m | > 25t **or** 25–50t | Register, report **annually**. **No disposal fees, no PRNs.** RAM not required |
| **No obligation** | < £1m | **or** < 25t | None |

Sources: [gov.uk who is affected](https://www.gov.uk/guidance/extended-producer-responsibility-for-packaging-who-is-affected-and-what-to-do),
[gov.uk small producer](https://www.gov.uk/guidance/epr-for-packaging-what-you-must-do-as-a-small-producer).

> ⚠️ **Calculator trap:** the £1m/£2m turnover test is *entity-level*, but the tonnage sweep-up is
> *network-level*. A model asking "what's your turnover and tonnage?" and returning one number is wrong
> for any franchised estate.

---

## 2. Household vs non-household — the biggest cost driver

Waste disposal fees are charged **only on household packaging** (plus commonly-binned packaging and
household glass drinks containers)
([fees guidance](https://www.gov.uk/guidance/extended-producer-responsibility-for-packaging-recycling-obligations-and-waste-disposal-fees)).
Non-household packaging attracts **no disposal fee** — but still counts toward the tonnage threshold
and the PRN obligation.

The [assessment guidance](https://www.gov.uk/guidance/extended-producer-responsibility-for-packaging-how-to-assess-household-and-non-household-packaging)
is explicit for QSR. **Example 5 (fast-food packaging):**

> *"As the consumer is the final user of the packaging not a business and the food product is not
> designed for business use only, all of the primary packaging, used by both the dine in and takeaway
> customers must be classified as household packaging."*

**Dine-in packaging is household too.** There is no eat-in/takeaway discount. Takeaway cups, clamshells,
wraps, carrier bags, condiment sachets, lids and straws consumed on premises — all household, all
fee-bearing.

**Back-of-house / transit packaging** goes the other way. **Example 6:** a producer supplying spices to
a restaurant that does not pass the packaging on to customers can classify it **non-household if it can
evidence this**. Bulk sauce drums, case cardboard and pallet wrap arriving at outlets are non-household
— *and are normally the supplier's obligation, not yours*, unless you self-import or supply under your
own brand.

The default rule is adverse: **primary and shipment packaging must be classed as household unless** you
supply directly to a business/public-institution end user, or supply indirectly where the product is
designed for business-only use and is not reasonably likely to be binned domestically or in a public bin.

> ⚠️ **Trap 1:** any tool letting a user tag dine-in packaging as "non-household" produces a materially
> understated number.
> ⚠️ **Trap 2:** the **`PB` (public bin)** packaging type code exists separately from `HH`. Year-1 fees
> explicitly **excluded** the costs of packaging binned in public bins or littered
> ([2025 base fees](https://www.gov.uk/government/publications/extended-producer-responsibility-for-packaging-2025-base-fees/extended-producer-responsibility-for-packaging-2025-base-fees)).
> QSR packaging is disproportionately public-bin/litter, so **the sector's fees are structurally
> understated in Y1 and the Y2 increases hit it hardest.** A year-on-year model assuming a flat cost
> basis will understate.

---

## 3. What must be submitted, in what format, when

### Format **[CONFIRMED]**

A single **CSV** uploaded to the "Report packaging data" service. Columns, in order
([file spec](https://www.gov.uk/government/publications/packaging-data-how-to-create-your-file-for-extended-producer-responsibility/file-specification-for-packaging-data-from-2025)):

`organisation_id` · `subsidiary_id` · `organisation_size` (S/L) · `submission_period` ·
`packaging_activity` · `packaging_type` · `packaging_class` · `packaging_material` ·
`packaging_material_subtype` · `from_country` · `to_country` · `packaging_material_weight` ·
`packaging_material_units` · `transitional_packaging_units` · `ram_rag_rating`

Allowed codes — **Activity:** `SO` `PF` `IM` `SE` `HL` `OM` · **Type:** `HH` `NH` `CW` `OW` `PB` `RU`
`HDC` `NDC` `SP` `CLR` · **Class:** `P1`–`P6`, `O1` `O2` `B1` · **Material:** `AL` `FC` `GL` `PC` `PL`
`ST` `WD` `OT` · **RAM:** `R` `A` `G` `R-M` `A-M` `G-M` · **Nation:** `EN` `NI` `SC` `WS`

Weights in **whole kilograms**. Plastic must be split **rigid / flexible** for household and public-bin
packaging. Units counts required for drinks containers. `transitional_packaging_units` left blank for
2025/2026 data.

### Calendar **[CONFIRMED]**

| Duty | Large producer | Small producer |
|---|---|---|
| Data: Jan–Jun (H1) | **1 October same year** | n/a |
| Data: Jul–Dec (H2) | **1 April following year** | full year by **1 April following year** |
| 2026 registration data | **1 October 2025** | April 2026 |
| 2025 data resubmissions needing new evidence | **1 April 2026** | — |
| Recycling obligation (PRN/PERN) evidence, year to 31 Dec | **31 January following year** | n/a |
| First mandatory plastic/paper bag report (2026 data, England) | **1 April 2027** | — |

### Hard cut-offs that determine your bill **[CONFIRMED]**

From the [PackUK operational plan 2026–27](https://www.gov.uk/government/publications/packuk-operational-plan/packuk-operational-plan-2026-to-2027):

- *"After 1 May 2026, PackUK will not generally consider any new data submitted for the 2026 to 2027
  assessment year."*
- *"PackUK will not recalculate a notice of liability for producers who have resubmitted packaging data
  after 1 September 2026."*
- Fees for 2026–27 calculated in **November 2026**; **initial notice of liability by end of November 2026**.
- **RAM 2027 to be published by 1 July 2026.**

> ⚠️ These two dates (1 May, 1 Sep 2026) mean data errors become **permanently priced in**. A tool that
> models fees but not the correction window misses the real risk.

### Registration fees **[CONFIRMED, with a discrepancy]**

2026 rates per [registration guidance](https://www.gov.uk/guidance/register-with-the-environmental-regulator-extended-producer-responsibility-for-packaging):
small **£1,303** direct / **£696** via compliance scheme; large **£2,842** direct / **£1,803** via
scheme; **late fee £386**; **closed-loop packaging waste £2,548/yr** (large only).
The [small-producer page](https://www.gov.uk/guidance/epr-for-packaging-what-you-must-do-as-a-small-producer)
states **£1,216 / £631** — likely the 2025 figures. **Verify against the current page before use.**

---

## 4. Base fees and RAM modulation

### Year 1 (2025–26) — **[CONFIRMED]**, published 30 June 2025

| Material | £/tonne |
|---|---|
| Aluminium | 266 |
| Fibre-based composite | 461 |
| Glass | 192 |
| Paper and card | 196 |
| Plastic | 423 |
| Steel | 259 |
| Wood | 280 |
| Other | 259 |

*"For the first year of EPR for packaging (2025 to 2026), costs associated with the management of
packaging commonly disposed of in public bins or littered will not be included."* First invoices
October 2025.

### Year 2 (2026–27) — **[ILLUSTRATIVE ONLY]**, published 19 December 2025

| Material | Green | Amber | Red |
|---|---|---|---|
| Aluminium | 245 | 270 | 325 |
| Fibre-based composite | 475 | 525 | 630 |
| Glass | 185 | 205 | 245 |
| Paper & board | 190 | 210 | 250 |
| Plastic | 415 | 455 | 545 |
| Steel | 260 | 290 | 345 |
| Wood | 410 | 450 | 540 |
| Other | 205 | 225 | 270 |

PackUK describes these as *"best estimates"* and *"likely to change significantly as producers submit
more data."*
([Year 2 illustrative fees](https://www.gov.uk/government/publications/year-2-illustrative-waste-disposal-fees-extended-producer-responsibility-for-packaging/year-2-illustrative-waste-disposal-fees-extended-producer-responsibility-for-packaging))

**Status as at Aug 2026:** the December 2025 document said confirmed Y2 fees were expected **June 2026**;
the PackUK operational plan says fees are **calculated in November 2026**. **Could not verify that
confirmed 2026–27 fees have been published** (search budget exhausted). **Treat Y2 as unconfirmed** and
check [the announcements page](https://www.gov.uk/government/news/extended-producer-responsibility-for-packaging-announcements).

### RAM modulation — **[CONFIRMED as policy, in force from Y2]**

From the [modulation statement](https://www.gov.uk/government/publications/extended-producer-responsibility-for-packaging-modulated-disposal-fees/packuk-extended-producer-responsibility-epr-for-packaging-producer-disposal-fees-modulation-statement)
(updated 17 Feb 2026):

> *"Modulation will commence from year 2 of the scheme with the first modulated fees applying to
> disposal fee calculations for the 2026 to 2027 financial year (calculated using data relating to
> packaging supplied in 2025)."*

**Red multipliers:** **1.2×** (2026–27) → **1.6×** (2027–28) → **2.0×** (2028–29).

**Green:** not a fixed multiplier. The red premium forms a redistribution pot applied as an **equal
percentage discount across all green-rated materials** — PackUK estimates ~**9%** off amber for Y2, but
the actual discount is **arithmetically dependent on the red/amber/green mix of the whole market**, so
it cannot be known in advance.

**Scope:** household packaging only, across the 8 material categories. Medical packaging has separate
codes (`R-M`/`A-M`/`G-M`).

**RAM versions** ([RAM 2027 overview](https://www.gov.uk/government/publications/assess-packaging-recyclability-recyclability-assessment-methodology-ram-2027/ram-2027-overview),
updated 2 July 2026): **RAM v1.1** for the **2026** reporting year; **RAM 2027** for the **2027**
reporting year. Only **large producers** must assess. Scope is household packaging **including household
glass drinks containers and packaging that commonly ends up in public bins**. Reusable/refillable
packaging assessed once on first supply. Take-back-scheme evidence can exempt from materials assessment.

> ⚠️ **Four severe traps here:**
> 1. **The green discount is not knowable ex ante.** Any tool quoting "green = amber × 0.91" presents a
>    market-dependent estimate as a rate.
> 2. **Two-year lag.** 2025 packaging drives 2026–27 fees. A design change today does not move the bill
>    for ~18 months. A calculator showing instant savings from a redesign is wrong about *when*.
> 3. **RAM is component-level, not pack-level.** A cup, its lid and its sleeve can carry different RAG
>    ratings; you rate components then aggregate. A per-tonne-per-material model cannot express this.
> 4. **The 1.2×→1.6×→2.0× escalator** means red-rated exposure roughly *doubles* by 2028–29 with zero
>    change in tonnage. QSR formats (PE-lined paper cups, black plastic, composite clamshells, laminated
>    wraps) skew red.

---

## 5. Plastic Packaging Tax — separate tax, separate regulator

[gov.uk / HMRC](https://www.gov.uk/guidance/check-if-you-need-to-register-for-plastic-packaging-tax)

| Item | Position |
|---|---|
| **Rate from 1 April 2026** | **£228.82/tonne** **[CONFIRMED]** |
| Prior rates | £223.69 (Apr 2025), £217.85 (2024), £210.82 (2023), £200.00 (2022) |
| **Charge basis** | Finished plastic packaging components containing **< 30% recycled plastic by weight** |
| **Registration threshold** | **10 tonnes** of finished plastic packaging components manufactured in or imported into the UK — expected *in the next 30 days* or actual *in the last 12 months* (rolling) |
| **Who registers** | **Manufacturers and importers.** Not "users" of packaging |
| **Returns** | Regular filing cycle with records, accounts and **supply-chain due diligence checks** |

**How it interacts with pEPR — it doesn't, and that's the point:**

| | pEPR | PPT |
|---|---|---|
| Regulator | PackUK / EA, SEPA, NRW, NIEA | HMRC |
| Trigger | Supplying packaging to the UK market | Manufacturing or importing plastic components |
| Threshold | £1m/£2m turnover + 25t/50t | 10t plastic, no turnover test |
| Basis | Weight × material × household/non-household × RAG | Weight × <30% recycled content |
| Payable by a QSR chain? | **Yes** on branded household packaging | **Only if you import or manufacture** |

> ⚠️ These are **cumulative, not alternative**. Non-recycled plastic in a cup lid can attract *both* PPT
> (if you import it) and a red-rated pEPR fee. **PPT can catch a chain that manufactures nothing** — a
> chain importing own-brand cups directly from an Asian supplier is an importer and hits the 10t test far
> below its pEPR thresholds. The **due diligence obligation** means even buying from UK converters carries
> supply-chain evidence risk. "We don't make packaging so PPT doesn't apply" is the classic error.

---

## 6. Deposit Return Scheme

| Item | Position | Status |
|---|---|---|
| **Launch** | **1 October 2027** | **[CONFIRMED]** — [joint policy statement](https://www.gov.uk/government/publications/deposit-return-scheme-for-drinks-containers-policy-statements/deposit-return-scheme-for-drinks-containers-joint-policy-statement) |
| **Deposit** | **20p flat, all materials and sizes** | **[CONFIRMED]** — announced by Exchange for Change 23 Apr 2026 ([letsrecycle](https://www.letsrecycle.com/news/uk-drs-to-adopt-flat-20p-deposit-across-all-materials/)) |
| **In scope** | PET plastic, steel, aluminium; **150ml–3 litres** | **[CONFIRMED]** |
| **Glass** | Excluded in England / NI / Scotland. **Wales includes glass, initially without a deposit** | **[UNVERIFIED]** — Wales detail from secondary reporting only |
| **Schemes** | Three legally distinct: England+NI (joint), Scotland, Wales | **[CONFIRMED]** |
| **DMO** | **Exchange for Change** for England, Scotland, NI | **[CONFIRMED]** |
| **Producer registration** | Producers, manufacturers, importers and return-point operators must register with the DMO **before 1 October 2027**; unregistered suppliers may not supply in-scope drinks | **[CONFIRMED]** |
| **Producer fees** | No upfront annual registration fee. DMO recovers cost via **per-container producer fees**, material sales revenue and unredeemed deposits | **[CONFIRMED]** |
| **Handling fees** | Not specified in the joint policy statement | **[UNVERIFIED]** — level not yet set |

### What a restaurant chain must actually do

- **Return point obligation: NO (mandatory).** *"Hospitality venues, food-to-go stores, schools, gyms,
  and mobile caterers are NOT required to operate return points but may voluntarily apply."*
  Supermarkets and convenience stores **are** mandatory from day one.
- **Producer obligation: YES, if you supply in-scope containers under your own brand or import them.**
  A chain selling own-brand bottled water or canned soft drinks is a DRS **producer** — register with
  the DMO, apply the deposit, meet labelling requirements, pay per-container fees.
- **Retailer obligation: YES.** You must **charge the 20p deposit** at point of sale on every in-scope
  container sold. For a dine-in venue where the container never leaves, this is a pure margin/price-point
  problem with no offsetting redemption revenue unless you voluntarily host a return point.
- **Low Volume Products** (<5,000 units/yr UK-wide) are exempt from applying the deposit and specific
  labelling but **must still register and report volumes**.

> ⚠️ DRS containers are **also** pEPR-reportable (`HDC`/`NDC` type codes, unit counts required), but
> once DRS is live the funding basis for those containers shifts. A tool treating DRS as "not our
> problem, we're not a supermarket" misses (a) own-brand drinks producer registration, (b) the 20p
> working-capital and pricing impact across 200 outlets, and (c) the on-trade dine-in case where
> deposits are charged but essentially never redeemed.

---

## 7. What a naive "EPR fee calculator" would miss

1. **Franchise sweep-up (Sch. 10 Pt. 1).** Threshold logic is not entity-level for a franchised network.
2. **"Best endeavours" data collection from franchisees.** A *legal* duty to try to obtain licensee data
   and to **document the estimation method** when it can't. An evidence and systems obligation, not a fee.
3. **7-year record retention** under Schedule 10 — outlasts most POS/procurement retention policies.
4. **Correction windows are the real risk, not the rate.** 1 May 2026 and 1 Sep 2026 lock in errors.
5. **Nation-level reporting (`EN`/`NI`/`SC`/`WS`).** A UK chain must split tonnage by nation supplied —
   and by nation *discarded* for self-managed waste. Most chains lack that granularity.
6. **PRN/PERN is a second, separate cost** with a volatile market price on top of disposal fees. 2026
   recycling targets: **paper/board/FBC 77%, glass 76%, aluminium 62%, steel 81%, plastic 57%, wood 46%**.
   PRN prices appear in **no** published fee table.
7. **RAM assessments are a workstream, not a number** — component-level across the whole SKU range,
   redone as RAM versions change, with the methodology moving under you.
8. **Rigid vs flexible plastic split** is mandatory for household/public-bin plastic.
9. **Public-bin / litter costs were excluded from Y1 fees.** The QSR sector's dominant disposal pathway.
   Any trend line built off Y1 is a false baseline.
10. **PPT catches direct importers** at 10t with no turnover test, plus due-diligence obligations.
11. **Single-use plastics bans (England)** — [gov.uk](https://www.gov.uk/guidance/single-use-plastics-bans-and-restrictions).
    **Cutlery, drinks stirrers, balloon sticks and expanded/extruded polystyrene food and drink
    containers are banned outright with no food-service exemption.** Plates/bowls/trays permitted only if
    **pre-filled or filled at point of sale**. Straws only on request and out of sight. **"You cannot buy
    it at any price" — no fee model expresses this.**
12. **Carrier bag charge (England)** — minimum **10p**, all retailers. Retailers with **250+ FTE** must
    record and report bag sales, proceeds and donations **by 31 May each year**. Penalties up to **£5,000**
    (charging/records) or **£20,000** (obstruction). Exemptions for unwrapped food (e.g. chips) mean a
    chain's bag population is *mixed*, requiring per-bag-type classification. **Separately**, pEPR requires
    large producers to report **plastic and paper bags supplied in England to the Environment Agency**,
    first mandatory report for 2026 data due **1 April 2027**.
13. **Devolved divergence.** Four regulators (EA, SEPA, NRW, NIEA), three DRS schemes, different SUP bans
    per nation. A UK-wide chain runs four compliance perimeters.
14. **Simpler Recycling / workplace waste separation (England).** **[UNVERIFIED]** — could not retrieve
    the gov.uk page. A mandatory waste-stream separation regime exists for non-household premises under
    the Environment Act 2021 with staged in-force dates. **Verify before relying on it.** Operational at
    every outlet, entirely outside any EPR fee model.
15. **The PRO transition.** PackUK aimed to appoint a Producer Responsibility Organisation in **March
    2026**; scheme administration may move, changing invoicing and interfaces mid-model.
16. **Compliance scheme vs direct registration** materially changes registration cost (£1,803 vs £2,842
    for a large producer) and who does the work — a build/buy decision no fee calculator surfaces.

---

## 8. Highest-priority open items

| # | Question | Why it matters |
|---|---|---|
| 1 | Does the franchisor **pay disposal fees** on swept-up franchisee tonnage, or only report it? | Decides whether franchise estate tonnage lands on the franchisor's P&L. Source: NPWD *Agreed positions and technical interpretations* (image-based PDF; needs OCR or a direct regulator request) |
| 2 | Have **confirmed 2026–27 base fees** been published? | Operational plan implies Nov 2026; Dec 2025 doc said June 2026. All Y2 modelling is illustrative until resolved |
| 3 | Actual **green discount percentage** for 2026–27 | Market-dependent; ~9% is an estimate, not a rate |
| 4 | **Simpler Recycling** dates and streams | Operational cost at every outlet |
| 5 | Current-year **registration fee** table (£1,303 vs £1,216 discrepancy) | Trivially resolvable, but a wrong constant is a wrong tool |
| 6 | **DRS handling fees** and per-container producer fees | Not yet set; a placeholder here would be fabrication |

---

## Sources

- [SI 2024/1332 — contents](https://www.legislation.gov.uk/uksi/2024/1332/contents/made) ·
  [reg. 102](https://www.legislation.gov.uk/uksi/2024/1332/regulation/102/made) ·
  [Schedule 10](https://www.legislation.gov.uk/uksi/2024/1332/schedule/10/made) ·
  [reg. 34](https://www.legislation.gov.uk/uksi/2024/1332/regulation/34/made)
- [Who is affected](https://www.gov.uk/guidance/extended-producer-responsibility-for-packaging-who-is-affected-and-what-to-do) ·
  [Household vs non-household](https://www.gov.uk/guidance/extended-producer-responsibility-for-packaging-how-to-assess-household-and-non-household-packaging) ·
  [Collecting packaging data](https://www.gov.uk/guidance/how-to-collect-your-packaging-data-for-extended-producer-responsibility)
- [File specification from 2025](https://www.gov.uk/government/publications/packaging-data-how-to-create-your-file-for-extended-producer-responsibility/file-specification-for-packaging-data-from-2025) ·
  [Groups and subsidiaries file spec](https://www.gov.uk/government/publications/groups-and-subsidiaries-how-to-create-your-file-for-extended-producer-responsibility)
- [Register with the regulator](https://www.gov.uk/guidance/register-with-the-environmental-regulator-extended-producer-responsibility-for-packaging) ·
  [Small producer duties](https://www.gov.uk/guidance/epr-for-packaging-what-you-must-do-as-a-small-producer) ·
  [Recycling obligations and disposal fees](https://www.gov.uk/guidance/extended-producer-responsibility-for-packaging-recycling-obligations-and-waste-disposal-fees)
- [2025 base fees](https://www.gov.uk/government/publications/extended-producer-responsibility-for-packaging-2025-base-fees/extended-producer-responsibility-for-packaging-2025-base-fees) ·
  [Year 2 illustrative fees](https://www.gov.uk/government/publications/year-2-illustrative-waste-disposal-fees-extended-producer-responsibility-for-packaging/year-2-illustrative-waste-disposal-fees-extended-producer-responsibility-for-packaging) ·
  [Modulation statement](https://www.gov.uk/government/publications/extended-producer-responsibility-for-packaging-modulated-disposal-fees/packuk-extended-producer-responsibility-epr-for-packaging-producer-disposal-fees-modulation-statement)
- [PackUK operational plan 2026–27](https://www.gov.uk/government/publications/packuk-operational-plan/packuk-operational-plan-2026-to-2027) ·
  [RAM 2027 overview](https://www.gov.uk/government/publications/assess-packaging-recyclability-recyclability-assessment-methodology-ram-2027/ram-2027-overview)
- [Plastic Packaging Tax registration](https://www.gov.uk/guidance/check-if-you-need-to-register-for-plastic-packaging-tax)
- [DRS joint policy statement](https://www.gov.uk/government/publications/deposit-return-scheme-for-drinks-containers-policy-statements/deposit-return-scheme-for-drinks-containers-joint-policy-statement) ·
  [20p deposit confirmed](https://www.letsrecycle.com/news/uk-drs-to-adopt-flat-20p-deposit-across-all-materials/)
- [Single-use plastics bans](https://www.gov.uk/guidance/single-use-plastics-bans-and-restrictions) ·
  [Carrier bag charges](https://www.gov.uk/guidance/carrier-bag-charges-retailers-responsibilities)
- [pEPR announcements](https://www.gov.uk/government/news/extended-producer-responsibility-for-packaging-announcements) ·
  [NPWD agreed positions](https://npwd.environment-agency.gov.uk/public/Guidance.aspx?CategoryId=41fc1dbb-47a2-47fd-bb82-4938d83729e0) ·
  [PackUK £63m shortfall](https://www.letsrecycle.com/news/packuk-confirms-shortfall-as-63m-announces-year-2-recovery-target/)
