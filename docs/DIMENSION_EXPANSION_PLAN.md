# Dimension expansion — routing (done) + extraction plan

Draft 2026-07-13. Triggered by the "similar to the French repair index?" query and a keyword-theme audit
that found several themes we classify on but can't *route* to. Companion: `tests/eval/README.md`,
`docs/ATLAS_A0_A1_SPEC.md`; related memory: [[structured-dimensions-multilingual]],
[[router-eval-and-dev-backbone]], [[biological-cycle-scope]].

## 0. What a "dimension" is (the test)

A dimension = a **compliance-requirement envelope** — a facet a bill *imposes* (recycled-content %, a
collection target, a labeling rule). It is populated per-bill in `compliance_details[dim]` by the Sonnet
extraction and *filters* only when `compliance_details[dim].status == 'present'` (research.py RULE 2).
Contrast the other axes: **materials** (what stream), **instrument** (the bill's dominant mechanism, ~one
per bill), **places** (jurisdiction). A concept is dimension-shaped iff it's a requirement facet, not a
subject or a lever.

## 1. Routing layer — DONE (2026-07-13, this change)

Four dimensions added and routable now (router `DIMENSION_KEYS` + `_DIM_TRIGGERS`, golden cases in
`router_golden.json`). They **degrade gracefully**: with no envelope yet, RULE 2 finds 0 and retrieval
falls back to instrument/text — no regression. Verified: deterministic `_map_dimension` catches all four;
the LLM router reliably emits the two strongest (repairability, reuse_refill).

| dimension | keyword theme (source) | corpus signal | notes |
|---|---|---|---|
| `repairability` | repairability_and_durability | 31 (+378 RtR bills) | repair score/index, durability, parts availability, planned obsolescence |
| `reuse_refill` | reuse_and_refill | **125** | reuse mandates/targets, refillable/returnable packaging, refill infra |
| `digital_product_passport` | digital_product_passport | 7 (EU-heavy, growing) | DPP/traceability/lifecycle-disclosure — distinct from generic `labeling` |
| `remanufacturing` | remanufacturing | 25 | refurbishment/remanufacturing standards, industrial symbiosis |

Deferred from the audit: `embodied_carbon`/buy_clean (0 signal now), `procurement` and `resale_secondhand`
— these are **levers/incentives, not requirement facets** → route to the `incentives` instrument, not a
new dimension.

## 2. Extraction layer — making them filter (the real work)

Routing recognizes the query; **filtering needs the envelope populated**. Today only ~44 bills have *any*
v2 dimension (`extraction_version` present on 44) — so a re-run is the lever for **all** dimensions, new
and existing, not just these four.

### 2a. Model choice — measured (2026-07-13): hybrid, not Haiku-alone

A/B ran Haiku on the 44 bills that already have a Sonnet extraction (`tests/eval/ab_haiku_vs_sonnet_dims.py`,
via the now model-parameterized `SonnetExtractor(model=...)`). Result: status agreement **77%**,
present-detection **precision 84% / recall 87%** (Sonnet = truth), non-English recall held (FR 88%,
US 88%), 0 parse failures. Per-dimension bias: Haiku **over-triggers** pro_structure/labeling/fee (the
"mentioned ≠ operative" tell) and **under-detects** bans_restrictions (missed 8/20). The test did NOT
score sub-metric *numeric* accuracy (thresholds/dates) — Sonnet's strength and what the sub-metric audit
needs — so the real Haiku-alone gap is at least this big.

**Decision: hybrid.** Haiku-alone is too lossy for citable briefings (~15% presence error + per-dim bias
+ untested numeric drift). But 87% presence-recall makes Haiku a strong, cheap **triage**: Haiku first
pass answers "does this bill carry any dimension?"; **Sonnet does the precise extraction only on flagged
bills** (per-dim status, grounded excerpts, sub-metrics). Haiku false-positives just cost a few extra
Sonnet calls (not quality); the ~13% recall gap is the only risk, covered by a periodic full-Sonnet audit
sample. (Grounding-fail delta Haiku 63% vs Sonnet 47% is discounted — the 47% baseline shows the
verbatim-substring proxy is noisy on accented FR text.)

Steps:
1. **Extend the extraction schema** — add the four envelopes to the Sonnet dimension extractor
   (`app/classification/sonnet_extractor.py` / `scripts/extract_dimensions.py`). Each envelope =
   `{status, source_excerpt, confidence, + dimension-specific sub-metrics}` (see §3).
2. **Re-run over the ce_relevant corpus** (~1,900 US bills + the non-US rows). Multilingual Sonnet
   extraction is validated and the non-English corpus is 100% text-ready ([[structured-dimensions-multilingual]]);
   the US-text caveat is that full text is prod-only, so run against prod via the Cloud SQL proxy.
   Bump `extraction_version`. **Cost estimate:** ~1,900 × one Sonnet call ≈ bounded by
   `max_sonnet_calls_per_run`; batch/overnight like the other backfills. This is the dominant cost.
3. **Retrieval is already generic** — RULE 2 keys on `compliance_details[dim].status`, so no retrieval
   code change is needed once the envelopes exist. (A later refinement: let a dimension *narrow* an
   already-scoped set — today it's a standalone tier, so instrument+dimension doesn't AND. See §5.)

## 3. Sub-metrics per new envelope (answers "are we missing metrics *within* dimensions?")

Yes — this is worth a schema audit. A dimension's value is its sub-fields, and several existing envelopes
are thin. Proposed sub-metrics:

- `repairability`: `has_repair_score` (bool), `score_scheme` (e.g. FR indice de réparabilité / EU repair
  index), `parts_availability_years`, `manuals_required`, `disassembly_required`, `obsolescence_clause`.
- `reuse_refill`: `reuse_target_pct`, `target_year`, `scope` (packaging/foodware/…), `refill_infrastructure_required`.
- `digital_product_passport`: `dpp_required`, `data_fields` (composition/provenance/repair), `carrier`
  (QR/RFID), `effective_year`.
- `remanufacturing`: `refurb_standard`, `remanufacture_allowed`, `secondary_material_target`.

**Existing-envelope audit (do in the same pass):** confirm each of the 8 current dimensions captures its
key metric — e.g. `recycled_content.min_pct` + `.effective_year` + `.material_scope`;
`collection_targets.rate` + `.deadline`; `eco_modulation.criteria` (durability/recyclability/etc);
`fee_amounts.schedule`. If any is missing, add it here — the re-run is the moment to fix it.

## 4. The dim ⇄ instrument dual-axis question (recycled_content/labeling have both — should others?)

**Why the overlap exists and is correct:** `instrument` = the bill's *dominant policy type* (mostly one
per bill — "this is a recycled-content law"). `dimension` = a requirement facet *present within* a bill
(many per bill — "this EPR law also carries a recycled-content clause"). A concept belongs on **both**
axes when it commonly appears as *both* a standalone law type *and* an embedded provision. That's exactly
recycled_content and labeling.

Applying the test:
- **repairability ⇄ right_to_repair** — already dual: `right_to_repair` is the instrument (the law type),
  `repairability` the facet. ✓ No new instrument needed.
- **reuse_refill** — standalone reuse-mandate laws do exist (125-bill signal). **Candidate for an
  instrument twin too** (`reuse` instrument) if the corpus shows enough standalone reuse laws — check
  before adding. For now: dimension only.
- **digital_product_passport, remanufacturing** — almost never a bill's dominant type; embedded provisions
  → **dimension only** is correct.

**The reverse gap (instruments with no dimension twin):** `deposit_return`, `epr`, `product_stewardship`,
`chemical_restriction` exist only as instruments. A bill can *embed* a deposit or a chemical restriction as
one provision among many, so a `deposit_return` / `chemical_restriction` **dimension** would be defensible
for completeness — low priority, but the same principle. Recommendation: adopt the rule **"extract every
requirement facet (multi-label dimensions) + classify the one dominant instrument"**, and let the two axes
overlap wherever a concept is both a law-type and a provision.

## 5. Open follow-ons

- **Dimension-as-refinement** — today a routed dimension is a standalone retrieval tier (RULE 2, only when
  unscoped). To answer "repair-index bills *in the EU*" it must AND with place/instrument scope. Small
  `_scope_extra`/`_relevant_bills` change; do it when the envelopes land.
- **Router dimension-emission softness** — the LLM router under-emits DPP/remanufacturing; retrieval uses
  the deterministic `_map_dimension` (solid) today, so low urgency, but tighten the prompt before the
  router drives retrieval directly.

## 6. Water / ocean — a SCOPE blind spot, not a dimension (flagged 2026-07-13)

Raised in review: river-cleanup acts, blue economy, ocean health. This is **not** a dimension (not a
producer compliance facet) and **not currently caught** — there are *zero* water/ocean inclusion terms in
`data/seed/epr_keywords.json`, so the classifier is actively *dropping* these bills unless they trip a
plastics/packaging term. It's a genuine scope gap, and it splits in two:

1. **Marine plastics / microplastics / ocean plastic pollution** — directly circular-economy-adjacent
   (upstream of it is single-use-plastic and packaging EPR). Lowest-friction inclusion: a
   `marine_plastics` / `microplastics` **material** tag + keyword terms; largely folds into the existing
   plastics regime. Likely worth doing.
2. **River cleanup / blue economy / ocean health / fisheries / water quality** — broader environmental &
   marine policy, mostly *outside* the current EPR/circular-economy remit. Including it is a deliberate
   **scope expansion** on the model of the biological-cycle expansion ([[biological-cycle-scope]]) — new
   keyword theme + classification-scope change + likely new sources. **This is a product-scope decision,
   not a dimension add** — recommend deciding it explicitly rather than bolting on.

Recommendation: treat #1 as a small material/keyword addition to evaluate, and #2 as an explicit
scope-expansion decision (its own mini-plan if yes). Either way it does **not** ride on the dimension
extraction re-run.
