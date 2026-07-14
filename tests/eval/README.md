# Router eval — golden set

Ground-truth eval for the NL→facet query-understanding router (Atlas A1, roadmap Pillar B). The goal:
**measure any router against fixed failure cases before writing it**, so "the scanner can't do X" is a
number, not a vibe.

- `router_golden.json` — the cases (hand-curated ground truth; see the `meta` block for the full schema,
  role/intent vocab, and slug sources).
- `score_baseline.py` — grades **today's deterministic resolver** against the set. Run first to record
  the starting line.

## Run

```
venv/Scripts/python.exe tests/eval/score_baseline.py
```

## Baseline (deterministic resolver, DB mode, 2026-07-13)

Full run with places scored (`--dsn` against local Postgres, alembic 037, 80 jurisdiction nodes). Place
*resolution* only reads the `jurisdictions` alias table, which is the `app/geo` seed — identical across
lanes and independent of the bills corpus — so local scores place resolution exactly as dev-once-migrated
would. (Dev was 2 migrations behind at the time — see below.)

| metric | score | reading |
|---|---|---|
| slug extraction F1 (overall) | **0.98** | the scanner *finds* the right facets |
| free_text strip (includes/excludes) | **22/22** | residual for FTS is clean |
| place / reference role | **100%** | jurisdiction + `reference`-role handled deterministically (via `_EXPANSION_CUES`) |
| role accuracy — illustrative-vs-filter | **67%** (8/12) | it can't tell an example from a filter |
| role accuracy — negation | **83%** (5/6) | can't express `exclude` (California added as a filter) |
| role accuracy — overall | 87% (39/45) | high only because most cases are all-filter |
| intent accuracy | **0%** (0/22) | no intent field at all |

**The thesis, sharpened by the DB run:** places and reference-role are effectively *solved* by the
deterministic resolver. The router's value is concentrated in exactly three places:
1. **illustrative-vs-filter** (67%) — the `"electronics like phones"` problem; the one thing only the LLM can do.
2. **intent** (0%) — lookup/list/compare/count is entirely absent today.
3. **alias-coverage misses** (slugF1 0.80 on `para-smartphone-repairability-gap`, `noreg-carpet-stewardship`)
   — "repairability"↛right_to_repair, "stewardship programs"↛pro_structure; the router generalizes past the alias tables.

Everything else (place resolution, most slug extraction, free_text) the scanner already nails — so the
router should be scoped to *add* those three, not re-do what works.

### Dev-lane finding (2026-07-13)
Dev (`signalscout_dev`) is at **alembic 035** and has **no `jurisdictions` table** — it's missing
`036_jurisdiction` + `037_research_sessions` (the whole A0 backbone). The router can't ship to dev until
those are applied + `scripts/backfill_jurisdictions.py` is run there. Local is at 037 and fully backfilled.

## Router v1 results (`app/api/research_router.py`, 2026-07-13)

One Haiku call (`route_query` forced tool) emits facet slugs + per-facet role + intent + residual
free_text; a deterministic binder validates every slug against the canonical vocab (LLM never invents a
code) and resolves place names against the jurisdiction table. Run: `--router --dsn <local>`.

| metric | baseline (deterministic) | router v1 |
|---|---|---|
| **intent** | n/a (no field) | **100%** (22/22) |
| illustration on the headline case (`electronics like phones`) | 2/4 | **4/4** |
| slug extraction F1 (overall) | 0.98 | 0.90 |
| role accuracy (overall) | 87% | 84% |
| free_text | 22/22 | 21/22 |

**Verdict: the router solves what it was built for (intent + illustration-vs-filter on the canonical
case) but is not yet a strict win** — slugF1 dropped 0.98→0.90. The drop decomposes into:

1. **Debatable golden expectations (adjudicate, don't tune away).** `most compelling incentives`,
   `carpet stewardship`, and (before a fix) `recycled-content mandates` — the router picks the
   **instrument** (`incentives` / `product_stewardship` / `recycled_content`, all real corpus values)
   where the golden encoded a **dimension** (`eco_modulation` / `pro_structure`). Those instrument slugs
   didn't exist when the deterministic dimension-map was written, so the router is arguably *more* right.
   These are ground-truth decisions for a human, not router bugs.
2. **Soft dimension detection.** "take-back"→`collection_targets`, "restrictions"→`bans_restrictions`
   don't reliably fire even with prompt hints; the router prefers an instrument or leaves it in free_text.
3. **Temp=0 is not deterministic.** The same question returned clothing/footwear as *illustration* on one
   run and *filter* on the next. **Consequence: the parse MUST be cached per question and never re-run
   per pagination page**, or result sets shift between pages. This is the concrete form of the
   paging-stability risk noted in the design.

**Next to make it a strict win:** (a) add a per-question parse cache (fixes determinism + halves cost);
(b) adjudicate the instrument-vs-dimension golden cases; (c) a bit more dimension-detection prompt work.
Then wire it into `/research/ask` in shadow mode (log router + deterministic side by side on real asks).

## Scoring a router (harness notes)

A router emits the same `Facets` contract (extended with per-facet `role` and a top-level `intent`). To
score it, reuse `score_baseline.py`'s comparison core but feed it the router's output instead of the pure
matchers, and turn on the two facets the offline baseline skips:

1. **Places** — run against a DB (or a seeded jurisdiction fixture) so `place` roles
   (`filter`/`reference`/`exclude`) and ambiguity (`ambig-georgia`) are scored.
2. **Intent** — exact-match `expect.intent`.
3. **free_text** — assert `free_text_includes` all survive and `free_text_excludes` are all stripped.

Ship the router in **shadow mode** first: run it beside the deterministic resolver on every real ask, log
both, and diff against this set weekly. Flip only when `illustrative-vs-filter` role and `intent` clear a
bar you set here — and when the `no-regress`/`regression` categories stay at 1.00.

## Extending the set

Add cases when a real ask surprises the router. Each case must pin: `intent`, every facet with its `role`,
and `free_text_includes`/`excludes`. Mark `source: prod-observed` for anything seen live (highest value),
and set `baseline.*` from a fresh `score_baseline.py` run. Keep discriminator **pairs** together — e.g.
`illus-epr-electronics-phones-laptops` (phones = illustration) next to `illus-discriminator-cover-laptops`
(laptops = filter) — they're what stop the router from over- or under-generalizing.
