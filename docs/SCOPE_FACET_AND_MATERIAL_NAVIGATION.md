# Scope Facet & Material-First Navigation — Spec

_Status: draft · 2026-07-31 · Author: review session out of `CE_FALSE_REVIEW.md`_

## 1. The problem

`ce_relevant` is a **binary** — a bill is either in the corpus (`true`) or invisible (`false`).
The out-of-scope review surfaced a third state we can't express: bills that are **in the corpus but
should be off by default**. Two concrete drivers:

- **PFAS / toxics** — ~690 bills corpus-wide. Genuinely adjacent to circular economy (material
  restriction), but flipping them all `true` would drown the reuse/repair/remanufacture legislation
  that is the product's core. Founder guidance: *don't let PFAS overshadow the 6-R core.*
- **Transboundary shipment / scrap trade** — a customer running **e-scrap recovery markets across
  jurisdictions** explicitly asked for this. It was on the "segment away" list until that feedback;
  now it's a wanted, opt-in slice.

Neither `true` (pollutes the default view) nor `false` (customer can never reach it) is right. We need
**core / adjacent / excluded**, and a filter surface that defaults to core and lets power users
(CSOs, recovery-market operators) toggle adjacencies on.

## 2. What already exists (build on, don't reinvent)

| Piece | Where | Note |
|---|---|---|
| Hidden scope gate | `dashboard-next/.../BillFilters.tsx:453` | `eprOnly` defaults `true`, silently drops `!ce_relevant`. Comment: *"the product's fixed editorial scope… not surfaced as a control."* This is the exact plug-in point. |
| Master relevance flag | `app/classification/haiku_classifier.py` | `is_ce_relevant` — the LLM's own editorial judgment. Most in-scope bills ride in via this, **not** via `TRACKED_INSTRUMENTS` (narrow: epr, right_to_repair, recycled_content, deposit_return). |
| Adjacency instruments (half-built) | `haiku_classifier.py:39-42` | `chemical_restriction` + `budget` are real classifier instrument types **deliberately hidden** from the UI (`BillFilters.tsx:64-70`). PFAS ≈ `chemical_restriction` + material `hazardous_materials`. |
| Material axis | `app/classification/materials.py` | 21 canonical materials incl. `hazardous_materials`, `electronics`, `solar_panels`. Roll-up groups exist (`MATERIAL_GROUPS`). |
| Scope onboarding | `dashboard-next/src/components/scope` | Personalization onboarding already shares the canonical material list — the coachmark walkthrough has a home. |
| Audit trail | `classification_changes` table | old/new snapshots per run_id; the 42 manual review flips live under `manual-review-flip-2026-07-30/31`. |

**Missing:** a `waste_shipment` instrument type (transboundary/e-scrap trade has nowhere to live
today), and a scope facet that separates core from adjacent.

## 3. The model — three scope states

Every bill resolves to exactly one **scope**:

- **`core`** — default-visible circular economy (the 6 R's: reduce, reuse, refill, repair,
  remanufacture, resell + regenerate/restore — plus the money mechanisms: incentives, fees, green
  procurement).
- **`adjacent:<slug>`** — in the corpus, **off by default**, opt-in via a toggle. Open vocabulary;
  launch slugs: `toxics` (PFAS/chemical restriction), `transboundary` (waste shipment / scrap trade).
- **`excluded`** — never shown: nuclear, tobacco, generic appropriations, off-topic noise.

`excluded` and `adjacent` are both "not core" today, but they differ in intent: an adjacency is a
*promotable* topic (nuclear-plant **decommissioning** and cigarette-butt **EPR** could become
adjacencies later — the mechanism must support promotion without a schema change).

## 4. Data-model changes

Keep `ce_relevant` as the **Layer-1 membership** flag (deeply wired: index `idx_bills_relevant`, the
`/bills?ce_relevant=` param, the classifier). Add **Layer-2 scope** on top.

**Recommendation: one nullable scalar column** `bills.adjacency VARCHAR(24)`:

| `ce_relevant` | `adjacency` | Resolves to |
|---|---|---|
| `true` | `NULL` | **core** |
| `true` | `'toxics'` / `'transboundary'` / … | **included, tagged** (shown by default; tag is provenance/analysis, NOT a gate) |
| `false` | `NULL` | **excluded** |

**Decision (2026-07-31): no default filter.** Toxics and transboundary are **included in the default
view** — they are *not* gated behind a toggle. But we still **store the `adjacency` tag** so the slice
is: (a) traceable (why did this bill enter — core circular, or via the toxics/transboundary net?),
(b) analyzable (the material-axis CSO views in §8), and (c) *future*-filterable without a re-backfill
if the volume ever proves overwhelming. So there are effectively two visible states — **in** (core or
tagged) and **out** (excluded) — with the tag riding along for free.

- Default list query stays `ce_relevant = true` (no adjacency clause). `adjacency` is read for
  badging/analysis, not filtering.
- Scalar over jsonb: adjacencies are near-mutually-exclusive, and a scalar is trivially indexable
  (`CREATE INDEX idx_bills_adjacency ON bills(adjacency) WHERE adjacency IS NOT NULL`). If a bill ever
  needs two adjacencies, revisit as jsonb — not worth the cost now.
- Migration: `alembic` revision `037_bill_adjacency` — add column + partial index. No backfill in the
  migration itself (see §5).

**Volume note:** including toxics folds ~690 bills into the default corpus (~28% on top of the current
2,450 core). That's the tradeoff the "no filter" choice accepts for simplicity. Because the tag is
stored, flipping to a gated model later is a one-line query change, not a data migration — so this is
a safe default to start with and tighten only if PFAS visibly crowds the reuse/repair core.

## 5. Classifier & backfill

**5a. New instrument type `waste_shipment`.** Add to the `instrument_types` enum in the classifier
prompt (`haiku_classifier.py:143`) and the UI list. Covers transboundary movement, import/export of
waste, interstate/out-of-state waste, scrap-metal trade. This is a genuine gap regardless of the
adjacency work — e-scrap recovery is a real circular sub-market with no home today.

**5b. Adjacency derivation.** Compute `adjacency` from signals we already produce, so it's
reproducible and not hand-maintained:

```
# Inclusion nets — bring an otherwise-excluded bill IN, tagged:
toxics        := instrument_type = 'chemical_restriction'
                 OR (title/text matches PFAS|perfluoro|forever chemical|phthalate|flame retardant)
transboundary := instrument_type = 'waste_shipment'
                 OR (title/text matches transboundary|shipment of waste|scrap metal|cross-border waste)

# Hard carve-outs — force EXCLUDED (ce_relevant=false, adjacency NULL)…
nuclear  := title/text matches nuclear|radioactive|spent fuel
tobacco  := title/text matches tobacco|cigarette|vaping|vapor product

# …UNLESS the bill carries a genuine circular mechanism, which OVERRIDES the carve-out → include:
circular_override := instrument_type IN ('epr','deposit_return','right_to_repair','recycled_content',
                        'disposal_ban','organics_diversion')
                     OR title/text matches decommission|end[- ]of[- ]life|reuse|deconstruct|
                        remanufactur|refurbish|take[- ]back|product stewardship
```

**Precedence (2026-07-31 decision):**
1. **`circular_override` wins first.** A nuclear-plant *decommissioning* / EOL bill, or a cigarette-butt
   *EPR* scheme, is **core** — the circular mechanism beats the nuclear/tobacco carve-out. (Consistent
   with the PA decommissioning scope; see [[decommissioning-eol-scope]].)
2. Else **nuclear / tobacco carve-out → excluded.**
3. Else the **inclusion nets** (`transboundary`, then `toxics`) tag an otherwise-excluded bill IN.
4. Else unchanged.

A bill that is already *core* on its own merits (e.g. an EPR law that also restricts PFAS) stays
**core** with `adjacency NULL` — the nets only tag rows that would *otherwise* be `ce_relevant=false`.

**5c. Backfill script** `scripts/backfill_adjacency.py --dsn … [--dry-run]`:
1. For every `ce_relevant=false` row, apply the precedence above. If a circular_override fires on a
   nuclear/tobacco row, set `ce_relevant=true, adjacency=NULL` (it's core). If an inclusion net fires,
   set `ce_relevant=true, adjacency=<slug>`. Log every change to `classification_changes` (run_id
   `adjacency-backfill-<date>`).
2. Leave everything else `false`.
3. Idempotent; re-runnable.

Expected first-pass volumes (corpus-wide, from §12): ~**690 toxics**, ~**19 transboundary** (grows
once `waste_shipment` is a real classifier output, not just a keyword match); nuclear/tobacco rows stay
out except the handful with a circular-mechanism override.

**5d. Quick-win reconciliation (do first, independent of this spec):** 5 `epr` + 3 `deposit_return`
+ 1 `incentives` bills currently sit at `ce_relevant=false` — an instrument-typed circular bill marked
out of scope is almost certainly a misclassification. Flip via the existing manual-review path.

## 6. API changes

`GET /bills` (`app/api/bills.py`):
- **Default behavior is unchanged** — `ce_relevant = true` returns core + tagged (toxics/transboundary)
  together, since there's no default filter. No payload or perf change.
- Add `adjacency` to `BillSummary` so the client can *badge* a tagged row ("Toxics", "Transboundary")
  and so the material-axis views (§8) can slice on it. Badging only; not a gate.
- **Optional / future:** an `adjacency: str | None` filter param (CSV; `exclude:toxics` to drop a
  slice) — only if we later decide a slice should be gateable. Cheap to add on top of the stored tag;
  not built now.
- `ce_relevant=false` still returns the raw excluded bucket for admin/review tooling.

## 7. Frontend — badging only (no toggle, per the no-filter decision)

The 2026-07-31 decision removes the toggle/coachmark work from the critical path. There is **no Scope
section, no default filter, no onboarding walkthrough** to build — a first-time CSO just sees the full
included corpus. The only frontend change:

- **Row badge:** when a bill carries an `adjacency` tag, show a small chip ("Toxics", "Transboundary")
  so the user understands *why* an adjacent bill is in the list. Reads `BillSummary.adjacency` (§6).
- No change to `BillFilterState`, `applyBillFilters`, or `eprOnly` — the default stays "everything
  `ce_relevant`."

**Deferred (only if PFAS volume proves to crowd the core):** a Scope section in the existing **More
filters** drawer that lets a user *exclude* a slice (`☑ Hide PFAS/toxics`). Because the tag is already
stored, this is purely additive later — a checkbox + one query clause, no re-backfill.

## 8. Material-first navigation (the CSO unlock)

The strategic layer this exposes. A CSO doesn't think *"show me circular-economy law"* — they think
*"I ship **electronics** and **packaging** into 12 jurisdictions; what applies to my materials?"* The
e-scrap customer **is** a CSO navigating by material footprint; transboundary is just one facet of
"electronics/scrap."

- **Entry point:** pick material footprint (already have the canonical list + the `scope` onboarding)
  → the corpus pivots to those materials, and **relevant adjacencies are auto-suggested**:

  | Material | Suggested adjacencies |
  |---|---|
  | electronics, batteries, solar_panels | transboundary (e-scrap crosses borders), toxics (RoHS/PFAS in devices) |
  | plastic_packaging, textiles | toxics (PFAS in packaging/apparel) |
  | metals | transboundary (scrap-metal trade) |

- This is the **Atlas facet-engine thesis** made concrete: material × instrument × jurisdiction ×
  adjacency-tag as composable facets, with the material axis as the CSO's natural entry. The stored
  `adjacency` tag is what makes the material→adjacency suggestion possible without re-deriving on the fly.
- Ties to existing roadmap: `docs/ATLAS_CIRCULAR_ROADMAP.md` (facet engine), the material roll-up
  groups in `materials.py`, and the `InstrumentMaterialMatrix` insight view.

## 9. Date search (CSO-critical) — D0+D1 IMPLEMENTED 2026-07-31 (local, undeployed)

Second feature the e-scrap CSO called critical: **search by date.** It splits into two dates a CSO
uses differently, with inverted coverage between US and foreign (numbers in §12):

| | Field | Meaning | US | Foreign |
|---|---|---|---|---|
| **Effective / compliance** | `compliance_details.effective_date` (Sonnet-extracted) | when an obligation takes effect — forward planning | thin (**116/1577**) | **strong + day-precise** (EU 184/189, JP 111/113, UK 86/89) |
| **Legislative activity** | `status_date` / `last_action_date` | when a bill moved — monitoring | day-precise (`status_date` 70/1526 Jan-1; `last_action_date` full) | weak — `last_action_date` **100% NULL** for every non-US region; `status_date` mostly Jan-1 year-only (EU/UK/PL/SE/AU) |

**Key reframe:** "reclassify foreign for granularity" is a non-issue for the date the CSO cares most
about — the **effective date is already day-precise cross-border**, and it's *US* that's the gap.
Dates come from source adapters + Sonnet extraction, never the classifier — so this is date-mapping /
backfill work, not reclassification.

**9a. Data model.** `effective_date` lives in `compliance_details` JSONB as a string (and can be
malformed — the in-force-year code at `bills.py:495` already regex-guards a `::date` cast). Promote it
to a real, indexable column:
- ✅ Migration `043_bill_effective_date` — `bills.effective_date DATE` nullable + `idx_bills_effective_date`.
  Populates from the JSONB (regex-guarded `^\d{4}-\d{2}-\d{2}$`). `extract_job.py` now writes the column
  at Sonnet-extraction time. (`038` in the original draft was already taken; landed as `043`, head 042→043.)
  Verified on local: backfill filled == JSONB-eligible, all day-precise.
- ✅ `Bill.date_precision` property ("day"|"year") — Jan-1 status_date + NULL last_action_date = year-only.
- **Activity date** needs no new column — `status_date` + `last_action_date` exist. Add a
  **`date_precision`** notion (derived, not stored): a `status_date` on Jan-1 with `last_action_date`
  NULL is *year-only*; everything else is *day*. The UI and query use it to avoid faking precision.

**9b. API.** `GET /bills` gains precise date-range params (the existing `year`/`year_from`/`year_to`
stay for chart drill-downs):
- `effective_from` / `effective_to` (DATE) → range on `bills.effective_date`.
- `activity_from` / `activity_to` (DATE) → range on `coalesce(last_action_date, status_date)`.
- **Mixed-granularity rule (documented):** a year-only row matches an activity range on **year
  overlap**, never on the fake Jan-1 day — so "Mar–Jun 2026" includes a 2026 year-only EU act (it
  *might* fall in range) rather than silently excluding it. Flag such rows in the response
  (`date_precision: "year"`) so the UI can mark them "2026 (year)".

**9c. Frontend.** One date control in the **More filters** drawer:
- A small **date-type select** (Effective date / Activity date) + **from/to** pickers. Default: no date
  filter (unchanged behavior).
- Rows matched on a year-only date render the year with a subtle "(year)" qualifier, so a CSO never
  mistakes a bucket for a precise deadline.
- Feeds the same server params; no client-side date filtering (mirrors the scope decision in §6).

**9d. Two backfills, ranked by value** (both audit-logged, dry-run first):
1. **US `effective_date`** — the biggest hole and the CSO's core date. Source: re-run Sonnet
   extraction on enacted US bills lacking `effective_date` (most were never extracted). Highest impact.
2. **EU precise dates via the SPARQL fix** — the EUR-Lex discovery query `SELECT`s only `?celex`
   (`eurlex.py:256`), discarding dates CELLAR exposes: `cdm:work_date_document` (adoption) and
   `cdm:resource_legal_date_entry-into-force` (effective). Add both to the SELECT + a re-fetch pass →
   189 EU bills gain real adoption **and** effective dates (replacing Jan-1 placeholders and filling
   `last_action_date`). Then per-adapter follow-ups (FR/JP already partial; PDF-mirror sources like IN
   FAOLEX may stay year-only — honest, not blocking).

Neither backfill gates the feature: date-search ships on current data (effective-date already
cross-border-precise; activity-date honest about mixed granularity) and *improves* as the backfills land.

## 10. Rollout phases

**Adjacency track (scope):**
1. **P0 — data model.** Migration `037_bill_adjacency` (column + partial index) + `waste_shipment`
   instrument type + the §5d quick-win reconciliation. No user-visible change.
2. **P1 — backfill.** `backfill_adjacency.py` against prod (dry-run → apply, audit-logged). Applies the
   §5b precedence: inclusion nets tag toxics/transboundary IN; nuclear/tobacco stay out unless a
   circular_override fires. **Delivers the customer ask** (transboundary in the default corpus) — no UI.
3. **P2 — API + badge.** `BillSummary.adjacency` + a row chip. Small, cosmetic.

**Date track (independent, can run in parallel):**
4. ✅ **D0 — data model.** Migration `043_bill_effective_date` + populate from JSONB + persist at
   extraction time + `date_precision` property. Done, verified local, undeployed.
5. ✅ **D1 — API + filter UI.** `effective_from/to` + `activity_from/to` params (year-overlap for
   year-only rows) + `status_date`/`effective_date`/`date_precision` on `BillSummary` + the date control
   in More filters (client-side `applyBillFilters` + exported `billDatePrecision`). Done, tsc clean,
   semantics unit-tested. **Delivers the CSO's second critical ask** on current data. Remaining polish:
   render the "(year)" qualifier on year-only rows in `BillTable` (helper is exported, not yet wired).
6. **D2 — backfills.** US effective_date (Sonnet) then EU SPARQL precise dates. Improves coverage under
   the shipped filter.

**Shared bigger bet:**
7. **P3 — material-first nav.** Material entry point + adjacency suggestions, with date as a facet. The
   CSO story / Atlas facet engine.
8. **Deferred — exclude-slice filter.** Only if PFAS crowds the core. Additive, no re-backfill.

The toggle-drawer + coachmark layer from the earlier draft is **cut** (no-filter decision). P0+P1 and
D0+D1 are each ~a day's work and together deliver both of the CSO's critical asks.

## 11. Decisions (resolved 2026-07-31) + remaining

**Resolved:**
- **No default filter** — toxics + transboundary are included, not gated. Tag stored for
  provenance/analysis/future-gating. (§3)
- **Nuclear + tobacco** — excluded, **unless** a circular mechanism (EPR, decommissioning/EOL, reuse,
  deconstruction, remanufacturing) overrides → then included as core. (§5b)
- **Scalar `adjacency`** — confirmed; one adjacency per bill, revisit as jsonb only if a bill is
  legitimately both.

**Remaining:**
- **Does core ever *include* an adjacency-tagged bill?** Per §5b, no — the nets only tag
  otherwise-excluded rows, so a bill that's core on its own merits stays `adjacency NULL`. Confirm.
- **PFAS volume watch** — ~690 toxics rows enter the default (~28% on top of core). Ship it, but keep
  an eye on whether it visibly crowds the reuse/repair/remanufacture story; the deferred exclude-slice
  filter (§7, §10 Deferred) is the escape hatch if so.
- **`waste_shipment` prompt wording** — needs a crisp definition so the classifier separates genuine
  transboundary/scrap-trade from ordinary in-state disposal logistics.
- **US effective_date backfill cost** — re-running Sonnet on ~1,400 US enacted bills has an LLM cost;
  scope to enacted-only (obligations that actually bind) to bound it, and gate behind
  `enable_sonnet_extraction`.
- **Activity-date default sort** — foreign `last_action_date` is NULL, so the current
  `order_by(last_action_date desc nullslast)` buries all foreign rows. Once the date filter ships,
  consider sorting by `coalesce(last_action_date, status_date)` so foreign isn't always last.

## 12. Appendix — corpus numbers (prod, 2026-07-31)

- `ce_relevant=true`: **2,450** · `false`: 7,683 (pre-review).
- Instrument (true): epr 1152, right_to_repair 381, incentives 246, deposit_return 239, other 134,
  labeling 114, recycled_content 49, **chemical_restriction 43**, preemption 37, disposal_ban 17,
  organics_diversion 14, budget 12.
- Instrument (false): (null) 4317, other 2461, **chemical_restriction 580**, budget 144, labeling 79,
  preemption 56, **epr 5, deposit_return 3, incentives 1** ← §5d quick-win.
- Materials (true): plastic_packaging 859, metals 648, electronics 614, glass 579, paper_packaging
  447, batteries 327, organics 303, **hazardous_materials 215**, … solar_panels 56.
- Adjacency buckets (corpus-wide, total / already `true`): **toxics/PFAS 690 / 45**, nuclear 25 / 0,
  tobacco 50 / 5, transboundary+scrap 19 / 5.
- **Date coverage (ce=true)** — `effective_date`: US 116/1577, EU 184/189, JP 111/113, FR 90/122, UK
  86/89, PL 50/50. `last_action_date`: US 1526/1577, **all foreign regions 0**. `status_date` Jan-1
  (year-only) share: US 70/1526 (day-precise), EU 189/189, UK 89/89, PL 50/50, AU 32/32 (year-only);
  JP 1/113, FR 102/122 (partly real).
