# Cost Exposure Calculator (`/exposure`) — Spec

**Status:** proposed (2026-08-11) · **Owner:** kenny
**Depends on:** `dashboard-next/src/lib/feeSchedule.ts` (built), `GET /compliance/pathways` (built),
`docs/PRO_TARIFF_INGESTION_PLAN.md` (scoped, **not built** — the accuracy dependency)
**Related:** `dashboard-next/src/lib/studio.ts`, `docs/FEE_DATA_API_SPEC.md`, memory `compliance-action-vision`

---

## 1. The question this answers

> *"I am a restaurant chain. I put packaging on the market in the US, UK and EU. What will EPR cost me
> next year, and what do I do about it?"*

Nothing in Atlas answers that today. The Packaging Studio answers a narrower question — *what does
**this one package** cost, and what's a cheaper material?* — and answers it well. The gap between the two
is not the fee math. It is:

| Studio (built) | Exposure (this spec) |
|---|---|
| one package | a portfolio of 40–200 SKUs at real volumes |
| one active schedule at a time (`ScheduleSwitcher`) | every jurisdiction summed into one ledger |
| markets = 7 US states, all priced on CA SB-54 | US + UK + EU + APAC, each on its own basis |
| assumes you're covered | asks whether you're a covered producer at all |
| ¢/package | annual money, per jurisdiction, with an action list |

The Enterprise tier already sells this ("Exposure mapped across your own product lines" —
`lib/tiers.ts` `ENTERPRISE.features`). `/exposure` is the productised, self-serve version of the thing
we currently only do as a bespoke engagement.

### Non-goals

- **Not an invoice.** A PRO invoices on audited placed-on-market data with its own category mapping.
  This is a forecast, and every screen says so.
- **Not a replacement for the Studio.** Studio is design-time (should this cup be PET or PLA?).
  Exposure is finance-time (what is the 2027 line item?). They share the engine, not the UI.
- **No invented rates.** Where no tariff is published (Germany, EU-wide, most 2024–26 enactments) the
  answer is "obligated, unpriced" — never a plausible-looking number. See §6.

---

## 2. What already exists (verified, 2026-08-11)

**Reusable as-is:**

- `lib/feeSchedule.ts` — the rate engine. Native units (`cents_per_lb`/`cents_per_kg`/`per_kg`/`per_tonne`),
  six currencies, four modulation shapes (`add_per_tonne` / `percent` / `multiplier` / band-as-base),
  three composition policies (`stack` / `exclusive_malus` / `selector_plus_stack`), floors and caps,
  and a per-rule audit trail (`AppliedModulation[]`) so any number can show its working.
  `resolveRate(schedule, format, attrs)` is the single entry point and is pure.
- `UNPRICED_JURISDICTIONS` — DE / EU / CN already registered with a `reason` and a citable note.
  The honesty scaffolding exists; this spec extends it rather than inventing one.
- Registered schedules: **`US-CA` (SB 54 draft 2027), `UK` (PackUK Year-2 illustrative), `JP` (JCPRA FY2025)**.
- `GET /compliance/pathways` — supports `state`, `region`, `regions` (CSV), `bill_ids`
  (`app/api/compliance.py:437`). Non-US pathways are reachable today via `region=EU` / `regions=UK,FR`.
- `lib/nextSteps.ts` — deadline-type + pathway-action → imperative step, with the entity and
  registration URL. This is the "register for a PRO" output, already written.
- `buildQuote`'s obligation indexer (`studio.ts:736`) — laws indexed by market × canonical material
  category, with wildcard handling for packaging-wide laws. Portable to portfolio scale unchanged.
- Persistence pattern — `SavedPackages.tsx` stores specs in account prefs via `PATCH /me/settings`
  under one key. `/exposure` copies this exactly (`exposurePortfolios`), no new table in P0.

**Missing / blocking:**

1. **No portfolio object.** `StudioSpec` holds one package.
2. **No multi-schedule summation.** `activeSchedule` is a single value; switching remaps components
   (`remapComponentsToSchedule`) rather than pricing both.
3. **US states are a proxy.** `scheduleForMarket()` falls every non-CA state back to the SB-54
   flagship. Oregon has a real published CAA schedule — we just haven't ingested it.
4. **EU has no rates and won't until ~2028** (PPWR delegated acts). A real EU number means national
   PRO tariffs (Citeo, CONAI, Ecoembes, Repak…), which is `PRO_TARIFF_INGESTION_PLAN.md` Tier B.
5. **No scope/threshold data.** Nothing in the corpus answers "is a producer of my size covered here?"
6. **No weight reference.** `default_g` on palette formats + `CATEGORY_DEFAULT_G` is all we have —
   thin for a QSR bill-of-packaging. (The 35-SKU shape×material reference catalog referenced in
   memory `packaging-reference-catalog-3d-swatch` is **not in this repo** — confirm before depending on it.)

---

## 3. The model

The pivot object is **tonnes placed on market**, not packages — because that is what every scheme
charges on and what every scheme makes you report. The SKU list is just the honest way to derive it.

```
  Portfolio                     ScopeGate                    Exposure
  ─────────                     ─────────                    ────────
  SKU × Jurisdiction            per jurisdiction:             per (jurisdiction, material):
    units/year          ──►       covered?          ──►         tonnes × resolveRate(...)
    components[]                  threshold?                    = annual fee, native currency
      material, grams             obligated party?              + confidence tier
      attrs (PCR, colour…)
                          ┌─────────────────────────────────────────┐
                          │ tonnage table = the fee basis AND       │
                          │ the draft of the report you must file   │
                          └─────────────────────────────────────────┘
```

### 3.1 Types (`lib/exposure.ts` — new, pure, client-side)

```ts
/** One packaging component of one SKU. Same shape as studio's SpecComponent so specs interop. */
export interface ExposureComponent {
  key: string;
  name: string;                 // "12oz cup", "dome lid"
  material: string;             // palette/format id, resolved per active schedule
  grams: number;
  weightSource: 'entered' | 'reference' | 'category_default';   // drives confidence, §6
  attrs?: PackageAttributes;    // PCR%, colour, RAM grade, reusable, disruptor — feeSchedule.ts
}

export interface ExposureSku {
  id: string;
  name: string;                 // "Regular hot drink — dine in"
  components: ExposureComponent[];
  /** Units placed on market per year, PER jurisdiction. A chain's mix is never uniform. */
  volumes: Record<JurisdictionCode, number>;
}

export interface Portfolio {
  id: string;
  name: string;
  programYear: number;          // fees are annual and versioned; never implicit
  jurisdictions: JurisdictionCode[];
  skus: ExposureSku[];
  producer: ProducerProfile;    // §3.3
}
```

### 3.2 Jurisdictions — a first-class registry (not the studio's `MARKETS`)

`studio.ts`'s `MARKETS` is seven US states with `kind: 'state'`. Exposure needs a wider entry that
knows how to price *and* how to fetch obligations:

```ts
export interface Jurisdiction {
  code: string;                 // 'US-CA' | 'US-OR' | 'UK' | 'FR' | 'DE' | 'EU' | 'JP'
  label: string;
  region: string;               // for GET /compliance/pathways?regions=…
  state?: string;               // for ?state=…
  /** Schedule that prices it, and how honestly. null = obligated but unpriced. */
  pricing:
    | { basis: 'own'; scheduleId: string }        // its own published table
    | { basis: 'proxy'; scheduleId: string; note: string }  // e.g. US-OR priced on CA until CAA lands
    | { basis: 'none'; reason: UnpricedReason; note: string }; // reuses UNPRICED_JURISDICTIONS
}
```

Seeded from the existing registry: `US-CA` own, `UK` own, `JP` own, the other six US states proxy,
`DE`/`EU`/`CN` none. Every new adapter from the tariff plan flips a `proxy`/`none` to `own` and the
UI improves with no frontend change.

### 3.3 Scope gate — runs *before* any number

For a restaurant chain the first-order question is not the rate, it's whether they are the obligated
party and whether they clear the threshold. Getting this wrong is a 100% error, which is worse than
any rate imprecision.

```ts
export interface ProducerProfile {
  legalEntityName?: string;
  /** Franchisor vs franchisee changes WHO is obligated in most brand-owner regimes. */
  model: 'own_operated' | 'franchised' | 'mixed' | 'unknown';
  /** Annual turnover per jurisdiction, in that jurisdiction's currency. Optional; gates thresholds. */
  turnover?: Record<JurisdictionCode, { amount: number; currency: CurrencyCode }>;
}

export type ScopeVerdict =
  | { status: 'covered'; because: string; citation: Citation }
  | { status: 'below_threshold'; because: string; citation: Citation }
  | { status: 'near_threshold'; marginPct: number; because: string; citation: Citation }
  | { status: 'unknown'; because: string };   // the honest default
```

Thresholds live in a new **curated, cited** table — `app/scoring/producer_thresholds.py` mirrored to
`lib/producerThresholds.ts` (or served; see §8). Encode **only** what we can cite to a source document;
everything else is `unknown` with "check this yourself" and a link to the measure. A half-populated
table that is honest about its gaps is useful. A guessed one is a liability.

Also surface, per jurisdiction, the **obligated-party test** (brand owner / first placer / importer /
franchisor) as prose from the pathway's `action_summary`, with a warning when `model: 'franchised'` —
this is precisely where a chain's exposure is most often mis-modelled in both directions.

### 3.4 The math

```ts
// tonnes, per (jurisdiction, schedule format), from the SKU list
tonnes = Σ_sku Σ_component (sku.volumes[j] × component.grams) / 1e6

// fee, per line, in the schedule's own currency
line.fee = tonnes × resolveRate(schedule, format, component.attrs).ratePerTonne
```

`resolveRate` already returns `applied: AppliedModulation[]`, so every line can expand into
"base £455/t → RAM red ×1.2 → £546/t" without new machinery.

**Currency: no FX in the stored numbers.** The primary artifact is a per-jurisdiction ledger, each row
in its native currency — that is what you will actually be invoiced. A single converted grand total is
offered *on top*, behind an explicit, user-visible FX rate and date, labelled **indicative**. Rates are
entered by the user or fetched with the date stamped; they are never baked into a persisted figure.

---

## 4. Screens

Four steps, each independently useful, no step blocking the next more than it must.

### 4.1 Footprint
Build the SKU list. Three entry paths, in order of how people actually work:
- **CSV / paste import** — the real path. Columns: `sku, component, material, grams, <jurisdiction
  volume columns…>`. Fuzzy-map the material column onto palette ids, show every unmapped row rather
  than silently dropping it, and let the user resolve them inline.
- **Starter portfolios** — a QSR preset (hot cup, dome lid, sleeve, cold cup, straw, clamshell, fry
  carton, napkin, carrier bag, cutlery) with reference weights, so the first number appears in under a
  minute and the user edits down instead of building up.
- **Manual add** — the studio's component editor, reused.

Every defaulted weight is visibly tagged, with a running "N of M weights are defaults" counter. Weights
are the single largest source of error in the whole model and the UI should say so, not hide it.

### 4.2 Scope
Per-jurisdiction verdict cards: covered / below threshold / near threshold / unknown, each with its
citation and the obligated-party test. Jurisdictions ruled out here are excluded from the total but
stay listed with their reason — a disappearing jurisdiction reads like a bug.

### 4.3 Exposure
The ledger. Rows grouped by jurisdiction, then material, each showing tonnes → rate → fee, in native
currency, each carrying a **confidence chip** (§6). Above it:
- a per-jurisdiction bar (native currency, not summed across currencies);
- the indicative converted total, with its FX rate and date;
- an **unpriced-exposure callout**: "3 jurisdictions where you are obligated but no schedule is
  published — DE, ES, PL." That callout is a feature, not an apology. Nobody else will tell them.

Any row can expand into its modulation trail and the measure it derives from.

### 4.4 Actions
Four ranked lists, all derivable from data we already hold:

1. **Register / join** — `join_pro`, `register_with_state`, `file_individual_plan` pathways for the
   in-scope jurisdictions, with entity name, `registration_url`, and `next_deadline_date`.
   Straight from `/compliance/pathways` + `nextSteps.ts`. Sorted by deadline.
2. **Report** — the §3.4 tonnage table *is* the reporting basis. Offer it as CSV per jurisdiction with
   the scheme's own category names where a tariff is ingested. This is the highest-value output we can
   produce for near-zero extra work.
3. **Reduce** — fee-reduction levers ranked by annual money saved, each priced through the same engine:
   - *modulation levers* — per-schedule `AttributeInput[]` (UK RAM red→amber, PCR thresholds, drop the
     pigment, remove the disruptor). These are the "eco-modulated fee" answers the ask names directly.
   - *material swaps* — the studio's `cost_curve`, filtered to `same_family` so suggestions stay
     functionally plausible (a fry carton does not become glass).
   - *lightweighting* — ∂fee/∂gram per component, which falls straight out of the linear model.
   - *reuse* — where a scheme exempts or floors reusable systems (`minFractionOfBase: 0`).
   Each lever states its assumption ("assumes RAM amber is achievable for this format") and links to
   the Design Guide principle behind it.
4. **Watch** — measures that are enacted-but-unpriced or still moving, wired to the existing watchlist.

---

## 5. Reuse plan (what moves, what stays)

- **Extract** from `studio.ts` into `lib/exposure.ts`: the obligation indexer (market × category with
  wildcard handling), `canon()`, `ACTION_REQUIRED`, and the pathways fetch+cache. Studio imports them
  back — no behaviour change, no duplicated law-matching logic.
- **Leave alone**: `feeSchedule.ts` (used verbatim), `buildQuote` (package-scale, still Studio's), the
  studio hash codec.
- **Add**: `Jurisdiction` registry, `Portfolio` types, CSV importer, threshold table, ledger builder.
- **Interop**: a Studio package can be added to a Portfolio as an SKU, and an exposure row can open in
  the Studio for redesign. Both directions use the existing spec hash, so nothing new to serialise.

---

## 6. Confidence ladder (the honesty contract)

Every exposure line carries exactly one tier. This is the spine of the whole product; a chain will make
a budget decision on these numbers.

| Tier | Meaning | Source | UI |
|---|---|---|---|
| **confirmed** | published, in-force tariff for this program year | `pro_tariff_schedule.status = 'confirmed'` (tariff plan P1) | plain number |
| **illustrative** | published by the administrator but not final | UK Year-2, CA SB-54 draft-until-Oct-2026 | number + "illustrative" chip |
| **proxy** | priced on another jurisdiction's table | US states on SB-54 | number + "priced on CA SB-54" + range |
| **estimated** | bill-stated fee only, no schedule | `compliance_details.fee_amounts` | range, never a point |
| **unpriced** | obligated, no published schedule | `UNPRICED_JURISDICTIONS` | no number, explicit callout |

Rules:
- **The headline total is a range whenever any line is non-`confirmed`**, and the range is honest about
  which lines widened it. A point estimate over illustrative data is the failure mode of this product.
- A tariff older than one `program_year` **stops being quoted as current** (the staleness guard from
  the tariff plan). Stale is worse than absent.
- Never mix `unpriced` into the total as zero. Zero is a claim.
- The provenance footer names every schedule, its program year, its citation URL, and its retrieval date.

---

## 7. Accuracy dependencies

`/exposure` is only as good as its rate tables, and today's tables are thin. In build order:

1. **CAA per-state schedules** (tariff plan P0) — turns six US states from `proxy` to `confirmed`.
   PDFs verified parseable; days of work. **This is the single biggest accuracy win available.**
2. **PackUK confirmed Year-2 fees** (tariff plan P1) — `illustrative` → `confirmed` for the UK.
3. **Tier-B probes** (CONAI, Citeo, Ecoembes, Repak) — the only path to a real EU number before the
   PPWR delegated acts land ~2028. Expect access friction.
4. **Threshold data** (§3.3) — new curation, no existing source. Scope: the ~12 jurisdictions where a
   chain-sized producer's coverage is genuinely in question.
5. **Reference weights** — confirm the 35-SKU catalog exists, or seed a QSR-specific table.

Germany stays permanently `unpriced` (competing private dual systems price commercially); the spec
treats that as a correct answer, not a gap.

---

## 8. API surface

P0 needs **no new endpoints** — everything runs client-side against `/compliance/pathways` and
`/compliance/fee-schedule`, matching the studio's static-export architecture.

Later, in priority order:
- `GET /compliance/thresholds?regions=…` — serve the curated threshold table so it updates without a
  frontend deploy (it will change often at first).
- `GET /compliance/tariffs?jurisdiction=…&year=…` — once `pro_tariff_schedule` exists, so the
  frontend stops shipping bundled rate tables.
- `POST /exposure/portfolios` — only when portfolios need to be shared across a team (P3). Prefs-key
  persistence covers single-user until then.

---

## 9. Gating

Pro. It is the clearest "this is worth $200/mo" surface we have, and it directly delivers what the
`PRO.features` bullet already promises ("Check which laws hit your products, by material and jurisdiction").

- **Free teaser:** one jurisdiction, ≤3 SKUs, full scope gate + action list, exposure number blurred
  behind the standard `GateCard` / `UpcomingDeadlinesLock` pattern. The scope verdict stays free —
  "you are a covered producer in Oregon" is exactly the fact that makes someone subscribe.
- **Pro:** unlimited SKUs and jurisdictions, CSV import/export, saved portfolios.
- **Enterprise:** the existing bespoke engagement, now with this as the delivery vehicle rather than a
  spreadsheet.

Analytics via the existing `track()` taxonomy: `exposure_import`, `exposure_scope_verdict`,
`exposure_quote`, `exposure_lever_applied`, `exposure_export`, plus `trackGateHit` on the teaser wall.

---

## 10. Phasing

- **P0 — the shell, honestly labelled.** `lib/exposure.ts`, jurisdiction registry, CSV import + QSR
  starter, scope gate over whatever thresholds we can cite, ledger with the full confidence ladder,
  four action lists, prefs persistence. Prices on CA/UK/JP + proxy. Ships as a real tool with visible
  gaps rather than a fake-precise one.
- **P1 — real US numbers.** CAA adapter (tariff plan P0) wired in; six US states flip to `confirmed`.
- **P2 — UK confirmed + reporting export.** PackUK final fees; per-jurisdiction reporting CSV in scheme
  categories; PDF brief for the board deck.
- **P3 — EU depth + team.** Tier-B tariff adapters as they clear; server-side portfolios; year-over-year
  and a "what changed since your last quote" diff driven off corpus updates (the retention hook —
  exposure changes when the law changes, and we are the ones who know it changed).

---

## 11. Risks

- **False precision.** A confident total over illustrative rates is the way this product loses trust in
  one screenshot. §6 exists for this; do not let a designer collapse the range to a point.
- **Weight data.** Users will not weigh a lid. Defaults will carry most portfolios, so the defaults must
  be defensible and visibly flagged.
- **Franchise liability.** Getting the obligated party wrong is a larger error than any rate. Prose +
  warning, never a silent assumption.
- **Scheme category mismatch.** Our 22 material categories are coarser than any tariff table
  (PET clear vs pigmented vs thermoform are three prices). Cite `scheme_category` verbatim, map loosely,
  and leave the mapping null where it would misprice — the tariff plan's rule, inherited here.
- **Support load.** "Why is my number different from my PRO invoice?" is an inevitable, legitimate
  question. The modulation trail + provenance footer are the answer, and they need to be good enough to
  self-serve it.
