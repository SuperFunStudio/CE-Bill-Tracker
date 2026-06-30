# V2 — Full-Text Bill Search with Material-Attribute Precision & In-Text Highlighting

**Status:** Plan / not started. Layer A (structured resin filter) shipped 2026-06-25 — see [[polymer-resin-extraction]].
**Driver:** Customer feedback on the V1 prototype — they need to search *down to material attributes* (resin level, e.g. `EVA foam`, `HDPE`, `expanded polystyrene`), not just the AI summary. Stretch goal for this revision: when a term matches, **show where it appears in the bill text** (snippet + highlight), so the user can see the actual statutory language.

**The bigger payoff — covered-product discovery the summary omits.** The driver isn't only resins. A bill's statutory definitions enumerate *covered products* that the short `ai_summary` flattens away. Canonical example: **SB 707** (CA textile EPR) covers **footwear / shoes** in its definitions, but the summary just says "textiles" — so searching "shoes" returns nothing today, even though the bill genuinely covers them. Full-text indexing makes any product, material, or entity named in the bill text findable, even when our summary never mentioned it. This directly strengthens [[product-coverage-extraction]] (covered-product grid) — same root cause: the detail lives in the text, not the summary.

---

## 1. Why today's search can't do this

Current search is **client-side, over a static snapshot**:

- The bills list ships to the browser as a snapshot of `BillSummary` rows. `applyBillFilters()` in `dashboard-next/src/components/bills/BillFilters.tsx` does `title / ai_summary / bill_number .includes(q)` in memory.
- **The extracted bill text is never stored.** `bills` (see `app/models.py`) has `title`, `description`, `ai_summary`, `compliance_details` — no full-text column. When the pipeline needs text it fetches it live and discards it.
- Resin-level terms (`EVA`, `HDPE`) usually **don't appear in the AI summary** — they live in the statutory text. So the customer's terms return nothing today even when the bill is a match.

**Consequence:** material-attribute search and highlighting both require the full text to be *persisted and indexed server-side*. This is a backend feature, not a frontend filter.

## 2. What we can reuse (already built)

We are not starting from zero — the hard part (reliably getting clean bill text) is solved:

- **Text-fetch ladder** — `scripts/scan_bill_polymers.py` already fetches each bill's full text via the proven path: `OpenStatesClient.get_text_from_source(source_url)` (direct state-site scrape, no quota) → `get_bill_text(openstates_id)` → LegiScan `getBillText` as last resort. Handles HTML and PDF (`_extract_pdf_text`).
- **Controlled resin detector** — `app/classification/polymers.py::detect_polymers(full_text)` returns high-precision resin codes (`HDPE`, `EVA`, `EPS`, …). The scanner already writes them to `bills.compliance_details['polymers']` (JSONB, no migration).
- **Per-bill detail API** already returns `compliance_details`, so structured resin tags can surface immediately.

So the resin *signal* is already extractable; what's missing is (a) persisting the text for keyword search + highlighting, and (b) a search endpoint.

## 3. Two layers — ship them in order

### Layer A — Structured resin filter ✅ SHIPPED 2026-06-25
Resin codes from `compliance_details['polymers']` surfaced as a `BillSummary.polymers` field + an
auto-hiding "Resin / Polymer" multiselect. 38 prod bills tagged across 9 resins. Details in
[[polymer-resin-extraction]]. No free-text, no highlighting — that's Layer B.

---

## Layer B — Full-text search + in-text highlighting (detailed scope)

**Status: ✅ SHIPPED & LIVE ON PROD (2026-06-26).** Steps 1–7 built, migration 028 applied, backfill
done (**1,458/1,535 bills indexed, 95%**), code deployed (api revision signalscout-api-00093), and
`ENABLE_BILL_TEXT_REFRESH=true` enabled so the daily refresh job keeps the index current. Verified on
prod: `/bills/search?q=footwear` returns highlighted hits; `/bills/text-coverage` → {1458, 1535}.

Goal: a user types `shoes`, `EVA foam`, or `SB 707` and gets every bill whose **statutory text**
matches — even when our `ai_summary` never mentioned it — each result showing the highlighted
snippet where the term appears.

### Decisions (resolved — were the open questions in the prior draft)

- **D1 · Storage = separate `bill_texts` table** (not a column on `bills`). Keeps the large text and
  its index out of the snapshot-baked `/bills` list query, which must stay cheap and text-free.
- **D2 · Index = `english` FTS as the core, `pg_trgm` as a targeted supplement.** The `english`
  dictionary already tokenizes abbreviations as standalone tokens, so `websearch_to_tsquery('english',
  'HDPE')`/`'shoes'`/`'"EVA foam"'` all match (and quoted phrases + OR come free). `pg_trgm` is
  **already enabled in prod** (migration 002) — add a trigram index only as a fallback for true
  substring/partial/fuzzy queries (e.g. `polyeth*`, glued punctuation) if testing shows FTS gaps. So
  the "english vs. exact codes" question resolves to: english FTS handles both; trgm is an optional
  enhancement, not a parallel system.
- **D3 · UX = keep the instant client filter; add full-text as an opt-in deep search.** The current
  title/summary/bill_number client-side filter stays exactly as-is (free, instant). When a term is
  present, fire a debounced live `GET /bills/search?q=` and render its hits as a **separate, labeled
  result group** ("_N more bills mention '<term>' in their full text_") with highlighted snippets.
  This is honest (summary-match vs. deep-text-match are visually distinct), preserves the snappy
  default, and only pays DB cost on demand. Minimal alternative: a single "Search full text" checkbox.
- **D4 · Backfill scope = all `ce_relevant` bills (~1,535)**, not just plastics — the SB 707/shoes
  case is textiles, so resin-only scope would miss the main payoff.
- **D5 · Ingest = decoupled refresh job, not inline.** Don't block the hot ingest path on a text
  fetch; mark rows stale and refresh in a scheduler job.

### Step-by-step

1. **Migration 028 + model** (`alembic/versions/028_bill_texts.py`, `app/models.py`)
   - `bill_texts`: `bill_id` PK/FK→`bills.id` `ON DELETE CASCADE`; `text TEXT`;
     `text_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED`;
     `char_len INT`; `source VARCHAR` (`source_url`|`openstates`|`legiscan`);
     `indexed_change_hash VARCHAR` (skip re-fetch when the bill's `change_hash` is unchanged);
     `fetched_at TIMESTAMPTZ`.
   - Indexes: `GIN(text_tsv)`; **optionally** `GIN(text gin_trgm_ops)` (trgm already available — but
     measure: a trigram index over 128k-char documents is large; defer until a query gap proves it
     needed). `BillText` ORM model + a `text` relationship/loader that is **never** eager-loaded on the
     list query.

2. **Factor the fetch+clean helper** (`app/ingestion/bill_text.py`)
   - Pull the proven ladder out of `scripts/scan_bill_polymers.py`:
     `get_text_from_source(source_url)` → `get_bill_text(openstates_id)` → LegiScan `getBillText`,
     reusing the PDF/HTML cleaners (`_extract_pdf_text`, whitespace-normalize). Expose
     `async fetch_clean_text(bill) -> tuple[str, source]`. `scan_bill_polymers.py` then imports this
     instead of carrying its own copy (removes duplication).

3. **Backfill script** (`scripts/backfill_bill_text.py`)
   - Same shape as `scan_bill_polymers.py`/`backfill_deadlines.py`: `--dsn`, `--dry-run`, `--limit`,
     resumable (skip bills whose `bill_texts.indexed_change_hash == bills.change_hash`),
     NULL-safe candidate filter (the bug noted in [[polymer-resin-extraction]]). Run against prod via
     Cloud SQL proxy. **Estimate:** ~1,535 bills × ~9s ≈ **~4 h** (batch/overnight); storage ≈
     **30–60 MB** text + GIN index. Text reachability ~95% (420/439 in the plastic sample).

4. **Search endpoint** (`app/api/bills.py`, `app/schemas.py`)
   - New route `GET /bills/search?q=&limit=` (separate from the snapshot-baked `/bills`).
   - Query: `... JOIN bill_texts t WHERE t.text_tsv @@ websearch_to_tsquery('english', :q)`,
     ranked by `ts_rank`.
   - Snippets: `ts_headline('english', t.text, websearch_to_tsquery('english', :q),
     'StartSel=<mark>,StopSel=</mark>,MaxFragments=3,MinWords=5,MaxWords=18')` — Postgres returns the
     highlighted fragments; **no full text ever ships to the browser**.
   - Response `BillSearchHit(BillSummary)` adds `snippets: list[str]` and `text_indexed: bool`.

5. **Frontend** (`dashboard-next/src/hooks/useBills.ts`, `lib/api.ts`, `BillFilters.tsx`, `BillTable`/results)
   - `useBillTextSearch(q)` mirrors `useCompanies(search)`: enabled only when `q` is non-empty,
     debounced (~300 ms), `queryKey: ['billSearch', q]`.
   - Render the hits as the separate "found in full text" group with the `<mark>` snippets styled
     (sanitize: only `<mark>` is allowed — escape everything else server-side or render via a tiny
     allowlist, never `dangerouslySetInnerHTML` on raw text).
   - Bill detail page: scroll-to + highlight the first match (optional polish).

6. **Ingest refresh job** (`app/scheduler/jobs.py`)
   - Periodic `refresh_bill_texts`: select bills where `change_hash` differs from
     `bill_texts.indexed_change_hash` (or no row), fetch via `fetch_clean_text`, upsert. Bounded batch
     per run so it never floods LegiScan quota. Keeps the index current without touching the hot path.

7. **Coverage honesty** (UI)
   - Per the `bill_texts.text_indexed` flag, show "full text not indexed" on bills we couldn't fetch,
     so an empty deep-search result reads as "not in our text" only for indexed bills — never a silent
     false negative (the WA/CO fetch gaps from [[deadlines-backfill-pipeline]] still apply).

### Effort & sequencing (each step independently shippable)

| Step | Work | Rough effort |
|------|------|--------------|
| 1 Migration + model | additive table, GIN(tsv) | ~0.5 d |
| 2 Fetch helper | factor existing ladder | ~0.25 d |
| 3 Backfill + prod run | script + ~4 h run | ~0.5 d + run |
| 4 Search endpoint | FTS + `ts_headline` | ~0.5 d |
| 5 Frontend | hook + snippet group + sanitize | ~1 d |
| 6 Refresh job | scheduler stale-scan | ~0.5 d |
| 7 Coverage UI | indexed flag | ~0.25 d |

Build order: **1 → 2 → 3** (data first), then **4 → 5** (the feature), then **6 → 7** (durability +
honesty). Steps 4–5 can demo against the backfilled data before the refresh job exists.

### Risks / watch-items
- **Trigram index size** over large documents — measure before adding (D2); FTS alone may suffice.
- **`ts_headline` cost** — it re-parses the document per hit; fine at this scale (hundreds of hits),
  but cap `limit` and consider `ts_headline` only on the returned page, not the full match set.
- **HTML/`<mark>` injection** — sanitize snippet rendering (step 5).
- **LegiScan quota** — 30k/mo; backfill (~1.5k) and the bounded refresh job both fit, but the refresh
  batch size is the throttle to set.
- **Coverage ≠ complete** — ~5% of bills never fetch; surface it (step 7).

## Downstream re-runs unlocked by persisted text

Persisting full text removes the per-bill **fetch bottleneck** that limited every text-based extraction
to a subset — so re-running them across the full corpus (reading `bill_texts`, no re-fetch) becomes cheap.
Nothing *must* re-run (Layer B is additive; all pages keep working), but these are worth it:

| Re-run | Powers | Cost | Why |
|--------|--------|------|-----|
| `extract_responsibility_chain` | "who's next responsible" chain | **FREE** (heuristic) | coverage was only ~30–38 bills → full corpus, zero LLM cost |
| `build_product_coverage` | covered-product grid | paid (cheap, Haiku) | catches products the summary omits — the **SB 707 / footwear** case; only run on electronics+batteries so far |
| `backfill_deadlines` | Upcoming Deadlines page | paid (Sonnet, $$) | closes coverage gaps incl. WA/CO; budget it |
| `extract_management_model` | PRO/individual/govt model | paid (LLM) | result is currently **local-only, never pushed to prod** — run against prod regardless |

Not worth a corpus re-run: `scan_bill_polymers` (resins cluster in plastics, already done), `build_r2r_electronics_set` (curated/narrow), `measure_stance_precision` (eval, not data), Insights (metadata-only).
**Meta-bottleneck:** Design Guide + fee citations read `compliance_details` from the **paid Sonnet Stage-3 extraction** (~211/1,535 bills) — persisted text makes scaling that cheaper, but it's the biggest paid decision and cascades into deadlines/design-guide/fees/chain at once.
⚠️ `extract_responsibility_chain` and `scan_bill_polymers` both R-M-W `compliance_details` — never run concurrently.

## Beyond Layer B — generalize to material-attribute detectors (fibers next)

**Decision (2026-06-25):** generalize `polymers.py` into a family-agnostic material-attribute framework;
**fibers is the next family after Layer B**; **metals deferred** (no stated need yet).

- **Generalize the framework.** `polymers.py` is already family-agnostic in shape (the `Polymer`
  dataclass = code, name, spelled regex, gated abbrev, context window). Refactor into per-family
  vocabularies (`POLYMERS`, `FIBERS`, …) each with its own context-cue regex, writing to
  `compliance_details` (e.g. a `materials` map or per-family keys). Layer B makes *running* any detector
  cheap (read `bill_texts`).
- **The bar for a controlled detector, post-Layer B:** FTS already covers open-ended terms
  (search "polyester"/"aluminum") for free. So build a controlled detector only where a family deserves a
  **precise, filterable facet** beyond raw search — i.e. there's persona demand AND false-positive risk
  that free-text can't handle cleanly. **Gate on demand, not capability.**
- **Fibers (next):** the textile analog of resins — directly serves the SB 707 / textile-EPR thread
  (footwear, apparel composition), and precision on `polyester`/`nylon`/`acrylic` is real. **Resolve the
  fiber↔polymer overlap up front:** polyester≈PET, nylon≈PA (already in `POLYMERS`), acrylic, spandex≈PUR
  are *already polymers* — a "Fiber" facet should be a **curated view over those + the natural fibers**
  (cotton, wool, silk, linen, hemp, rayon/viscose), not a parallel list. Surfaced as a "Fiber" multiselect
  in `BillFilters`, exactly like the resin filter (Layer A).
- **Metals (deferred):** not requested. If a battery/e-waste persona later asks, do a *narrow,
  high-precision* list (lithium, cobalt, lead-acid, aluminum) gated on battery/recycling context — never a
  broad metals taxonomy: spelled metal names are common English words and `lead` (the verb) is a severe
  false-positive landmine. Until then, lean on Layer B FTS.

---
*Foundation files: `scripts/scan_bill_polymers.py` (fetch ladder to factor out), `app/ingestion/openstates.py` (`get_text_from_source`/`get_bill_text`/`_extract_pdf_text`), `app/ingestion/legiscan.py::get_bill_text`, `app/ingestion/coordinator.py` (`change_hash` upserts = refresh trigger), `alembic/versions/002_company_impact_schema.py` (pg_trgm + GIN trgm pattern), `app/company_intel/resolver.py` (similarity query pattern), `dashboard-next/src/hooks/useCompanies.ts` (snapshot→live search), `dashboard-next/src/components/bills/BillFilters.tsx` (search input + `applyBillFilters`). Next migration number: 028 (027 is latest).*
