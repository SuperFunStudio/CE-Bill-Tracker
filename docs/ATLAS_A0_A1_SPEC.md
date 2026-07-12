# Atlas Circular — A0 + A1 Implementation Spec

Draft date: 2026-07-11. Status: **spec, about to build.** Concrete build plan for the two phases
scoped into this major update (see `docs/ATLAS_CIRCULAR_ROADMAP.md`): **A0** the jurisdiction backbone
+ persistence primitive, **A1** the scalable facet-hybrid analysis engine that replaces the brittle
`_relevant_bills` cascade and closes the §2a failures.

Grounding (current schema): `Bill.region` = 2-char country/family code (`US`, `EU`, `FR`, `DE`, `CN`,
`CA`, `GB`, `JP`, `ES`, `AU`, …); `Bill.state` = 2-char sub-code (US state, or same as region for
national law, `EU` for EU-wide). `(region, state)` disambiguates — `(US,CA)`=California vs
`(CA,CA)`=Canada. Alembic head = `035`. Explorer facets already exist in `GET /bills` (state, region,
regions, status, material_category, instrument_type, policy_stance, dimensions, urgency, year(_from/to),
min_confidence).

---

## A0 — Jurisdiction backbone + persistence

### A0.1 `jurisdiction` table (migration `036_jurisdiction`)

```
jurisdiction
  id           serial PK
  parent_id    int NULL FK jurisdiction(id)
  level        text NOT NULL  -- 'world' | 'bloc' | 'country' | 'state' | 'municipality'
  code         text NOT NULL UNIQUE  -- 'WORLD','EU','US','FR','US-CA','CA','CA-BC','US-CA-SF'
  name         text NOT NULL         -- 'France','California','Canada'
  aliases      text[] NOT NULL DEFAULT '{}'  -- ['France','French','FR','République française']
  path         ltree NOT NULL        -- 'world.us.us_ca'  (fast subtree queries)
  bill_count   int NOT NULL DEFAULT 0 -- denormalized, refreshed by a job (cheap atlas nav)
  indexes: GIST(path), GIN(aliases), unique(code)
```

- Requires the `ltree` extension (`CREATE EXTENSION IF NOT EXISTS ltree` in the migration).
- **Code scheme:** hierarchical + unambiguous. Country = its 2-char (`FR`, `US`, `CA`=Canada);
  US state = `US-<st>` (`US-CA`=California); provinces `CA-BC`; municipalities `US-CA-SF`. This is
  what resolves the `CA` collision the flat columns can't.
- **`aliases` is the retrieval fix** — `France → ['France','French','FR']`, so "examples from France"
  resolves to the FR node even though AGEC's title has no "France" token.

### A0.2 Attach bills

- Add `Bill.jurisdiction_id int NULL FK` (same migration). Keep `region`/`state` as denormalized
  mirrors during transition (**dual-write**; drop them only after A2 proves the new path).
- Add `idx_bills_jurisdiction` on `jurisdiction_id`.

### A0.3 Seed + backfill (`scripts/backfill_jurisdictions.py`, idempotent)

1. **Seed the tree** from a static map in code (`app/geo/jurisdictions.py`): `WORLD` → blocs/countries
   → US states / provinces. Countries + US states + the ~27 live regions, each with `name` + `aliases`
   (country names, demonyms, ISO codes; US state names + abbreviations + nicknames). Municipalities
   are **not** seeded now — the schema just permits them (Pillar D).
2. **Map every bill** by its `(region, state)` pair to a jurisdiction `code`:
   - `(US, US)` → `US` (federal) · `(US, CA)` → `US-CA` · `(EU, EU)` → `EU` (bloc) ·
     `(FR, FR)` → `FR` · `(CA, CA)` → `CA` (Canada) · `(CA, BC)` → `CA-BC` · etc.
   - Unmapped pairs are logged, not silently dropped (surfaces any data we haven't modeled).
3. Set `Bill.jurisdiction_id`; refresh `jurisdiction.bill_count`.
4. Verify against prod via the Cloud SQL proxy: every ce_relevant bill has a `jurisdiction_id`;
   AGEC (id 107838) resolves to `FR`; spot-check the `(US,CA)` vs `(CA,CA)` disambiguation.

### A0.4 Persistence primitive (migration `037_research_sessions`)

`research_session` (id uuid, owner_user_id NOT NULL, title, visibility default `private`,
share_token null, created/updated) + `research_turn` (id, session_id, seq, question, rewritten_query,
facets jsonb, strategy, answer jsonb, bill_ids int[], bill_total int, created_at). Per
`PUBLIC_AFFAIRS_RESEARCH_DESIGN.md` §4. Tables land now (backbone); wiring `/ask` to write them is the
first thing A1 does. Not exposed to users until A2.

---

## A1 — Scalable facet-hybrid engine

Replaces `_relevant_bills` (single-tsquery cascade) with a router → filter∩rank → narrate pipeline.

### A1.1 NL→facet router (`app/api/research_facets.py`)

One cheap Haiku call parses the question into facet *strings* + residual free text; a **deterministic
resolver** then maps strings → concrete ids/enums (LLM never invents codes):

```
router(question) -> {
  places:      ["France"],          # -> resolver: alias match -> jurisdiction ids (subtree)
  materials:   ["tires"],           # -> material_categories enum
  instruments: [], dimensions: [],  # -> existing vocab (the 8 dimension keys, instrument_types)
  statuses:    [], year_from/to: null,
  free_text:   "anti-waste law",    # residual -> FTS
  intent:      "lookup|list|compare|count"
}
```

- **Place resolution** is deterministic: `SELECT id, path FROM jurisdiction WHERE :s = ANY(aliases)`
  (case-insensitive), then filter bills by `path <@ node.path` (subtree — "US" pulls all states).
- First turn only; follow-ups (A2) prepend the thread via the contextual rewrite.
- Cost guard: skip the LLM when the question is empty/trivial; cache identical (question) within a
  session.

### A1.2 Retrieval (`_relevant_bills` rewrite)

```
base = Bill WHERE ce_relevant
   [AND jurisdiction_id IN (subtree of resolved places)]     # authoritative — fixes "France"
   [AND material_categories && :materials]
   [AND instrument_types && :instruments]
   [AND compliance_details[:dim]->>'status' = 'present' ...]  # per dimension
   [AND status / year filters]
   [AND (text_tsv @@ tsq OR meta_doc @@ tsq)]                 # only when free_text present
```

- **Facets are authoritative; free_text is relevance within them.** If facets present + no free_text →
  a ranked *listing* (like the Explorer). If free_text present → hybrid. This subsumes the old
  3 tiers; the OR-broad noise that buried AGEC at rank 346 is gone because a France query is a
  jurisdiction filter, not a word match.
- **Ranking** (composite, deterministic for stable paging):
  `score = greatest(ts_rank(text), ts_rank(meta)·w_title) + w_enacted·is_enacted + w_recent·recency`
  with title/exact-match boost. Order by `score DESC, id DESC`. Pure-facet listings order by recency.
- Returns the same `(rows, total, strategy)` contract + the resolved `facets` for display.

### A1.3 Narration contract (the "never lies" rule)

The LLM is handed: the **facet interpretation** (so the UI can show "Interpreting *France* →
jurisdiction: France (12 bills)"), **counts** (total + by-facet), and a **representative sample**
(top-N by score). Rules tightened in the system prompt:
- The faceted set + counts are ground truth; **never assert a bill/topic is absent** — describe
  coverage relative to totals ("of the 12 French bills, the sample shows…").
- A true zero is now *accurate* (the facet filter is authoritative), so "no bills match
  jurisdiction=France" is a real, safe statement — the failure mode where it said that while AGEC sat
  at rank 23 cannot recur.

### A1.4 Endpoints

- `POST /research/ask` — router → retrieval → narrate; writes a `research_turn`; returns answer +
  `facets` (interpretation) + bills page 1 + total + session_id. LLM cost unchanged (1 narration +
  1 cheap router call).
- `GET /research/bills` — paginate the same faceted set (re-run router+filter deterministically, or
  accept resolved facets); SQL-only.

### A1.5 Verification (regression = the bugs that started this)

Against prod via proxy, assert:
1. "Is there any examples from France to compare to the US?" → set includes FR-jurisdiction bills
   incl. AGEC; sample is not all-EU; answer does not claim France is absent.
2. "records about the france anti waste law? AGEC?" → AGEC near the top (jurisdiction FR + title
   "anti-waste"), not rank 346.
3. Regression on the good cases: "most compelling incentives" still returns the eco-modulation set;
   "deposit return beverage container" still precise; paging stable + non-overlapping.
4. Every prior §2a failure has a passing assertion before A1 is called done.

---

## Build order

1. `036_jurisdiction` migration + `app/geo/jurisdictions.py` seed map + `Jurisdiction` model.
2. `scripts/backfill_jurisdictions.py`; run + verify on prod (proxy).
3. `037_research_sessions` migration + models.
4. `app/api/research_facets.py` router + resolver.
5. Rewrite `_relevant_bills` → facet-hybrid; update `/ask` + `/research/bills`; tighten prompt.
6. Verification script (A1.5) green on prod, incl. the AGEC/France regressions.
7. Migrations applied to prod via the standard deploy (manual `alembic upgrade` if the lock-guard is
   needed — see [[deploy-mechanism]]).

## Open (decide in-flight, non-blocking)

- Ranking weights (`w_title`, `w_enacted`, `w_recent`) — tune against the regression queries.
- Ambiguous place names (e.g. "Georgia" US-state vs country) — resolver returns both; the answer
  surfaces the ambiguity. Punt multi-match UX to A2.
- Whether `/research/bills` re-runs the router (simplest) or takes resolved facets (fewer LLM calls).
  Recommend re-run for now; router is cheap + deterministic.
