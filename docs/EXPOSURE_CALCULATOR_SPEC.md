# Obligation & Exposure Engine (`/exposure`) — Spec v2

**Status:** proposed · **v1** 2026-08-11 (fee-calculator framing) · **v2** 2026-08-11, rewritten after
four primary-source research passes (UK, EU member states, US states, practitioner workflow).
**Owner:** kenny
**Depends on:** `dashboard-next/src/lib/feeSchedule.ts`, `GET /compliance/pathways`,
`docs/PRO_TARIFF_INGESTION_PLAN.md`
**Related:** `docs/FEE_DATA_API_SPEC.md`, memory `compliance-action-vision`

---

## 0. What changed from v1, and why

v1 specced a **portfolio fee calculator**: SKUs in, tonnes out, rate applied, annual number, action list.
The research says that product is the wrong one, for three independent reasons.

**It's commoditised.** Twenty-plus vendors ship near-identical fee calculation at $15/month to
demo-gated enterprise — the price spread of a category about to compress. The PROs give it away
outright: Citeo requires **no data at all** below 10,000 consumer sales units (flat €80/yr) and no
detailed data below 500,000; Der Grüne Punkt auto-transfers quantities from your ERP for free.

**Tonnage isn't the billing unit.** In four of six EU markets studied, `€/tonne` has no relationship to
the invoice. France bills household packaging **per consumer sales unit** and delivered food **per
order** (€0.0676–0.1829). The Netherlands bills a **per-1,000-unit** SUP surcharge. California charges
a PPMF component fee **per plastic component unit** — at a billion lids, straws and sauce cups, that is
**$1.0–1.2M before a single pound is weighed**. German municipal packaging tax is **per item**, uncapped
in Freiburg. A tonne-based model cannot express any of these.

**Whether you owe anything at all is the hard question, and nobody sells the answer.** Fourteen law
firms have practices feeding on producer-attribution ambiguity; **zero software vendors address it** —
every platform assumes you already know you're obligated. It is also the question Atlas is uniquely
positioned on: it is a cited-legal-corpus problem, and we have a 40-jurisdiction cited corpus with
pathways, entities and deadlines already attached.

**The v2 thesis:** the wedge is *"are you obligated, on what, and by when"*. The exposure number is the
hook that makes a chain enter its data. The applicability determination, the supplier-document register
and the frozen submission record are what they pay for and renew.

---

## 1. The five things a naive fee calculator gets wrong

Each is evidenced in the research and each forces a structural change.

| # | Finding | Structural consequence |
|---|---|---|
| 1 | **Liability varies by jurisdiction and by sourcing structure.** Oregon: the producer of food serviceware is "the person that first sells… in or into this state" (ORS 459A.866(3)) — the *supplier*, even for logo-branded cups. CO/ME/MN/MD/WA name the **franchisor** explicitly; CA reaches it via 14 CCR §18980.2(d)(3)(C). UK Sch. 10 Pt. 1 sweeps sub-threshold franchisees into the franchisor's return. Germany from 12 Aug 2026: own-branded service packaging makes the chain the producer where its supplier previously licensed it. | **§3 — a producer-attribution layer**, resolved per (entity × jurisdiction × regime × sourcing route). Not a scope checkbox. |
| 2 | **Charges are levied on at least six different bases**, and several are not fees at all. | **§4 — plural charge bases**, incl. piece count on the *input* side. |
| 3 | **Non-EPR charges frequently exceed the EPR fee.** Spain's €0.45/kg plastic tax; Germany's EWKFondsG at €1.236/kg on beverage cups; German municipal tax at €0.50 + €0.50 + €0.20 per item, which alone can exceed €1.50 on one meal. | **§5 — obligation classes**, of which "EPR fee" is one of nine. |
| 4 | **Some obligations have no number at all** — PFAS and EPS bans, format bans, reuse mandates, labelling. "You cannot buy this at any price." | Same — modelled as constraints and workstreams, never as £0. |
| 5 | **Obligations do not only ratchet up.** The Netherlands is abolishing its takeaway charge (planned 1 Jan 2027) and **not enforcing it through end-2026**; France removed five maluses for 2026 including the opaque-PET malus; Ireland's 20c "latte levy" has been imminent since 2021 and is still not commenced. | **§8 — `unenforced` and `contingent` confidence tiers.** A tool that only adds rules overstates exposure. |

---

## 2. Product shape (KISS)

One primary path, everything else progressive disclosure.

```
   60-SECOND PATH                          DEPTH (unlocked as they go)
   ──────────────                          ───────────────────────────
   1. Who are you?         ──────────────► entity tree, franchise model,
      countries + brand model                 turnover per market, AR status
   2. Ten biggest items    ──────────────► CSV/distributor import, full SKU list,
      + rough volumes                         piece counts, supplier register
   3. ANSWER:                             ──► per-line modulation trail, provenance,
      • am I obligated, where, as what        alternative-material curves per market
      • what must I do, by when
      • what will it cost, in a range
```

Screen 3 is the product. Screens 1–2 exist to make it truthful. The number is deliberately **third** —
behind "am I obligated" and "what must I do" — because those are the two answers nobody else sells and
because a chain that has missed a registration deadline does not need a cost forecast, it needs a
lawyer.

### Screens

1. **Profile** — entity tree (franchisor, franchisees, subsidiaries, per-market operating entities),
   franchise model, sourcing route per market (domestic supplier / self-import / own-brand), turnover
   by market. This is short, and it drives everything downstream.
2. **Footprint** — the SKU list. CSV/paste import targeting a **distributor purchase extract** (cases
   by period by DC) rather than an idealised table, because that is the file that exists. Reference
   weights fill the gaps, visibly flagged. Piece counts captured alongside weights.
3. **Obligations** — per (jurisdiction × regime): are you the producer, are you above threshold, what
   must you do, by when, and what is the state of your registration. The centrepiece.
4. **Exposure** — the ledger, in native currency, per charge basis, with the confidence ladder.
5. **Actions** — register / report / reduce / substitute / watch (§9).

---

## 3. Producer attribution — the core layer

This is the thing v1 didn't have and the thing nobody else ships.

> ✅ **BUILT 2026-08-11.** `app/scoring/producer_attribution.py` (curated dataset + resolver),
> `GET /compliance/producer-attribution` (open, unauthenticated — same posture as `/pathways` and
> `/fee-schedule`), 25 tests in `tests/test_api/test_producer_attribution.py`.
> **15 entries** across 14 jurisdictions: 9 statutory, 4 regulatory, 2 guidance, and **9 recorded
> open questions**. The TypeScript sketch below is the shape the client consumes; the Python module
> is the source of truth. Regimes beyond `packaging_epr` and `plastic_tax` are not yet populated.
>
> The endpoint is deliberately open: knowing you are a covered producer in Oregon is the fact that
> makes someone subscribe, so gating it would sell a locked answer to a question the buyer cannot
> yet articulate. An absent (jurisdiction, regime) pair returns **no row**, and callers must render
> that as "unknown — verify this yourself", never as "not obligated". A test asserts the endpoint
> returns 200-with-zero-rows rather than 404 for exactly this reason.

```ts
export type AttributionRule =
  | 'franchisor'        // CO, ME, MN, MD, WA (statute); CA (regulation); UK Sch.10 sweep-up
  | 'first_seller'      // OR food serviceware — ORS 459A.866(3)
  | 'brand_owner'       // UK reg.16; FR donneur d'ordre from 2026; DE own-brand from 12 Aug 2026
  | 'packer_filler'     // UK reg.17; DE Serviceverpackung filled at the outlet
  | 'importer'          // ES plastic tax; DE EWKFondsG; IT modulo 6.1/6.2; UK PPT
  | 'supplier_discharged'; // ES art.28.1; IT prima cessione; DE §7(2) pre-12-Aug-2026

export interface AttributionVerdict {
  jurisdiction: string;
  regime: RegimeId;                  // EPR, plastic tax, DRS, PFAS, labelling…
  rule: AttributionRule;
  liableEntity: string | null;       // which node of the entity tree — null = not you
  because: string;                   // prose, quoting the statutory test
  citation: Citation;                // measure + article, verbatim
  confidence: 'statutory' | 'regulatory' | 'guidance' | 'unresolved';
  sourcingSensitive: boolean;        // true where domestic-buy vs self-import flips the answer
}
```

Three rules the model must respect:

**Attribution is per regime, not per jurisdiction.** California exempts restaurants from its carryout
bag law entirely — "store" under PRC §42280(f) means full-line grocers, large retail with a pharmacy,
or Type 20/21 licensees — while covering restaurant foodservice ware under SB 54. Same state, same
chain, opposite answers.

**Attribution is sourcing-sensitive.** Italy: buying from an Italian supplier embeds the CAC in the
invoice price and the restaurant files nothing; importing empty packaging makes it declare on modulo
6.1. Germany: the §7(2) *Vorvertreiber* route let the supplier license service packaging — and from
**12 August 2026** own-branded packaging makes the chain both *Erzeuger* and *Hersteller*, with **no
transition period**. So the input is entity + sourcing structure, not volume.

**"Not you" is a first-class answer, and so is "nobody".** Oregon DEQ's term for the case where the
first seller is a small producer is **"orphaned"** — no fees are paid, by anyone, and they are neither
pushed up nor down the chain. A model that invents a liability which legally does not exist is as wrong
as one that misses a real one.

### The threshold engine

Thresholds sit under attribution and are tested at the level attribution assigns — which is why a
per-store model exempts everyone and is wrong. Encode only what we can cite; return `unknown` with a
link to the measure otherwise.

Known shape of the variance, all verified: **UK** £2m turnover + 50t (large), £1m + 25t (small), tested
entity-level but with network-level tonnage sweep-up · **CA** <$1m gross sales *in California*, no
tonnage de minimis · **OR/CO/WA** $5m *global* revenue or 1 tonne, affiliates aggregated ·
**MN/MD** $2m global or 1 ton · **ME** $2m + first 15 tons of perishable-food packaging exempt ·
**IE** >10t **and** >€1m, both limbs, both measured in-State, **and for hospitality all on-site
consumption counts** · **NL** 50,000 kg combined across materials — *but deposit containers and all
single-use plastic report from the first unit* · **DE** VE thresholds 80t glass / 50t paper / 30t all
other materials combined.

### Authorised representative

A four-way split, and it is entity-structure-driven: **required** for non-established producers in
France (art. L541-10-9-1, in force 10 July 2026, all filières), Germany (PPWR Art. 45(3) + §5(2)
VerpackDG from 12 Aug 2026, existing registrants notifying ZSVR by 12 Nov 2026) and Spain (RD 1055/2022
art. 17.2 — **with the first Spanish-established distributor subsidiarily liable if none is appointed**);
**not required** in Italy, where CONAI membership is voluntary for foreign firms and the CAC simply
falls on whoever effects *immissione al consumo*. A local operating subsidiary moots the requirement
everywhere.

> ⚠️ Build as a flag, not a constant: the Commission **proposed in December 2025 suspending the Art. 45
> AR obligation** (models under discussion limit it to non-EU firms, or above 50 employees / €10m
> turnover, possibly to 2034). Undecided; the obligation is live now.

---

## 4. Charge bases — plural, from day one

`feeSchedule.ts` carries `RateUnit` on the **rate**. The gap is on the **input**: nothing in the model
carries a piece count, an order count, or a per-site count. All six of these are live today.

```ts
export type ChargeBasis =
  | { kind: 'per_weight'; unit: RateUnit }              // everywhere; the existing path
  | { kind: 'per_component_unit' }                      // CA PPMF $0.0010–0.0012 per plastic component
  | { kind: 'per_thousand_units' }                      // NL SUP-opslag €2.10/1,000
  | { kind: 'per_order' }                               // FR restauration livrée €0.0676–0.1829
  | { kind: 'per_item_at_point_of_sale' }               // DE municipal: €0.50 cup + €0.50 dish + €0.20 cutlery
  | { kind: 'percent_of_value'; note: string }          // IT simplified import 0.19% of net purchase value
  | { kind: 'flat_or_floor'; note: string };            // FR €110 household minimum, €145 Citeo Pro <4t;
                                                        // OR $1,200–5,800, CO $800–3,600 bands;
                                                        // ME caps $500/ton and $7,500/yr
```

Two consequences for the footprint model:

- **Piece count is a required input, not a derived one.** A container with a loose lid counts as **2
  items** for Dutch SUP reporting. California requires "total number of plastic components" reported
  alongside weight (14 CCR §18980.10.2(a)).
- **Assembly complexity is a cost driver independent of weight.** France's litter component scales with
  *unités d'emballage* per consumer sales unit: 0.1722 ct at 1 UE → 1.4293 ct at 20 UE. A burger meal —
  box, cup, lid, straw, bag, sauce sachet — is 6+ UE on one UVC, multiplying that component 4–5× versus
  a single-unit item. No tonnage model sees this.

---

## 5. Obligation classes — nine, of which fees are one

```ts
export type ObligationClass =
  | 'epr_fee'                 // the thing v1 modelled
  | 'eco_tax'                 // ES €0.45/kg plastic tax; UK PPT £228.82/t; DE EWKFondsG; IT MACSI (deferred)
  | 'municipal_tax'           // DE Verpackungssteuer — sub-national, per item
  | 'pass_through_charge'     // consumer-facing, sometimes remitted: CO 60% to municipality,
                              // NY 40% + EPF, ES art.55.2, NL meerprijs, UK carrier bag
  | 'deposit'                 // DRS — working capital, not cost
  | 'composition_ban'         // PFAS, EPS, SUP formats, PPWR Annex V
  | 'operational_mandate'     // reuse targets, dine-in reusables, separate collection rates
  | 'labelling'               // Triman/Info-tri, IT art.219(5), ES art.13, CA SB 343, SUPD marking
  | 'documentation';          // certificates and attestations — see §6
```

Rules: a `composition_ban` or `operational_mandate` **never** contributes a number to the ledger; it
appears as a constraint with a date and a penalty range. A `pass_through_charge` is not our cost — it
is collected from the customer, sometimes remitted to government, and carries its own filing. A
`deposit` is a working-capital line, not an expense, with a dine-in wrinkle: deposits charged on
on-premises consumption are essentially never redeemed by the customer.

**The magnitudes justify the separation.** German municipal tax at Freiburg rates — per component,
uncapped — exceeds the EPR fee on the same meal by an order of magnitude. Ireland's plastics cliff is
€169.70/t recycled vs **€620.22/t non-recycled**, 3.7×. Spain's €0.45/kg plastic tax is escapable only
via UNE-EN 15343-certified recycled content: no certificate, whole weight taxed.

---

## 6. The supplier-document register — the sleeper P0 feature

The practitioner research is unambiguous that the bottleneck is **component-level weights from
suppliers**, not arithmetic. A major UK foodservice distributor's EPR page tells hospitality customers
who is obligated and offers no packaging data, no format and no conversion methodology. Incumbents
paper over this with proprietary extrapolation (Ecoveritas "Factors", Valpak's 60–65M SKU set) and
**none publish sample sizes or error bounds** — while PackUK now charges **£2,548 per resubmission** and
attributed a **£63m year-one shortfall** to producer resubmissions. Estimate quality is a priced
liability nobody quantifies.

The same supplier conversation is legally compelled for several other artefacts, so one register serves
many regimes:

| Artefact | Who must hold it | Retention |
|---|---|---|
| Component weight + material declaration | everyone, for every EPR return | UK **7 years** (Sch. 10) |
| **PFAS certificate** | **NY ECL 37-0211 puts this on the *food seller*** — signed supplier certifications kept on site for DEC | **WA: life of packaging + 3 years**; MD within 30 days of request; CT purchaser may compel in 60 (30 if suspected) |
| Recycled-content certification | ES plastic-tax relief (UNE-EN 15343), UK PPT, PCR mandates | per regime |
| Recyclability grading | UK RAM (component-level), IT Aticelca 501 (moves paper composites €70→€55/t) | per program year |

So: one table — supplier × SKU × component — carrying weights, certificates, attestations and their
expiry, with a **gap list** ("47 SKUs missing lid weight, 12 suppliers unresponsive 30 days") and
per-field provenance: `measured | supplier_declared | gdsn | category_estimated`. Sysco's published
lesson is the design note: build guardrails so suppliers cannot enter wrong data, and use **GS1 GDSN
with GTINs at each packaging hierarchy level** where the supplier publishes it — that's the one real
standard, and it carries material, weight and state EPR classification without a dataset per state.

---

## 7. The three clocks

Conagra's packaging stewardship director on the shape of the job: fees "assessed on **2023 data,
reported in 2024, paid in 2025**." Confirmed structurally — Oregon set both PY2025 *and* PY2026 fees
from 2024 supply data; UK 2026–27 modulated fees are calculated from packaging supplied in 2025.

Every figure in the product carries **three years**, displayed separately and never conflated:

```ts
export interface Clocked<T> { dataYear: number; reportYear: number; cashYear: number; value: T }
```

This kills a v1 error directly: the "Reduce" list implied instant savings. A redesign today does not
move a UK bill for ~18 months. Every lever must state **when it lands**, not just what it saves.

It also makes the **correction windows** legible, which is where the real risk sits. After **1 May
2026** PackUK accepts no new data for the 2026–27 year; after **1 Sep 2026** it will not recalculate.
Errors become permanently priced in. Germany's *Vollständigkeitserklärung* is due **15 May**,
expert-certified, **non-extendable**.

---

## 8. Confidence ladder v2

Extended with two tiers the research forced.

| Tier | Meaning | Example | UI |
|---|---|---|---|
| **confirmed** | published, binding, current program year | **OR PY2026, CO PY2026** (both being invoiced), UK 2025 base fees | plain number |
| **illustrative** | published by the administrator, explicitly non-binding | **CA 2027** ("good faith, non-binding"; final Oct 2026), UK Year-2 | number + chip |
| **proxy** | priced on another jurisdiction's table | remaining US states | number + basis named + range |
| **estimated** | bill-stated fee only, no schedule | `compliance_details.fee_amounts` | range, never a point |
| **unpriced** | obligated, no published schedule | DE dual systems, most 2024–26 enactments | no number, explicit callout |
| **contingent** | enacted but not commenced; may never be | **IT MACSI** (deferred to 1 Jan 2027, 8th postponement), **IE 20c latte levy** (uncommenced since 2021) | listed, excluded from total, dated |
| **unenforced** | in force but the regulator has said it is not enforcing | **NL meerprijs** — ILT not enforcing through end-2026, abolition planned 1 Jan 2027 | listed, flagged, excluded |

Rules carried from v1 and reinforced: the headline total is a **range** whenever any line is
non-`confirmed`; a schedule older than one program year stops being quoted; `unpriced` never enters the
total as zero. Added: **`contingent` and `unenforced` never enter the total**, but always appear — the
value of knowing Italy's plastic tax is deferred again is exactly as high as knowing Spain's is live.

**A citation discipline the research vindicated.** The Colorado $5,000/$10,000 and Maryland
$500/$1,000 PFAS penalty figures circulating in trade coverage sit in the *firefighting-foam* and
*rug-and-carpet* subtitles of those acts, not the packaging provisions. Penalties, thresholds and rates
are cited to article level or marked unverified. Never transplanted from an adjacent subtitle.

---

## 9. Outputs

1. **Applicability determination** — per (entity × jurisdiction × regime): are you the producer, under
   which rule, above which threshold, with the statutory test quoted and dated. Re-runnable when the
   corporate or sourcing structure changes. *Nobody else sells this.*
2. **Registration register** — one row per (entity × jurisdiction × regime): the identifier, its
   renewal date, and its AR status. The identifiers are real and numerous: France **IDU** (15-char,
   one *per filière* — ménagers, EPRO, papiers graphiques, DEA, DEEE — and it must appear in CGV and
   on the website); Germany **LUCID** + dual-system contract + **DIVID** (EWKFondsG); Spain
   **ENV/[year]/XXXXXXXXX**, which must appear on invoices; Ireland Repak; UK RPD; US per-state + CAA.
3. **Obligations calendar** — register → submit → pay, three dates per jurisdiction, plus correction
   windows and non-extendable audit dates. Deadline-first, because that is what the job is measured on.
4. **Reporting pack** — the tonnage/piece table *is* the submission basis. Export per jurisdiction in
   that scheme's own categories and file format. The UK's is a defined CSV column spec; France wants
   per-UVC grams by product category; Germany wants volumes matching the dual-system report.
5. **Frozen submissions** — what was filed, on what data, under what assumptions, by whom, when.
   The artefact that survives a UK reg. 110 notice or a Citeo *contrôle*, and the thing that makes the
   resubmission windows navigable.
6. **Reduce** — levers ranked by money **and dated by when they land**, evaluated **per jurisdiction**
   because they conflict (see §10).
7. **Constraints** — composition bans and operational mandates with dates: what you cannot buy, what
   you must offer, what infrastructure you need.
8. **Per-SKU fee delta for procurement** — the output that actually changes behaviour. Conagra puts EPR
   fees on the P&L of the products that cause them, not in an EPR bucket, "because those individual
   brands and SKUs have to be accountable for those dollars." Belongs in should-cost models next to
   material and conversion cost.

---

## 10. Why "cheaper alternative" must be per-jurisdiction

v1's cost curve assumed a swap is globally better or worse. It isn't, and the same cup proves it three
ways.

**The state's collection list drives the rate, not the packaging.** A poly-coated paper hot cup:
**48.0¢/lb in Oregon** (on neither acceptance list), **20.0¢/lb in Colorado** (on the AML), **6¢/lb
illustrative in California**. An 8× spread on an identical cup.

**Swaps conflict across markets.** Oregon prices compostable rigids at **97¢/lb** and flexibles at
**102¢/lb** (accepted nowhere); Colorado prices certified compostables at **26–32¢/lb**. A national
compostables strategy *raises* Oregon fees. Italy's bioplastic CAC **doubles mid-year**, €130 → €246/t
on 1 July 2026.

**And a swap can create a second violation.** In Oregon, foam and PFAS were banned by the same act on
the same date (SB 543, 1 Jan 2025) — so a foam → grease-proof-paper switch that reaches for a
fluorinated coating trades one prohibition for another.

Recommendations therefore carry: the jurisdictions where they help, where they hurt, when they land,
and any constraint they trip.

---

## 11. Reuse plan and repo corrections

**Reusable as-is:** `resolveRate()` and the whole modulation engine — four op shapes, three composition
policies, floors/caps, `AppliedModulation[]` audit trail. It handles UK RAM selectors and stacking
bonus/malus correctly, and RAM being component-level fits the existing per-component `attrs` model.

**Extract** from `studio.ts` into `lib/exposure.ts`: the obligation indexer (market × category with
wildcard handling), `canon()`, `ACTION_REQUIRED`, the pathways fetch/cache. Studio imports them back.

**Corrections the research surfaced in current code.** ✅ = applied 2026-08-11.

- ✅ **Oregon and Colorado registered as their own schedules.** `orCaaSchedule()` / `coCaaSchedule()`
  transcribed from the CAA source PDFs with `pypdf` (OR published 29 Oct 2025, CO 13 Oct 2025) — not
  from a summary. `scheduleForMarket()` previously routed **every** US state to the CA flagship on the
  stated grounds that "CA SB 54 is the only detailed US schedule"; that was false, and backwards — OR
  and CO are binding and currently invoiced while CA remains explicitly non-binding until Oct 2026.
  Resolution is now exact key → `US-` prefixed state key → flagship, and a new `isProxyPriced()` tells
  the UI when a figure is an approximation. Both schedules are selectable in the studio switcher.
  - Oregon: SIM column is 0.0¢/lb on every PY2026 row, so no modulation rule; acceptance status
    (USCL / PRO / not-accepted) recorded in `tag`, since that is what drives the spread.
  - Colorado: passive eco-modulation is **already baked into Final Dues** by state law, so the rate is
    encoded directly with **no** rules — adding any would double-count. The four active PY2026
    incentives are not yet published in enough detail to encode.
  - New categories `printed_paper` and `compostable_packaging`. Compostables are deliberately their
    own category rather than folded into plastic/paper: Colorado prices certified compostables at
    26–32¢/lb while Oregon has no such class and prices PLA at 97–102¢/lb inside the ordinary plastic
    bands. A shared category would hide that a national compostables switch *raises* Oregon fees.
- ✅ **UK RAM escalator added.** `ukPeprSchedule(programYear)` with red at **1.2× (2026-27) → 1.6×
  (2027-28) → 2.0× (2028-29)**. Verified: plastic goes £455 amber → £546 / £728 / £910 red, i.e. red
  exposure exactly doubles by 28-29 with zero change in tonnage.
- ✅ **The fabricated UK green multiplier is gone.** `GREEN_ILLUSTRATIVE = 0.9` presented an estimate as
  a published rate. PackUK's green discount is a redistribution pot funded by the red premium and spread
  as an equal percentage across all green material — market-mix dependent and unknowable in advance. Now
  `UK_RAM_GREEN_ESTIMATE`, labelled as an estimate in the rule text that travels into the UI via
  `AppliedModulation.label`.
- ⚠️ **`FALLBACK_PALETTE` / `ca_sb54_fees.py` — NOT corrected, deliberately.** Values predate the 1 May
  2026 CAA illustrative table and `pp_ps` at 98¢/lb is labelled "PP bottle / PS foam" while 98 is
  reported to be *Other/Mixed Plastics — Textiles* — label and rate may describe different rows. The
  source PDF could not be retrieved to verify replacements, and the governing rule is that **a rate is
  never taken from a summary**. Both files now carry the caveat in-line; fix by ingesting the CAA table.
  CA pricing is unchanged and regression-checked (plastic_rep still $1,190.49/t).
- ❌ **Piece count** — still no home in the model, so California's PPMF component fee cannot be
  expressed at all. Documented in-line at `caSb54Schedule()`. Needs the §4 input change.
- ❌ **Jurisdiction granularity must go sub-state.** WA, VT, RI and OR preempt local bag ordinances; CA,
  NY, CO, CT and NJ do not — so a chain exempt under state law can still be caught by city ordinance.
  Germany's municipal packaging tax is the same problem: Tübingen, Freiburg (uncapped, per component),
  Konstanz live; Bonn, Bremen, Köln, Heidelberg, Osnabrück and others adopted; **Bavaria has banned
  municipal packaging taxes outright** from January 2026.

**Assets already on disk:** the US research left parsed `OR2026.pdf`, `CO2026.pdf`, `sb54regs.pdf` and
`orguide.pdf` in the session scratchpad. All parse cleanly with `pypdf`, confirming the tariff plan's
Tier A assessment.

---

## 12. Phasing

- **P0 — the applicability engine + registration register + calendar.** Entity tree, producer
  attribution per (jurisdiction × regime) for the markets we can cite, threshold tests, registration
  IDs and renewals, obligations calendar with correction windows, supplier-document register with the
  gap list. Exposure ledger over CA/UK/JP + OR/CO once registered, priced on the plural charge bases,
  full confidence ladder. **No new endpoints** — client-side against `/compliance/pathways` and
  `/compliance/fee-schedule`, prefs-key persistence as `SavedPackages` does.
- **P1 — real numbers.** CAA adapter (tariff plan P0) for OR/CO/CA; UK confirmed Year-2 fees; the RAM
  escalator. Frozen submissions and the reporting pack.
- **P2 — EU depth.** Citeo household (per-UVC + per-order + litter component), Ecoembes, CONAI bands,
  Repak, Verpact — each with its own charge basis. The eco-taxes (ES, DE EWKFondsG, UK PPT) as separate
  classes. German municipal tax as a sub-national layer.
- **P3 — team and time.** Server-side portfolios, multi-user, year-over-year diff driven off corpus
  updates ("what changed since your last submission") — the retention hook, since exposure changes when
  the law changes and we are the ones who know it changed.

---

## 13. Risks

- **False precision.** A confident total over illustrative rates loses trust in one screenshot. §8
  exists for this; the range must not collapse to a point in design review.
- **Attribution errors are the largest possible error.** Getting Oregon wrong bills a chain for fees it
  does not owe; getting the UK franchise sweep-up wrong misses an entire estate. Every verdict quotes
  its statutory test and links the measure.
- **Regulatory volatility in both directions.** PPWR alone has 30+ implementing acts running to 2029,
  and a live Commission proposal to suspend the AR obligation. Verpact is openly telling businesses to
  "provisionally continue with the situation as it applied before 12 August." Build flags, not constants.
- **Scheme-category mismatch is permanent.** Colorado prices PET clear at 17¢/lb and PET pigmented at
  50¢/lb; Oregon prices PP containers at 62¢ and PP lids at 29¢ — **the lid is often a different rate
  from the cup it fits**. Cite `scheme_category` verbatim, map loosely, leave null where it would
  misprice.
- **Support load.** "Why is my number different from my PRO invoice?" is inevitable and legitimate. The
  modulation trail, the three clocks and the provenance footer must be good enough to self-serve it.

---

## 14. Open items blocking a trustworthy build

Carried from the research, in priority order. Each is a fact we do not have, not a design choice.

1. **Does a UK franchisor *pay* disposal fees on swept-up franchisee tonnage, or only report it?**
   Decides whether a franchised estate's tonnage lands on the franchisor's P&L. The answer is in the
   NPWD "Agreed positions and technical interpretations" document — an image-based PDF needing OCR or a
   direct request to the regulators.
2. **Have confirmed UK 2026–27 base fees published?** The Dec 2025 document said June 2026; the PackUK
   operational plan says fees are calculated in November 2026. All Year-2 modelling is illustrative
   until resolved.
3. **PFAS effective dates for nine states** (WA, ME, MN, NY, VT, CT, RI, MD, CO) — plausibly a larger
   cost driver than the EPR fee.
4. **Cutlery/straw coverage in CO, ME, MN, MD, WA** — not resolved on any statute's face.
5. **France: is H2-2026 EPRO actually payable?** The Ministry says obligations run from 1 Jan 2027;
   Citeo Pro's own June 2026 deck is already invoicing "Éco-contribution 2026 = S2 2026."
6. **Germany: were EWKFondsV rates revised at the 1 Jan 2026 review?** And does VerpackDG carry §§33–34
   (Mehrwegangebotspflicht) forward verbatim?
7. **Spain: the 2026 (not 2027) Ecoembes household schedule and the full eco-modulation grid** — both
   behind 403s.
8. **Colorado's current CPI-adjusted revenue threshold**; **Maine's Stewardship Organization RFP
   status** (all Maine clocks run from contract execution, and no contract existed as of May 2026).
9. **Reference weights** — confirm whether the 35-SKU shape×material catalog exists (it is *not* in this
   repo) or seed a QSR-specific table. Weights remain the largest error source in the model.
