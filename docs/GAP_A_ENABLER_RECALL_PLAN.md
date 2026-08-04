# Gap-A: Cross-jurisdiction enabler recall pass

## Why

Ask-the-Atlas under-represents *enabler* instruments (recycled-content procurement, funding/
incentives, right-to-repair, deposit/fee levers). The federal-enabler seed
([federal-enablers-corpus] work) fixed the US-federal hole by **curating out-of-corpus** items.
This pass tackles the complementary hole: enabler bills **already ingested** but wrongly parked
at `ce_relevant = false`, so they never surface. It generalises the 2026-07-30 manual
`ce_relevant=false` review (run_id `manual-review-flip-2026-07-30`) from a hand pass into a tooled,
auditable one, under the "enablers of the circular economy" scope principle.

## What the data proved (2026-08-03, local corpus)

- **Op2 (re-instrument the already-relevant `other`/NULL bucket) is a no-op.** Tight enabler nets
  over `ce_relevant=true AND instrument_type in ('other',NULL)` return ~0 (recycled-content 0,
  incentives 1, repair 0, deposit 3). `reclassify_other.py` / `reclassify_incentives.py` already
  drained it. The noisy `ilike` counts ("stewardship 2900", "recycled content 1388") were false
  positives. **Drop Op2.**
- **Op1 (relevance recall from `ce_false`) is the action**, and it is small + US-centric:
  ~603 tight-net candidates, **US 551 / FR 15 / CA 12 / UK 5 / CN 5 / AU 4 / …**.
  By family: deposit/fee 522, recycled-content procurement 77, incentives/funding 23, repair 9.
- **Foreign enabler gaps are NOT recoverable here.** Foreign law bypasses the ingest keyword gate,
  so foreign enablers aren't sitting in `ce_false`; the ~44 foreign candidates are the tail, not the
  gap. The EU/UK green-public-procurement hole is **Gap-B curation** (apply the federal-seed model),
  tracked separately.
- **Precision demands an LLM judge.** A random deposit-net sample was mostly noise ("Broomrape
  Control Program", "Legal *Deposit* of Publications", "insurance telematics", "SUBSIDY REPAYMENT").
  A deterministic-only flip would pollute the corpus with hundreds of junk rows.

## Design — net → judge → gated apply (reuses existing machinery)

Model on `scripts/backfill_adjacency.py` (dry-run default, `--dsn` prod tunnel, `classification_changes`
old/new snapshot + run_id + one-query undo). New script: `scripts/recall_enablers.py`.

1. **Candidate generation** — tightened compound nets over `title||ai_summary||description`, only
   `ce_relevant=false`. Families + fixes:
   - `recycled_content` : (recycled|recovered|post-consumer) content/material NEAR (procure|purchase|
     buy|minimum|standard|mandate).
   - `incentives`       : (grant|rebate|tax credit|subsidy|revolving fund|low-interest loan) NEAR
     (recycl|compost|reuse|remanufactur|circular|repair).
   - `right_to_repair`  : (right to repair|repairability|spare/replacement parts).
   - `deposit_return`   : **tighten** — require a beverage/container context AND a return/redemption/
     refund token; exclude "legal deposit", "deposit account/insurance/subsidy". (Kills the 522→~sane.)
2. **Adjudication** — reuse `app/classification/haiku_classifier.py`. Per candidate, judge against the
   enabler rubric → `{is_enabler: bool, instrument_type, confidence, reason}`. Cheap: a few hundred
   Haiku calls.
3. **Apply** (gated) — for accepted candidates set `ce_relevant=true`, `instrument_type` = judged
   family (prepended into `instrument_types`), `reviewed`/`needs_review` per the apply policy below.
   `adjacency` stays **NULL** — these are core CE (wrongly excluded), not adjacent, unlike the
   transboundary/toxics nets. Every change → `classification_changes` under run_id
   `enabler-recall-<date>`.

## Guardrails

- **Dry-run default**; `--commit` writes; `--dsn` for the prod tunnel (same contract as
  backfill_adjacency).
- **Confidence bands**: auto-apply ≥ high; route the middle to `needs_review=true` (visible but
  flagged); drop rejects. (Policy is a decision below.)
- **Idempotent**: a second run finds no `ce_false` matches left in the accepted set.
- **One-query undo** via the run_id (delete the audit rows + restore old_value), exactly as
  backfill_adjacency documents.
- **Precision sample before commit**: print a random N of accepted flips for eyeball, like this scope.

## Decisions (see conversation)

1. Apply policy: auto-apply high-confidence vs route everything to `needs_review` for human sign-off.
2. Build now (local dry-run first) vs land after the federal prod deploy.

## Out of scope (→ Gap-B curation, separate)

Foreign/EU/UK green-public-procurement and other enablers never ingested. Use the federal-seed
pathway (curated JSON → keyless full-text fetch → region-tagged import) once recall confirms the hole.
