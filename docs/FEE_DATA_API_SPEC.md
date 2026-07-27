# Fee Data API — Spec

**Status:** proposed (2026-07-27) · **Owner:** kenny · **Depends on:** nothing new — data already on prod
**Related:** memory `fee-data-api-feasibility`, `app/api/compliance.py`, `dashboard-next/src/lib/feeSchedule.ts`

## 1. Goal & framing

Expose the **bill-sourced fee data already extracted into `bills.compliance_details`** as a public REST/JSON
API, honestly split into two provenance layers:

| Layer | Source | What it is | Where it lives today |
|---|---|---|---|
| **A. Bill-sourced fee facts** | `compliance_details.fee_amounts` / `eco_modulation` envelopes | Typed, cited fee amounts + eco-modulation criteria *as stated in the measure* | Already on prod — **this spec exposes it** |
| **B. Curated fee schedules** | `app/scoring/ca_sb54_fees.py`, `feeSchedule.ts` | Runnable per-material rate tables + modulation math (CA/UK/JP…) | Existing `GET /compliance/fee-schedule` |

Layer A is the new work. **No LLM re-extraction, no new ingestion** — the data is in the corpus.

### Prod inventory (verified 2026-07-26, read-only probes)
- `fee_amounts` envelope present on **433** bills; **313** carry ≥1 numeric amount.
- **1,064** numeric rate entries (of 1,339 total), typed by `basis` + `currency`.
- `eco_modulation` present on **166** bills (163 with structured criteria).
- Every `present` envelope carries a verbatim `source_excerpt` → **the data is already grounded/cited.**

### Non-goals
- **Not** a universal formula engine. Statutes state *mechanism* ("0.1% of revenue", "£750/yr", "amount set by
  the council"), not a clean per-material formula. The runnable formula stays Layer B.
- **Do NOT** run `scripts/extract_fee_citations.py` / populate `bill_fee_citation` — that pipeline reads a legacy
  `compliance_details` field set + the empty curated `fees{}` block (0 published sources, 0 numeric on prod).
  It is superseded by this spec. Either delete it or repoint it at the envelopes in a later phase.

## 2. Data shape (source of truth)

From `app/classification/sonnet_extractor.py` (EXTRACTION_VERSION 5):

```jsonc
// bills.compliance_details.fee_amounts
{
  "status": "present|absent|not_applicable",
  "rates": [
    { "basis": "per_ton|per_unit|flat|eco_modulated|percent_revenue|unspecified",
      "amount": 750,            // number OR null (mechanism stated, amount set by rulemaking)
      "currency": "GBP",        // ISO 4217
      "material": "Producer registration fee (per producer per year)" }  // free-text descriptor
  ],
  "source_excerpt": "…verbatim quote, original language…"
}
// bills.compliance_details.eco_modulation
{ "status": "…", "criteria": ["recyclability", "recycled_content", …], "source_excerpt": "…" }
```

**Data-quality reality:** the `material` descriptor is free-text and the `rates[]` array mixes fee *kinds* —
genuine producer fees sit alongside registration caps, consumer incentives (MA "$18/mattress" social-impact
payment), de-minimis thresholds, and admin-cost floors. `basis` alone doesn't separate them. This spec adds a
derived `fee_kind` (§4) so consumers can filter to what they mean.

## 3. Endpoints

Add to the existing `app/api/compliance.py` router (`prefix="/compliance"`). All read, open + rate-limited
(same tier as `/fee-schedule` and `/pathways`). New Pydantic models in `app/schemas.py`.

### 3.1 `GET /compliance/fee-amounts`
One row **per rate entry** (flattened from `rates[]`), each carrying its bill context and provenance.

**Query params** (mirror `app/api/bills.py` conventions):
| param | default | notes |
|---|---|---|
| `region` | `all` | **Deliberate divergence** from bills.py's US-default: fee data is heavily cross-jurisdiction, so a fee product defaults to every region. Explicit code (`EU`) or `regions` CSV narrows. |
| `regions` | – | CSV, wins over `region` (as in bills.py `_parse_regions`) |
| `state` | – | sub-jurisdiction code |
| `status` | – | e.g. `enacted` |
| `basis` | – | one of the 6 basis values |
| `fee_kind` | – | derived (§4): `producer_fee\|registration\|incentive\|penalty\|threshold\|admin_cost\|unspecified` |
| `currency` | – | ISO 4217 |
| `has_amount` | – | `true` → only numeric rows (313-bill / 1,064-row set); `false` → mechanism-only rows |
| `material_category` | – | filter on the parent bill's `material_categories` |
| `limit` / `offset` | 100 / 0 | `le=5000`, as bills.py |

**Response** — `list[FeeAmountRow]`:
```jsonc
{
  "bill_id": 12345, "region": "US", "state": "MD", "bill_number": "HB-575",
  "bill_title": "…", "status": "enacted", "source_url": "https://…",
  "basis": "flat", "amount": 5000, "currency": "USD",
  "material": "Computer manufacturer initial registration fee",
  "fee_kind": "registration",           // derived, §4
  "grounded": true,                      // has source_excerpt
  "source_excerpt": "…verbatim clause…",
  "extraction_version": 5
}
```

**SQL** — read-time lateral unnest of the JSONB, no new table (Phase 0):
```sql
SELECT b.id, b.region, b.state, b.bill_number, b.title, b.status, b.source_url,
       r->>'basis'    AS basis,
       (r->>'amount')::numeric AS amount,
       r->>'currency' AS currency,
       r->>'material' AS material,
       b.compliance_details->'fee_amounts'->>'source_excerpt' AS source_excerpt,
       (b.compliance_details->>'extraction_version')::int AS extraction_version
FROM bills b
CROSS JOIN LATERAL jsonb_array_elements(b.compliance_details->'fee_amounts'->'rates') AS r
WHERE b.compliance_details->'fee_amounts'->>'status' = 'present'
  AND b.ce_relevant = true
-- + region/state/status/basis/currency/has_amount filters
ORDER BY b.last_action_date DESC NULLS LAST
LIMIT :limit OFFSET :offset;
```
`fee_kind` and `material_category` are applied in Python after fetch (fee_kind is derived; material_category
is an array-contains on the parent). Add a GIN index consideration only if the lateral scan is slow at 2.4k
bills — it won't be at this size.

### 3.2 `GET /compliance/fee-amounts/summary`
Cheap chartable aggregate for the Insights/dev surfaces — counts by `basis`, `currency`, `fee_kind`, and
`region`, plus `{bills_with_fees, bills_with_numeric, total_rate_entries}`. Drives the developers-page
example and a marketing stat.

### 3.3 `GET /compliance/eco-modulation`
Shape differs (`criteria[]`, not `rates[]`) → its own endpoint. One row per bill: `{bill_id, region, state,
bill_number, bill_title, status, source_url, criteria: [...], grounded, source_excerpt}`. Filters:
`region`/`regions`/`state`/`status`/`limit`/`offset`.

## 4. `fee_kind` derivation

A **deterministic, pure classifier** (`app/synthesis/fee_kind.py`) mapping `(basis, material_descriptor)` →
one of `producer_fee | registration | incentive | penalty | threshold | admin_cost | unspecified`. No LLM.
Rule order (first match wins), tuned against the corpus:

1. `penalty` — descriptor matches `/fine|penalty|violation|forfeit/i`.
2. `threshold` — `/minimum threshold|de-?minimis|below which|exempt|floor/i` **and** amount reads as a cutoff.
3. `incentive` — `/incentive|bounty|refund|deposit|rebate|social impact|paid to|returned to/i` (money flowing
   *to* consumers/technicians — the same direction guard as `fee_citations.py`).
4. `registration` — `/registration|renewal|membership|join|enrol/i`.
5. `admin_cost` — `/oversight|administrative cost|program cost|cost recovery/i` (aggregate, not per-producer).
6. `producer_fee` — `basis IN (per_ton, per_unit, percent_revenue, eco_modulated)` and none of the above.
7. else `unspecified`.

Ship with a unit test asserting the classifier on ~30 hand-labeled corpus rows (target ≥90% agreement). Kind
is **computed at read** in Phase 0 (cheap; keeps it iterable). If it stabilizes and we want to filter in SQL,
persist it in Phase 3 (§6).

## 5. Honesty / provenance rules (carry into UI + docs)
- Row is `grounded` iff it has a `source_excerpt` (≈all `present` rows are).
- `amount: null` is **not** missing data — it means the measure states the mechanism but leaves the number to
  rulemaking. Surface as "mechanism stated; rate set by PRO/agency", linking to Layer B where one exists.
- Fix the `/developers` page: it advertises `/compliance/fee-schedule` as "producer-fee estimates with
  citations grounded in enacted text" — that's actually Layer A. Point that copy at `/fee-amounts`, and
  describe `/fee-schedule` as the curated rate-table layer.

## 6. Phasing
- **P0 (ship):** `GET /compliance/fee-amounts` + `/summary` + `/eco-modulation`, read-time JSONB unnest, no
  new table, no LLM. Schemas + endpoint tests (sibling to `tests/test_api/test_compliance_fee_schedule.py`).
- **P1:** `fee_kind` classifier + `?fee_kind` filter + its unit test.
- **P2:** wire the dev-page + an Insights "fees across jurisdictions" chart off `/summary`; correct the
  dev-page copy and the two-layer framing.
- **P3 (only if needed):** a `fee_amount_row` materialized view or normalized table (bill_id, basis, amount,
  currency, material, fee_kind, source_excerpt) for SQL-side filtering + a QC pass flagging suspect rows
  (amount with wrong-direction descriptor, currency/region mismatch). Also decide `bill_fee_citation`'s fate
  (repoint or drop).

## 7. Monetization & gating (decided 2026-07-27)

The API is a **different SKU from the $400/mo app seat** — a different buyer (builders, consultancies, law
firms, packaging/sustainability software vendors, PROs) buying **coverage**, not answers. The value metric is
**breadth × freshness** ("one normalized, cited point of access to 40+ jurisdictions, kept current"), not call
count. Competitors charge $10–50k/yr for narrower coverage → the eventual annual API/data plan anchors well
above the app seat.

**The open ↔ paid line is drawn at breadth, not at the endpoint.** Keep a genuinely useful free teaser (SEO +
developer-funnel), gate the cross-jurisdiction body:

| Rung | Access | Posture |
|---|---|---|
| **Free / open** | `/summary` (full aggregates), + `/fee-amounts` & `/eco-modulation` **US-only, capped rows** | $0 — funnel |
| **API Pro** | API key / Pro token → **all 40+ jurisdictions**, uncapped, cited rows | flat annual, above app seat |
| **Data License / Bespoke** | bulk snapshot/export, embed rights, webhooks, SLA | negotiated (existing "request access" lead-gen) |

**Do NOT build metering/billing infra in P0.** Reuse the existing best-effort Pro gate (`get_optional_pro`,
the same teaser pattern as Upcoming Deadlines) for the US-teaser / world-full split, and keep manual "request
API access" lead-gen for commercial deals. Sign 2–3 design partners to learn WTP + preferred shape (live API
vs. quarterly snapshot — bet is resellers want the snapshot + embed rights) before automating.

**P0 gating implementation:**
- `GET /compliance/fee-amounts/summary` → **open, full** (aggregate counts across all regions; the breadth teaser).
- `GET /compliance/fee-amounts` and `GET /compliance/eco-modulation` → best-effort Pro check: **Pro/admin gets
  all regions, uncapped**; everyone else gets **US-only, capped at `FEE_TEASER_LIMIT`**, with a `teaser: true`
  flag + `total_available` count + an upgrade `note`. Never 401s public traffic.
- Response is a **wrapper** `{rows, count, total_available, teaser, note}` (not a bare list) so the lock is
  legible to callers — a small change from §3.1's bare-list sketch.

## 8. Resolved decisions
1. **Default region** — `all` (cross-jurisdiction is the value); diverges from bills.py's US-default. For a
   non-Pro caller the effective scope is forced to US regardless (the teaser line).
2. **Granularity** — one row per rate entry (filterable).
3. **`fee_kind`** — computed at read (`app/synthesis/fee_kind.py`); pulled into P0 because the response schema
   needs it. Persist only if SQL-side filtering is later required (P3).
4. **Gating** — US-teaser-free / world-gated, per §7 (was "open" in the earlier draft; changed after the
   monetization discussion).
```
