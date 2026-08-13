# Atlas Circular — Codebase Context

_Generated 2026-08-13 06:30 UTC by `scripts/generate_codebase_context.py` (level: standard). Regenerate rather than hand-editing — every section below the preamble is derived from the source tree._

## Current focus

- **Launch comms and measurement.** Email has just moved to Postmark (both streams, compliant
  footer, verifiable sender); GA4 is now queryable from the terminal, with a pre-post traffic
  baseline recorded so a launch spike has something to be measured against.
- **The exposure calculator.** Speccing and building producer attribution — answering "who owes
  this" before "how much", starting from the OR/CO fee schedules.
- **Corpus text integrity.** Reversible repair paths for wrong-text bills, split by which failure
  actually happened, and extraction running against the enacted version rather than the
  introduced draft.
- **Conversion surfaces.** Paywalls all reporting themselves the same way, referral in email,
  and the pricing page argued rather than listed.

_Source: [docs/FOCUS.md](docs/FOCUS.md), last edited (uncommitted)._

Where the commits have actually landed in the last 21 days — derived, so it corroborates or contradicts the block above:

`dashboard-next/src/components` (121) · `dashboard-next/src/app` (100) · `app/api` (48) · `dashboard-next/src/lib` (45) · `app/alerts` (42) · `tests/test_alerts` (18) · `app/ingestion` (17) · `dashboard-next/scripts/og-assets` (13)

## What this is

**Atlas Circular** (repo/dirs still say `SignalScout` / `ce-bill-tracker` — same product,
pre-rename) is a jurisdiction-aware research atlas for circular-economy law: EPR, packaging,
right-to-repair, recycled content, disposal bans, procurement enablers, and adjacent
transboundary-waste rules. It ingests legislation from ~40 regions (US states + federal, EU,
and national adapters for JP/FR/GB/IN/IT/NO/TR/KE and more), classifies each measure with
Claude along several axes (instrument type, material, friction, management model), extracts
structured compliance dimensions, and serves it as a browsable corpus plus an LLM research
surface ("Ask the Atlas") that answers questions with citations back to specific bills.

Stack: **FastAPI + SQLAlchemy 2.0 (typed `Mapped`) + Postgres + Alembic** on the backend,
**Next.js (App Router, static export) + Tailwind** in `dashboard-next/`, Anthropic API for
classification/extraction/synthesis, APScheduler for recurring ingest, Postmark for email
(transactional + broadcast streams; the `SENDGRID_*` settings are inert legacy names kept so an
old environment still boots), Stripe for billing, Firebase Auth for identity.

Hosting is **Google Cloud**, project `ce-bill-tracker`: Cloud Run for the API, Cloud Run Jobs
for the pipeline, Cloud SQL Postgres, Firebase Hosting for the dashboard.

**Deploys are manual and local.** There is no GitHub Actions workflow and no Cloud Build
GitHub trigger — nothing ships on push. `gcloud builds submit` uploads the **working tree**
(minus `.gcloudignore`), not a git commit.

- Prod: `gcloud builds submit --config=cloudbuild.yaml --project=ce-bill-tracker`
  (wrapped by `scripts/deploy-prod.ps1`, which guards clean tree / on `main` / synced with
  `origin/main`, so what's live equals a committed `main` commit).
- Dev: same with `--config=cloudbuild.dev.yaml` — no guard; dev is deliberately the
  working-tree lane (separate DB `signalscout_dev`, service `signalscout-api-dev`,
  Firebase site `ce-bill-tracker-dev`).

Consequence worth holding onto when advising: a remote/cloud agent sees only what's been
**pushed to git**, while a deploy sees whatever is **on disk**. Those two views of "the code"
can differ, and only the prod deploy guard forces them to agree.


## Capabilities

What the product can do, grouped by user-facing job. Each cluster's pages and endpoints are derived from the tree; only the grouping is hand-declared (`CLUSTERS` in the generator), so anything new shows up either in a cluster or in **Unclustered** at the end.

"Gated by" lists the auth dependencies the backend actually enforces — a capability name maps to the cheapest plan carrying it, per `PLAN_CAPS`. Endpoints with no gate are public.

### Corpus browse & filter

The atlas itself: the bill corpus, per-bill pages, jurisdiction and state profiles, and the embeddable/anonymous slices.

- Pages: `/`, `/bill/[id]/[slug]`, `/embed`, `/jurisdictions/[region]/[code]`, `/library`, `/states`, `/states/[abbr]`
- API: 16 endpoints (16 public) in `app/api/bills.py`, `app/api/scope.py`
- Gated by: nothing — fully public

### Ask the Atlas (research)

LLM research surface — cited answers over the corpus, persisted research sessions, shared `/r/` links and published `/p/` pages.

- Pages: `/ask`, `/p`, `/r`
- API: 17 endpoints (3 public) in `app/api/research.py`
- Gated by: admin, ask (student+)

### Compliance pathways

What a given obligation actually requires: deadlines, structured compliance dimensions, and how-to-comply links.

- Pages: `/compliance`
- API: 6 endpoints (6 public) in `app/api/compliance.py`
- Gated by: nothing — fully public

### Company exposure & bill evaluation

Producer attribution — which companies a measure reaches — plus the fit-score evaluator for a single bill.

- Pages: `/company`, `/evaluate`
- API: 11 endpoints (7 public) in `app/api/companies.py`, `app/api/evaluate.py`
- Gated by: admin

### Federal actions & litigation

US federal regulatory actions and tracked litigation, alongside the legislative corpus.

- Pages: `/federal`
- API: 3 endpoints (3 public) in `app/api/federal.py`
- Gated by: nothing — fully public

### Insights & analytics

Momentum, heatmaps, passage-rate baselines and real-world outcomes.

- Pages: `/insights`
- API: 4 endpoints (4 public) in `app/api/insights.py`
- Gated by: nothing — fully public

### Design guide & packaging studio

Design-for-EPR principles, the packaging reference catalog, material swatches and labeling.

- Pages: `/design-guide`, `/label`, `/studio`
- API: 1 endpoint (0 public) in `app/api/design.py`
- Gated by: design_guide (student+)

### Watchlist & alerts

Per-user tracking with new-bill, deadline and digest email triggers.

- Pages: `/watchlist`
- API: 2 endpoints (2 public) in `app/api/alerts.py`
- Gated by: nothing — fully public

### Accounts, billing & access

Identity, entitlements and plan resolution, Stripe checkout and webhooks, referrals, beta access requests.

- Pages: `/account`, `/beta`, `/pricing`
- API: 21 endpoints (16 public) in `app/api/access.py`, `app/api/auth_email.py`, `app/api/billing.py`, `app/api/referrals.py`, `app/api/user.py`, `app/api/webhooks.py`
- Gated by: Pro

### Admin & pipeline ops

Internal only: corpus review queues, the research log, and manual triggers for the ingest/classify pipeline.

- Pages: `/admin`, `/admin/research`
- API: 25 endpoints (1 public) in `app/api/admin.py`, `app/api/pipeline.py`
- Gated by: admin

### Static & marketing

Content pages with no backing API surface of their own.

- Pages: `/about`, `/developers`, `/faq`, `/methodology`, `/privacy`, `/terms`
- Gated by: nothing — fully public

### Unclustered

Not claimed by any cluster above — add them to `CLUSTERS` in `scripts/generate_codebase_context.py`.

- API: 1 endpoint (1 public) in `app/api/health.py`
- Gated by: nothing — fully public

### Plan matrix

From `PLAN_CAPS` in `app/api/auth.py` — plans in declaration order, cheapest first.

| Capability | Free | Student | Research | Pro | Enterprise | What it unlocks |
| --- | --- | --- | --- | --- | --- | --- |
| `explore` | ● | ● | ● | ● | ● | Bill Explorer + jurisdiction data |
| `ask` | · | ● | ● | ● | ● | Ask the Atlas (research Q&A) |
| `design_guide` | · | ● | ● | ● | ● | full Design Guide |
| `insights_impact` | · | · | ● | ● | ● | Real-World Impact table + Bills-over-time chart |
| `deadlines` | · | · | · | ● | ● | Upcoming Deadlines calendar |
| `alerts` | · | · | · | ● | ● | watchlist / new-bill + deadline alerts |
| `studio` | · | · | · | ● | ● | Packaging Studio |
| `federal` | · | · | · | ● | ● | Federal Actions (also US-region gated at the route) |

> **Enforced server-side: `ask`, `design_guide`.** The rest — `explore`, `insights_impact`, `deadlines`, `alerts`, `studio`, `federal` — appear in `PLAN_CAPS` but are not required by any route, so the paywall for them is client-side and the API is reachable without the plan.

### Behavior behind default-off flags

These `app/config.py` settings default to **False**, so the code exists but is inert unless the environment turns it on. Reading the code alone will overstate what's running.

`ENABLE_EURLEX_INGESTION`, `ENABLE_LEGISCAN_INGESTION`, `ENABLE_LLM_CLASSIFICATION`, `ENABLE_SONNET_EXTRACTION`, `ENABLE_INTERPRETATION`, `ENABLE_COURTLISTENER`, `ENABLE_DIGEST`, `ENABLE_WEEKLY_DIGEST`, `ENABLE_DEADLINE_ALERTS`, `ENABLE_NEW_BILL_ALERTS`, `ENABLE_TRIAL_REMINDERS`, `ENABLE_WATCHLIST_RECAP`, `ENABLE_LINK_AUDIT`, `ENABLE_BILL_TEXT_REFRESH`

## Repo state at generation time

- Remote: `https://github.com/SuperFunStudio/CE-Bill-Tracker.git`
- Branch: `main` — HEAD `2c9b211 2026-08-12 Say what the Atlas holds, and put each control next to the thing it acts on`
- Uncommitted files: **6** (.claude/settings.json, cloudbuild.yaml, docs/CODEBASE_CONTEXT.md, scripts/generate_codebase_context.py, docs/FOCUS.md, docs/codebase_context.snapshot.json)
- Unpushed commits on this branch: **0**
- Alembic head: **048** (48 migrations)
- Size: 33 tables · 107 API endpoints · 30 frontend routes · 19 scheduled jobs · 116 scripts

> Note: the working tree is **not** clean/synced, so this summary describes code that a remote agent cloning `origin` would not see.

## Recent commits

```
2c9b211 2026-08-12  Say what the Atlas holds, and put each control next to the thing it acts on
21fb85e 2026-08-12  Send every email through Postmark, from one identity with two voices
d2a01c3 2026-08-12  Tell an admin mute apart from a real unsubscribe
2010327 2026-08-12  Record the pre-post traffic baseline so the spike has something to be measured against
1247a3c 2026-08-12  Stop shipping the corpus raw and uncached on every homepage load
18b6acd 2026-08-12  Read journeys out of the GA4 export, with the bots taken out first
5a6428f 2026-08-11  Wire BUSINESS_ADDRESS into the API and migration-job deploys
86ba639 2026-08-11  Give every outbound email a compliant footer and a verifiable sender
e9bd58c 2026-08-11  Answer "who owes it" before "how much": producer attribution + OR/CO fee schedules
dc6c598 2026-08-11  Stop losing the first page_view, and let anonymous readers personalize
c845a66 2026-08-11  Spec the exposure calculator
5e4b693 2026-08-11  Query GA4 from the terminal instead of its UI
e2f6fdd 2026-08-11  Offer the referral in email, and make the visit measurable
75da995 2026-08-11  Make every paywall report itself the same way
6b3c148 2026-08-11  Extract from the version that IS the law, not the introduced draft
```

## Changed since last generation

_Baseline: snapshot taken 2026-08-13 06:30 UTC at `2c9b211`. Structural only — a rewritten function body with the same signature doesn't appear here._

**New endpoints**

- `GET /admin/access-requests` — `list_access_requests` in app/api/admin.py (gated: require_admin)

**Removed endpoints**

- `GET /ghost/route`

**Moved gates**

- `DELETE /admin/outcomes/{outcome_id}` — was ungated → now require_admin

**Removed tables**

- `ghost_table`

**Changed columns**

- `access_requests`: +`created_at`

**New pages**

- `/ask`

**Changed defaults**

- `ENABLE_DIGEST` — was `True` → now `False`

**Migrations**

- head `047` → `048` (+1 revision)

## Directory map

```
alembic/  (1 py)  — Database migrations (single linear history)
  versions/  (48 py)
app/  (11 py)  — FastAPI backend (all Python application code)
  alerts/  (19 py)  — Email alerting, digests, subscriber notification triggers
  api/  (23 py)  — HTTP routers — one module per surface
  classification/  (10 py)  — Claude-backed classifiers + keyword gates that decide scope and axes
  company_intel/  (6 py)  — Company entity resolution + exposure briefs
  evaluation/  (6 py)  — Bill strength / fit-score evaluator
  geo/  (2 py)  — Jurisdiction tree + region/state normalization
  ingestion/  (17 py)  — Source adapters: LegiScan, OpenStates, EUR-Lex, Federal Register, per-country foreign clients
  links/  (2 py)  — Source-link health classification and repair
  research/  (3 py)  — Ask-the-Atlas retrieval, facet routing, session/turn persistence
  scheduler/  (2 py)  — APScheduler job definitions for recurring ingest/refresh
  scoring/  (8 py)  — Company impact scoring (gated, pre-launch)
  static/
  synthesis/  (7 py)  — LLM synthesis (design principles, briefings) over classified bills
  utils/  (5 py)  — Shared helpers
dashboard/  (2 py)  — Legacy dashboard — superseded by dashboard-next
  pages/  (4 py)
dashboard-next/  (3 ts)  — Next.js App Router frontend (static export -> Firebase Hosting)
  public/
  scripts/  (1 py)
  src/
data/  — Seed data and exports (data/seed IS shipped into the image)
  analysis/
  exports/
  seed/
docs/  — Design specs, roadmaps, plans, assessments
  research/
hackathon/  — Hackathon prototypes
  compliance-cliff/
  compliance-copilot-mcp/
  comply-by-friday/
  epr-forward-curve/
  epr-nutrition-label/
  exposure-terminal/
  spec-sheet-guard/
  swap-studio/
  under-appeal/
  whip-count/
scripts/  (116 py)  — One-off + operational scripts (backfills, audits, ingest runs, deploys)
tests/  (3 py)  — pytest suite
  eval/  (2 py)
  test_alerts/  (12 py)
  test_api/  (13 py)
  test_classification/  (2 py)
  test_company_intel/  (6 py)
  test_ingestion/  (6 py)
  test_scoring/  (2 py)
  test_synthesis/  (1 py)
```

## Backend API surface

FastAPI app: `app/main.py`. Routers live in `app/api/` and are registered there.

### app/api/access.py — `/access-requests`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| POST | `/access-requests` | `create_access_request` |  |

### app/api/admin.py — `/admin`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| GET | `/admin/access-requests` | `list_access_requests` | The willingness-to-pay leads (pricing / company-gate clicks), newest first. |
| POST | `/admin/access-requests/{request_id}/review` | `review_access_request` | Approve / deny an access-request lead. Approving a `research` request is what lets that email |
| GET | `/admin/account` | `admin_account` | Everything we know about one account, resolved by email: entitlement, Firebase identity |
| POST | `/admin/account/delete` | `admin_delete_account` | Permanently delete an account by email — the admin-driven twin of the user self-delete: |
| POST | `/admin/account/disable` | `admin_set_account_disabled` | Suspend or restore a user's ability to sign in (Firebase `disabled` flag) — a reversible freeze |
| GET | `/admin/entitlements` | `list_entitlements` | All accounts with a billing identity (paid + comp + free-with-history), newest first. |
| POST | `/admin/grant-pro` | `grant_pro` | Grant complimentary Pro to an email. Upserts the Entitlement (creating a row for an email that |
| GET | `/admin/me` | `admin_me` | Cheap admin probe for the frontend: 200 {is_admin: bool} for any signed-in user. |
| GET | `/admin/outcomes` | `list_outcomes` | All bill_outcome rows for review — UNREVIEWED first (the work queue), then lowest-confidence |
| DELETE | `/admin/outcomes/{outcome_id}` | `delete_outcome` | Reject a candidate outright (e.g. hallucinated or unverifiable figure). Hard delete — these are |
| PATCH | `/admin/outcomes/{outcome_id}` | `update_outcome` | Correct a candidate's fields and/or approve it (reviewed=true → live on the public page). |
| POST | `/admin/revoke-pro` | `revoke_pro` | Revoke a complimentary grant (back to free). Only comp grants are revocable here — a paid |
| GET | `/admin/stats` | `admin_stats` | Top-line counts + data-freshness markers for the console dashboard. |
| GET | `/admin/subscribers` | `list_subscribers` | The public free-update sign-ups (filter-scope subscriptions), newest first. Optional email/org |
| POST | `/admin/subscribers/{subscription_id}/active` | `set_subscriber_active` | Activate or deactivate a sign-up (mute/unmute their alerts without deleting the record). |

### app/api/alerts.py — `/subscriptions`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| POST | `/subscriptions` | `create_subscription` |  |
| DELETE | `/subscriptions/{subscription_id}` | `delete_subscription` |  |

### app/api/auth_email.py — `/auth`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| POST | `/auth/send-password-reset` | `send_password_reset` | Send the branded password-reset email. Unauthenticated by necessity — the whole point is that |
| POST | `/auth/send-verification` | `send_verification` | Send the branded 'confirm your address' email to the signed-in account. |

### app/api/billing.py — `/billing`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| POST | `/billing/checkout` | `create_checkout` | Open a Checkout Session for the requested membership and return its hosted URL (or, for a $0 |
| GET | `/billing/founding-seats` | `founding_seats` | How many founding seats are gone — the pricing page's seat counter, made true. |
| GET | `/billing/me` | `billing_me` | The dashboard's entitlement check — is the signed-in user on Pro. |
| POST | `/billing/portal` | `billing_portal` | Stripe-hosted customer portal so subscribers can manage/cancel their plan. |
| POST | `/billing/signup-trial` | `signup_trial` | Grant this account its one-time 7-day signup trial (full Pro, no card) and send the account |
| POST | `/billing/webhook` | `stripe_webhook` | Stripe → us. Verifies the signature (when a signing secret is set) and upserts entitlement. |

### app/api/bills.py — `/bills`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| GET | `/bills` | `list_bills` |  |
| GET | `/bills/collection-target-basis` | `get_collection_target_basis` | Distribution of how collection/recovery targets are *measured* — by weight, units, value |
| GET | `/bills/deadlines/summary` | `deadlines_summary` | Ungated aggregate counts (total/within-30/within-90/nearest + which states), optionally scoped |
| GET | `/bills/deadlines/upcoming` | `list_upcoming_deadlines` | Pro seats get the full merged deadline list (incl. up to 5 years of past dates so the page's |
| GET | `/bills/instrument-material-matrix` | `get_instrument_material_matrix` | Counts of EPR-relevant bills per (instrument_type × material_category × region) — the Insights |
| GET | `/bills/laws-in-force` | `get_laws_in_force` | Per-year, per-region counts of enacted CE laws that came INTO FORCE that year. |
| GET | `/bills/map-summary` | `get_map_summary` |  |
| GET | `/bills/outcomes` | `list_bill_outcomes` | Documented real-world outcomes of enacted laws — the Insights "Real-World Impact" feed. |
| GET | `/bills/search` | `search_bills` | Full-text search over the persisted bill text (`bill_texts`), returning each matching bill with |
| GET | `/bills/stance-momentum` | `get_stance_momentum` | Per-year, per-region counts of EPR-relevant bills by policy_stance — the Insights "momentum" view. |
| GET | `/bills/text-coverage` | `bill_text_coverage` | Counts of ce_relevant bills with vs. without indexed full text, so the deep-search UI can say |
| GET | `/bills/timeline` | `get_bill_timeline` | Per-year, per-status, per-region counts of EPR-relevant bills, bucketed by year of status_date. |
| GET | `/bills/{bill_id}` | `get_bill` |  |
| GET | `/bills/{bill_id}/litigation-cases` | `get_bill_litigation_cases` |  |
| GET | `/bills/{bill_id}/text` | `get_bill_text` | The bill's persisted full statute text (the `bill_texts` side table), read by id. Free — a |

### app/api/companies.py — `/bills`, `/companies`, `/entity-match-queue`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| GET | `/bills/{bill_id}/company-exposure` | `get_bill_company_exposure` | Companies most exposed to a specific bill, ranked by composite score. |
| GET | `/companies` | `list_companies` | List companies with optional filters. |
| GET | `/companies/exposure-ranking` | `get_exposure_ranking` | Top companies ranked by composite impact score for a given bill. |
| GET | `/companies/{company_id}` | `get_company` | Full company detail including materials and state presences. |
| GET | `/companies/{company_id}/exposure-brief` | `get_or_generate_exposure_brief` | Return a cached Exposure Brief for a (company, bill) pair, generating one if needed. |
| GET | `/companies/{company_id}/impact-scores` | `get_company_impact_scores` | All impact scores for a company, ordered by composite score descending. |
| GET | `/companies/{company_id}/obligations` | `get_company_obligations` | 'Are you affected, and what's your next deadline' for one company. |
| GET | `/entity-match-queue` | `list_match_queue` | List entity match queue entries pending manual review. |
| PATCH | `/entity-match-queue/{queue_id}/resolve` | `resolve_queue_entry` | Mark a queue entry as resolved, optionally linking to a company. |

### app/api/compliance.py — `/compliance`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| GET | `/compliance/eco-modulation` | `eco_modulation` | Eco-modulation criteria (design attributes that raise/lower fees) per measure, cited. One row per |
| GET | `/compliance/fee-amounts` | `fee_amounts` | Bill-sourced fee amounts, one row per stated rate, cited. US-teaser for non-Pro; full for Pro. |
| GET | `/compliance/fee-amounts/summary` | `fee_amounts_summary` | Open, full aggregate over the bill-sourced fee entries — the breadth teaser + chartable stat. |
| GET | `/compliance/fee-schedule` | `fee_schedule` | CA SB 54 (2027 draft) per-material-format producer fee schedule. Public reference data. |
| GET | `/compliance/pathways` | `list_pathways` |  |
| GET | `/compliance/producer-attribution` | `producer_attribution` | Which party owes the packaging obligation, per jurisdiction and regime, with citations. |

### app/api/design.py — `/design-guide`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| GET | `/design-guide/full` | `full_guide` |  |

### app/api/evaluate.py — `/evaluate`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| POST | `/evaluate/bill` | `evaluate_bill` |  |
| GET | `/evaluate/material-map` | `get_material_map` | The value×dispersion×channel map of known materials + their regime — reference data for the |

### app/api/federal.py — `/federal-actions`, `/litigation-cases`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| GET | `/federal-actions` | `list_federal_actions` | List federal actions from the Federal Register and other sources. |
| GET | `/litigation-cases` | `list_litigation_cases` | List litigation cases tracked from CourtListener. |
| GET | `/litigation-cases/{case_id}` | `get_litigation_case` | Get a litigation case with all events (timeline). |

### app/api/health.py — `/`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| GET | `/health` | `health` |  |

### app/api/insights.py — `/insights`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| GET | `/insights/champions` | `get_champions` | CE champion roster (slim — no per-bill list). Active (in-office) only by default, sorted by |
| GET | `/insights/champions/{person_id:path}/bills` | `get_champion_bills` | The bills behind a champion — each with its source_url (the link-to-source rule). |
| GET | `/insights/state-cycles` | `get_state_cycles` | One state's advancing-CE passage rate vs. the all-bills baseline, per legislative biennium — |
| GET | `/insights/state-gap` | `get_state_gap` | Per-state advancing-CE passage rate vs. the all-bills baseline. Sorted by gap (most |

### app/api/pipeline.py — `/pipeline`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| POST | `/pipeline/purge-legiscan` | `purge_legiscan` | Delete all LegiScan-sourced bills and their dependent rows. |
| POST | `/pipeline/reset-classification` | `reset_classification` | Reset confidence_score to NULL on Open States bills that failed keyword filtering. |
| POST | `/pipeline/run` | `trigger_pipeline` | Trigger the ingestion + classification pipeline as a Cloud Run Job. |
| POST | `/pipeline/run-classification` | `trigger_classification` | Classify all unclassified bills already in the database via Cloud Run Job. |
| POST | `/pipeline/run-federal` | `trigger_federal` | Manually trigger the Federal Register ingestion cycle. |
| POST | `/pipeline/run-openstates` | `trigger_openstates` | Trigger a full OpenStates historical sync (no updated_since filter). |
| POST | `/pipeline/run-scoring` | `trigger_scoring` | Manually trigger the company impact scoring cycle. |
| POST | `/pipeline/seed` | `trigger_seed` | DISABLED. The hand-curated seed was replaced by the OpenStates v3 sync; its rows were |
| GET | `/pipeline/seed-coverage` | `seed_coverage` | Read-only: check which previously-known enacted EPR laws are present after the |
| GET | `/pipeline/status` | `pipeline_status` | Return classification coverage stats for all bills in the database. |

### app/api/referrals.py — `/referrals`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| POST | `/referrals/attribute` | `attribute` | Credit a referral for the signed-in (newly-created) account and grant the referrer 30 days of |
| GET | `/referrals/me` | `my_referral` | The signed-in account's referral code (generated on first call). The frontend builds the share |

### app/api/research.py — `/research`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| GET | `/research/admin/turns` | `admin_research_turns` | The full research history — newest first — so an admin can audit questions and mine good answers |
| POST | `/research/ask` | `ask_the_atlas` |  |
| GET | `/research/bills` | `research_bills` | SQL-only pagination over the FULL relevant-bill set for a question. The Ask page's Prev/Next hit |
| GET | `/research/drafts` | `list_content_drafts` |  |
| POST | `/research/drafts` | `create_content_draft` | Send one or more turns of a research thread to the staging area: combine the selected turns (in |
| DELETE | `/research/drafts/{draft_id}` | `delete_content_draft` |  |
| GET | `/research/drafts/{draft_id}` | `get_content_draft` |  |
| PATCH | `/research/drafts/{draft_id}` | `update_content_draft` |  |
| POST | `/research/drafts/{draft_id}/publish` | `publish_content_draft` | Take a staged draft live at an instant, self-hosted /p/?token= permalink — independent of any |
| POST | `/research/drafts/{draft_id}/unpublish` | `unpublish_content_draft` | Take a published article back down: status → 'staged' so the public /p/ read 404s. The token is |
| GET | `/research/my-sessions` | `my_research_sessions` | The signed-in member's own Ask-the-Atlas history — the list backing My Library. Returns each |
| GET | `/research/published/{token}` | `published_article` | PUBLIC read of a published article — no auth. Resolves only a draft that is currently 'published' |
| POST | `/research/pulse` | `research_pulse` | Timeliness ranker behind the staging-page 'Pulse' button — ranks candidate research turns by what's |
| GET | `/research/session/{session_id}` | `research_session` | Load an owned research thread with its turns in order — so the Ask page can restore/continue a |
| POST | `/research/session/{session_id}/share` | `share_session` | Mint (or reuse) an unguessable share link for a research thread and flip it to link-visible. The |
| POST | `/research/session/{session_id}/unshare` | `unshare_session` | Revoke sharing: back to private AND drop the token, so a link that already leaked stops working |
| GET | `/research/shared/{token}` | `shared_session` | PUBLIC read of a shared research thread — no auth. Resolves ONLY when the session is explicitly |

### app/api/scope.py — `/anon-scope`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| POST | `/anon-scope` | `upsert_anon_scope` | Record (or update) an anonymous visitor's scope. Returns 204 — the client is the source of |

### app/api/user.py — `/me`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| DELETE | `/me/account` | `delete_account` | Permanently delete the signed-in account: cancel any live Stripe subscription, purge the |
| GET | `/me/settings` | `get_settings` |  |
| PATCH | `/me/settings` | `patch_settings` | Shallow-merge the given keys into the user's prefs, leaving other keys untouched. |
| PUT | `/me/settings` | `put_settings` |  |
| GET | `/me/watchlist` | `get_watchlist` |  |
| POST | `/me/watchlist` | `add_watch` |  |
| GET | `/me/watchlist/prefs` | `get_watchlist_prefs` | The user's watch-list notification prefs. Returns defaults if they haven't starred a bill yet |
| PUT | `/me/watchlist/prefs` | `put_watchlist_prefs` | Update which events the user is emailed about for their watched bills. Creates the |
| DELETE | `/me/watchlist/{bill_id}` | `remove_watch` |  |

### app/api/webhooks.py — `/webhooks`

| Method | Path | Handler | Notes |
| --- | --- | --- | --- |
| POST | `/webhooks/courtlistener` | `courtlistener_webhook` | Receive push notifications from CourtListener search and docket alerts. |

## Data model

SQLAlchemy 2.0 typed models in `app/models.py` (33 tables). Migrations are a single linear Alembic history in `alembic/versions/`.

### `bills` — `Bill` ([app/models.py:25](app/models.py#L25))

Columns: `id`, `legiscan_bill_id`, `openstates_id`, `celex_id`, `foreign_id`, `region`, `state`, `jurisdiction_id`, `bill_number`, `title`, `title_native`, `title_native_lang`, `description`, `status`, `status_date`, `last_action_date`, `source_url`, `source_url_status`, `source_url_final`, `source_url_checked_at`, `change_hash`, `last_fetched_at`, `ce_relevant`, `confidence_score`, `material_categories`, `instrument_type`, `instrument_types`, `urgency`, `ai_summary`, `policy_stance`, `stance_source`, `reviewed`, `needs_review`, `new_bill_alert_sent`, `compliance_details`, `effective_date`, `adjacency`, `litigation_risk`, `created_at`, `updated_at`

Relationships: `changes`, `deadlines`

### `jurisdictions` — `Jurisdiction` ([app/models.py:184](app/models.py#L184))

Atlas Circular's jurisdiction tree (migration 036) — world -> bloc/country -> state ->

Columns: `id`, `parent_id`, `level`, `code`, `name`, `aliases`, `path`, `bill_count`

### `bill_changes` — `BillChange` ([app/models.py:208](app/models.py#L208))

Columns: `id`, `bill_id`, `change_type`, `old_value`, `new_value`, `detected_at`, `alert_sent`

Relationships: `bill`

### `classification_changes` — `ClassificationChange` ([app/models.py:226](app/models.py#L226))

Audit log of classification deltas — one row per bill whose relevance/instrument changed on a

Columns: `id`, `bill_id`, `run_id`, `old_value`, `new_value`, `created_at`

### `bill_texts` — `BillText` ([app/models.py:258](app/models.py#L258))

Persisted full bill text + an FTS index — Layer B of the full-text search plan

Columns: `bill_id`, `text`, `text_tsv`, `char_len`, `source`, `indexed_change_hash`, `fetched_at`

### `bill_design_signal` — `BillDesignSignal` ([app/models.py:294](app/models.py#L294))

One cited design implication derived from a bill's compliance_details.

Columns: `id`, `bill_id`, `lever`, `obligation_type`, `design_action`, `source_excerpt`, `threshold_value`, `threshold_unit`, `confidence`, `extractor_model`, `reviewed`, `created_at`

Relationships: `bill`

### `bill_product_coverage` — `BillProductCoverage` ([app/models.py:332](app/models.py#L332))

One (product, obligation) the bill scopes — the atom behind the product-coverage grid.

Columns: `id`, `bill_id`, `product_slug`, `category`, `relationship_type`, `status`, `defined_by_reference`, `source_excerpt`, `threshold_value`, `threshold_unit`, `confidence`, `extractor_model`, `reviewed`, `created_at`

Relationships: `bill`

### `bill_fee_citation` — `BillFeeCitation` ([app/models.py:382](app/models.py#L382))

One cited fee or coverage-threshold fact extracted from a bill — the chain of custody

Columns: `id`, `bill_id`, `fact_type`, `basis`, `extracted_value`, `value_unit`, `source_excerpt`, `source_url`, `notes`, `confidence`, `extractor_model`, `reviewed`, `created_at`

Relationships: `bill`

### `alert_subscriptions` — `AlertSubscription` ([app/models.py:435](app/models.py#L435))

A subscription to bill movement, in one of two scopes (the `scope` column):

Columns: `id`, `firebase_uid`, `scope`, `email`, `organization`, `slack_webhook`, `states`, `region_scope`, `material_categories`, `instrument_types`, `min_confidence`, `alert_on`, `active`, `created_at`, `onboarding_email_sent_at`, `watchlist_recap_sent_at`, `deactivated_at`, `deactivation_source`

### `access_requests` — `AccessRequest` ([app/models.py:523](app/models.py#L523))

A captured "request access / pricing" click — the willingness-to-pay field experiment, and

Columns: `id`, `email`, `name`, `organization`, `plan_interest`, `message`, `source`, `status`, `reviewed_by`, `reviewed_at`, `created_at`

### `federal_actions` — `FederalAction` ([app/models.py:557](app/models.py#L557))

Columns: `id`, `federal_register_document_number`, `agency`, `title`, `action_type`, `material_categories`, `published_date`, `comment_deadline`, `effective_date`, `document_url`, `ce_relevant`, `preemption_risk`, `friction_type`, `instrument_type`, `ai_summary`, `raw_data`, `created_at`

### `compliance_deadlines` — `ComplianceDeadline` ([app/models.py:586](app/models.py#L586))

Columns: `id`, `bill_id`, `federal_action_id`, `region`, `state`, `deadline_type`, `deadline_date`, `description`, `who_affected`, `source_url`, `reminder_sent`

Relationships: `bill`

### `company` — `Company` ([app/models.py:620](app/models.py#L620))

Columns: `id`, `name`, `duns_number`, `cik`, `epa_registry_id`, `region`, `hq_state`, `naics_codes`, `operating_states`, `total_annual_volume_tonnes`, `volume_source`, `volume_confidence`, `created_at`, `updated_at`

Relationships: `aliases`, `materials`, `state_presences`, `impact_scores`

### `company_alias` — `CompanyAlias` ([app/models.py:660](app/models.py#L660))

Columns: `id`, `company_id`, `alias_name`, `source`, `match_confidence`, `verified`, `verified_by`, `verified_at`

Relationships: `company`

### `company_material` — `CompanyMaterial` ([app/models.py:690](app/models.py#L690))

Columns: `id`, `company_id`, `material_category`, `annual_volume_tonnes`, `volume_confidence`, `source`

Relationships: `company`

### `company_state_presence` — `CompanyStatePresence` ([app/models.py:709](app/models.py#L709))

Columns: `id`, `company_id`, `region`, `state`, `presence_type`, `is_primary`

Relationships: `company`

### `impact_score` — `ImpactScore` ([app/models.py:732](app/models.py#L732))

Columns: `id`, `company_id`, `bill_id`, `composite_score`, `material_score`, `geographic_score`, `severity_score`, `estimated_annual_cost`, `cost_confidence`, `volume_confidence`, `score_breakdown`, `calculated_at`

Relationships: `company`, `bill`

### `entity_match_queue` — `EntityMatchQueue` ([app/models.py:763](app/models.py#L763))

Columns: `id`, `candidate_name`, `source`, `suggested_company_id`, `confidence`, `resolved`, `resolved_at`

### `exposure_brief` — `ExposureBrief` ([app/models.py:781](app/models.py#L781))

Columns: `id`, `company_id`, `bill_id`, `brief_json`, `generated_at`, `ttl_expires_at`

Relationships: `company`, `bill`

### `litigation_cases` — `LitigationCase` ([app/models.py:811](app/models.py#L811))

Columns: `id`, `courtlistener_id`, `case_name`, `docket_number`, `court_id`, `court_name`, `date_filed`, `date_terminated`, `assigned_judge`, `case_status`, `challenge_type`, `plaintiff_type`, `key_plaintiffs`, `related_law_id`, `region`, `related_state`, `related_statute`, `preemption_risk`, `cl_url`, `last_activity_date`, `ce_relevant`, `relevance_reason`, `relevance_source`, `relevance_checked_at`, `created_at`, `updated_at`

Relationships: `related_law`, `events`

### `litigation_events` — `LitigationEvent` ([app/models.py:866](app/models.py#L866))

Columns: `id`, `case_id`, `courtlistener_entry_id`, `event_type`, `date_filed`, `description`, `summary`, `significance`, `document_url`, `created_at`

Relationships: `case`

### `cl_alert_subscriptions` — `CLAlertSubscription` ([app/models.py:888](app/models.py#L888))

Columns: `id`, `alert_type`, `cl_alert_id`, `query_string`, `docket_id`, `active`, `created_at`

### `entitlements` — `Entitlement` ([app/models.py:902](app/models.py#L902))

A paid seat. One row per account, keyed by email — the stable identity that bridges Firebase

Columns: `id`, `email`, `firebase_uid`, `plan`, `status`, `stripe_customer_id`, `stripe_subscription_id`, `current_period_end`, `comp`, `comp_note`, `comp_granted_by`, `comp_granted_at`, `founding`, `referral_code`, `signup_trial_used`, `trial_reminder_sent_for`, `preview_until`, `created_at`, `updated_at`

### `referrals` — `Referral` ([app/models.py:976](app/models.py#L976))

One completed share-to-unlock referral: a NEW account (referred) signed up via a referrer's

Columns: `id`, `referrer_uid`, `referred_uid`, `referred_email`, `created_at`

### `user_settings` — `UserSettings` ([app/models.py:998](app/models.py#L998))

Per-account UI preferences, keyed by the immutable Firebase uid. Today this holds the saved

Columns: `id`, `firebase_uid`, `email`, `prefs`, `created_at`, `updated_at`

### `anon_scope` — `AnonScope` ([app/models.py:1021](app/models.py#L1021))

The scope an ANONYMOUS visitor chose — the signed-out counterpart to

Columns: `id`, `client_id`, `states`, `material_categories`, `configured`, `scoped`, `created_at`, `updated_at`

### `user_watchlist` — `WatchlistItem` ([app/models.py:1061](app/models.py#L1061))

A bill an account follows — the Pro 'personal watch list'. Keyed by Firebase uid + bill, with

Columns: `id`, `firebase_uid`, `bill_id`, `created_at`

### `compliance_entity` — `ComplianceEntity` ([app/models.py:1090](app/models.py#L1090))

A real-world body a producer interacts with to comply: a stewardship organization

Columns: `id`, `slug`, `name`, `entity_type`, `region`, `url`, `registration_url`, `jurisdiction_scope`, `home_state`, `materials`, `description`, `created_at`

### `compliance_pathway` — `CompliancePathway` ([app/models.py:1127](app/models.py#L1127))

The "how do I comply with THIS law" record — one primary next-action per enacted law.

Columns: `id`, `bill_id`, `entity_id`, `region`, `management_model`, `action_type`, `action_summary`, `registration_url`, `next_deadline_date`, `has_fee`, `confidence`, `basis`, `reviewed`, `created_at`

Relationships: `bill`, `entity`

### `bill_outcome` — `BillOutcome` ([app/models.py:1185](app/models.py#L1185))

One documented real-world outcome attributable to (or enabled by) an enacted law.

Columns: `id`, `slug`, `bill_id`, `region`, `state`, `bill_number`, `law_title`, `instrument_type`, `material_categories`, `direction`, `metric_label`, `metric_value`, `metric_unit`, `metric_display`, `summary`, `attribution`, `as_of_date`, `source_name`, `source_url`, `confidence`, `reviewed`, `remediation_note`, `remediated_by_bill_id`, `remediation_bill_number`, `remediation_checked_at`, `created_at`

Relationships: `bill`

### `research_sessions` — `ResearchSession` ([app/models.py:1255](app/models.py#L1255))

A persisted 'Ask the Bills' research thread — the primitive that turns ephemeral asks into a

Columns: `id`, `owner_uid`, `title`, `visibility`, `share_token`, `created_at`, `updated_at`

Relationships: `turns`

### `research_turns` — `ResearchTurn` ([app/models.py:1282](app/models.py#L1282))

One question+answer within a ResearchSession. `bill_ids` snapshots the ranked relevant set at

Columns: `id`, `session_id`, `seq`, `question`, `rewritten_query`, `facets`, `strategy`, `answer`, `bill_ids`, `bill_total`, `created_at`

Relationships: `session`

### `content_drafts` — `ContentDraft` ([app/models.py:1309](app/models.py#L1309))

An editorial draft distilled from a research turn — the staging area behind the Substack content

Columns: `id`, `source_session_id`, `source_seq`, `title`, `dek`, `body_markdown`, `status`, `share_token`, `slug`, `published_at`, `created_by`, `created_at`, `updated_at`

## Migration history

_Most recent 15 of 48; run with `--level full` for all._

- `034` — Multi-value instrument_types (a law is often several instruments at once)
- `035` — Classification audit log + needs_review flag
- `036` — Atlas Circular jurisdiction tree + bills.jurisdiction_id
- `037` — Persisted research sessions + turns (Atlas Circular analysis layer)
- `038` — Content staging area — editorial drafts distilled from research turns (the Substack pipeline)
- `039` — Publishable content drafts — self-hosted article permalink (off-Substack publishing)
- `040` — Atlas Circular membership: temporary Pro preview window on entitlements
- `041` — Widen bills.state for namespaced sub-national codes
- `042` — Approval status on access_requests (gate Researcher checkout on human review)
- `043` — Promote extracted effective_date to a real indexable column on bills
- `044` — Add original-language title columns to bills
- `045` — Add bills.adjacency scope-provenance tag (transboundary / toxics …)
- `046` — Add the relevance verdict to litigation_cases (ce_relevant + provenance)
- `047` — Persist the scope anonymous visitors choose (states + materials), keyed by a client-generated id
- `048` — Record WHY a subscription went inactive, not just that it did

## Scheduled jobs

Defined in `app/scheduler/jobs.py` (APScheduler, started by the API process). Some are conditional on settings flags — check the source for the gates.

| Job | Trigger | Schedule | Function |
| --- | --- | --- | --- |
| daily_ingestion | cron | hour=2, minute=0 | `run_ingestion_cycle` |
| federal_register_poll | interval | hours=settings.federal_register_poll_interval_hours | `run_federal_cycle` |
| alert_dispatch | cron | hour='8-18', minute='*/30' | `run_alert_dispatch` |
| daily_scoring | cron | hour=3, minute=0 | `run_scoring_cycle` |
| weekly_company_refresh | cron | day_of_week='sun', hour=4, minute=0 | `run_company_refresh` |
| daily_interpretation | cron | hour=4, minute=0 | `run_interpretation_cycle` |
| cl_new_cases | cron | day_of_week='mon', hour=6, minute=0 | `poll_courtlistener_new_cases` |
| cl_refresh_cases | cron | hour=7, minute=30 | `refresh_active_cases` |
| cl_bill_match_reconcile | cron | hour=8, minute=0 | `reconcile_bill_matches` |
| monthly_digest | cron | day=1, hour=13, minute=0 | `run_digest_cycle` |
| weekly_digest | cron | day_of_week='mon', hour=13, minute=0 | `run_weekly_digest_cycle` |
| deadline_alerts | cron | hour=12, minute=0 | `run_deadline_alert_cycle` |
| new_bill_alerts | cron | hour=11, minute=30 | `run_new_bill_alert_cycle` |
| trial_reminders | cron | hour=13, minute=30 | `run_trial_reminder_cycle` |
| watchlist_onboarding | interval | minutes=20 | `run_watchlist_onboarding_cycle` |
| watchlist_recap | interval | minutes=20 | `run_watchlist_recap_cycle` |
| source_link_audit | cron | day_of_week='sat', hour=5, minute=0 | `run_source_link_audit_cycle` |
| bill_text_refresh | cron | hour=6, minute=30 | `run_bill_text_refresh_cycle` |
| eurlex_refresh | cron | day_of_week='tue', hour=5, minute=30 | `run_eurlex_cycle` |

## Frontend routes

Next.js App Router in `dashboard-next/src/app`, built as a **static export** and deployed to Firebase Hosting. Shared UI in `src/components`, hooks in `src/hooks`, chart primitives + API client in `src/lib`.

- `/about` — [dashboard-next/src/app/about/page.tsx](dashboard-next/src/app/about/page.tsx)
- `/account` — [dashboard-next/src/app/account/page.tsx](dashboard-next/src/app/account/page.tsx)
- `/admin` — [dashboard-next/src/app/admin/page.tsx](dashboard-next/src/app/admin/page.tsx)
- `/admin/research` — [dashboard-next/src/app/admin/research/page.tsx](dashboard-next/src/app/admin/research/page.tsx)
- `/ask` — [dashboard-next/src/app/ask/page.tsx](dashboard-next/src/app/ask/page.tsx)
- `/beta` — [dashboard-next/src/app/beta/page.tsx](dashboard-next/src/app/beta/page.tsx)
- `/bill/[id]/[slug]` — [dashboard-next/src/app/bill/[id]/[slug]/page.tsx](dashboard-next/src/app/bill/[id]/[slug]/page.tsx)
- `/company` — [dashboard-next/src/app/company/page.tsx](dashboard-next/src/app/company/page.tsx)
- `/compliance` — [dashboard-next/src/app/compliance/page.tsx](dashboard-next/src/app/compliance/page.tsx)
- `/design-guide` — [dashboard-next/src/app/design-guide/page.tsx](dashboard-next/src/app/design-guide/page.tsx)
- `/developers` — [dashboard-next/src/app/developers/page.tsx](dashboard-next/src/app/developers/page.tsx)
- `/embed` — [dashboard-next/src/app/embed/page.tsx](dashboard-next/src/app/embed/page.tsx)
- `/evaluate` — [dashboard-next/src/app/evaluate/page.tsx](dashboard-next/src/app/evaluate/page.tsx)
- `/faq` — [dashboard-next/src/app/faq/page.tsx](dashboard-next/src/app/faq/page.tsx)
- `/federal` — [dashboard-next/src/app/federal/page.tsx](dashboard-next/src/app/federal/page.tsx)
- `/insights` — [dashboard-next/src/app/insights/page.tsx](dashboard-next/src/app/insights/page.tsx)
- `/jurisdictions/[region]/[code]` — [dashboard-next/src/app/jurisdictions/[region]/[code]/page.tsx](dashboard-next/src/app/jurisdictions/[region]/[code]/page.tsx)
- `/label` — [dashboard-next/src/app/label/page.tsx](dashboard-next/src/app/label/page.tsx)
- `/library` — [dashboard-next/src/app/library/page.tsx](dashboard-next/src/app/library/page.tsx)
- `/methodology` — [dashboard-next/src/app/methodology/page.tsx](dashboard-next/src/app/methodology/page.tsx)
- `/p` — [dashboard-next/src/app/p/page.tsx](dashboard-next/src/app/p/page.tsx)
- `/` — [dashboard-next/src/app/page.tsx](dashboard-next/src/app/page.tsx)
- `/pricing` — [dashboard-next/src/app/pricing/page.tsx](dashboard-next/src/app/pricing/page.tsx)
- `/privacy` — [dashboard-next/src/app/privacy/page.tsx](dashboard-next/src/app/privacy/page.tsx)
- `/r` — [dashboard-next/src/app/r/page.tsx](dashboard-next/src/app/r/page.tsx)
- `/states/[abbr]` — [dashboard-next/src/app/states/[abbr]/page.tsx](dashboard-next/src/app/states/[abbr]/page.tsx)
- `/states` — [dashboard-next/src/app/states/page.tsx](dashboard-next/src/app/states/page.tsx)
- `/studio` — [dashboard-next/src/app/studio/page.tsx](dashboard-next/src/app/studio/page.tsx)
- `/terms` — [dashboard-next/src/app/terms/page.tsx](dashboard-next/src/app/terms/page.tsx)
- `/watchlist` — [dashboard-next/src/app/watchlist/page.tsx](dashboard-next/src/app/watchlist/page.tsx)

## Configuration surface

`app/config.py` (`pydantic-settings`), read from env / Secret Manager. **Names and non-secret defaults only — no values are read from `.env`.**

| Setting | Type | Default |
| --- | --- | --- |
| `database_url` | `str` | `<redacted>` |
| `test_database_url` | `str` | `<redacted>` |
| `legiscan_api_key` | `str` | `""` |
| `open_states_api_key` | `str` | `""` |
| `anthropic_api_key` | `str` | `""` |
| `postmark_api_key` | `str` | `""` |
| `postmark_server_id` | `str` | `""` |
| `postmark_message_stream` | `str` | `'outbound'` |
| `postmark_broadcast_stream` | `str` | `'broadcast'` |
| `sendgrid_api_key` | `str` | `""` |
| `sendgrid_from_email` | `str` | `""` |
| `sendgrid_reply_to` | `str` | `""` |
| `sendgrid_hello_email` | `str` | `""` |
| `email_from` | `str | None` | `None` |
| `email_reply_to` | `str | None` | `None` |
| `email_hello_from` | `str | None` | `None` |
| `email_from_name` | `str` | `'Atlas Circular'` |
| `email_hello_from_name` | `str` | `'Kenny at Atlas Circular'` |
| `email_click_tracking` | `bool` | `False` |
| `legifrance_client_id` | `str` | `""` |
| `legifrance_client_secret` | `str` | `""` |
| `lawgokr_oc` | `str` | `""` |
| `lawsafrica_token` | `str` | `""` |
| `nys_api_key` | `str` | `""` |
| `business_address` | `str` | `""` |
| `slack_webhook_url` | `str | None` | `None` |
| `fmp_api_key` | `str` | `""` |
| `fred_api_key` | `str` | `""` |
| `comtrade_api_key` | `str` | `""` |
| `newsapi_key` | `str` | `""` |
| `nrel_api_key` | `str` | `""` |
| `africa_laws_api_key` | `str` | `""` |
| `sec_user_agent` | `str` | `'AtlasCircular/1.0 contact@atlascircular.com'` |
| `enable_epa_frs` | `bool` | `True` |
| `enable_caa_registry` | `bool` | `True` |
| `enable_sec_edgar` | `bool` | `True` |
| `max_edgar_companies_per_run` | `int` | `50` |
| `enable_openstates_ingestion` | `bool` | `True` |
| `max_openstates_calls_per_run` | `int` | `5000` |
| `openstates_request_delay_seconds` | `float` | `6.0` |
| `openstates_recent_window_days` | `int` | `2` |
| `enable_eurlex_ingestion` | `bool` | `False` |
| `eurlex_in_force_only` | `bool` | `True` |
| `max_eurlex_acts_per_run` | `int` | `400` |
| `enable_legiscan_ingestion` | `bool` | `False` |
| `max_legiscan_calls_per_run` | `int` | `5000` |
| `enable_llm_classification` | `bool` | `False` |
| `enable_sonnet_extraction` | `bool` | `False` |
| `max_haiku_calls_per_run` | `int` | `100` |
| `max_sonnet_calls_per_run` | `int` | `20` |
| `scoring_material_weight` | `float` | `0.35` |
| `scoring_geographic_weight` | `float` | `0.35` |
| `scoring_severity_weight` | `float` | `0.3` |
| `enable_interpretation` | `bool` | `False` |
| `max_interpretation_calls_per_run` | `int` | `10` |
| `interpretation_brief_ttl_days` | `int` | `7` |
| `courtlistener_api_token` | `str` | `""` |
| `courtlistener_base_url` | `str` | `<redacted>` |
| `courtlistener_webhook_secret` | `str` | `""` |
| `enable_courtlistener` | `bool` | `False` |
| `max_cl_cases_per_seed_run` | `int` | `50` |
| `max_cl_cases_per_poll` | `int` | `10` |
| `courtlistener_request_delay_seconds` | `float` | `5.0` |
| `google_cloud_project` | `str` | `'ce-bill-tracker'` |
| `cloud_run_region` | `str` | `'us-central1'` |
| `legiscan_poll_interval_hours` | `int` | `24` |
| `federal_register_poll_interval_hours` | `int` | `6` |
| `enable_digest` | `bool` | `False` |
| `digest_window_days` | `int` | `30` |
| `enable_weekly_digest` | `bool` | `False` |
| `weekly_digest_window_days` | `int` | `7` |
| `enable_deadline_alerts` | `bool` | `False` |
| `deadline_reminder_days` | `list[int]` | `<...>` |
| `enable_new_bill_alerts` | `bool` | `False` |
| `new_bill_alert_window_days` | `int` | `7` |
| `enable_trial_reminders` | `bool` | `False` |
| `trial_reminder_lead_days` | `int` | `2` |
| `enable_welcome_email` | `bool` | `True` |
| `enable_welcome_recap` | `bool` | `True` |
| `enable_auth_emails` | `bool` | `True` |
| `enable_watchlist_recap` | `bool` | `False` |
| `enable_link_audit` | `bool` | `False` |
| `link_audit_batch_size` | `int` | `400` |
| `enable_bill_text_refresh` | `bool` | `False` |
| `bill_text_refresh_batch_size` | `int` | `200` |
| `bill_text_refresh_all_bills` | `bool` | `False` |
| `access_request_notify_email` | `str` | `'kenny@superfun.studio'` |
| `stripe_secret_key` | `str` | `""` |
| `stripe_pro_monthly_price_id` | `str` | `""` |
| `stripe_pro_annual_price_id` | `str` | `""` |
| `stripe_founding_coupon_id` | `str` | `""` |
| `stripe_founding_trial_days` | `int` | `90` |
| `stripe_student_product_id` | `str` | `""` |
| `stripe_research_monthly_price_id` | `str` | `""` |
| `stripe_research_annual_price_id` | `str` | `""` |
| `stripe_webhook_secret` | `str` | `""` |
| `stripe_publishable_key` | `str` | `""` |
| `edu_email_suffixes` | `list[str]` | `<...>` |
| `firebase_project_id` | `str` | `'ce-bill-tracker'` |
| `admin_emails` | `list[str]` | `<...>` |
| `internal_emails` | `list[str]` | `<...>` |
| `app_base_url` | `str` | `<redacted>` |
| `api_base_url` | `str` | `<redacted>` |
| `unsubscribe_secret` | `str` | `""` |

## Operational scripts

`scripts/` (116 files). Most take a `--prod-dsn`/`--dsn` and default to dry-run; read the docstring before running anything against prod.

- `add_bill_from_legiscan.py` — Add a single bill that ingestion missed, sourced from LegiScan and classified by Haiku.
- `add_missing_bills.py` — Batch-add the in-scope bills found by find_missing_bills.py (the keyword-filter gaps).
- `apply_known_status_overrides.py` — Authoritative status overrides for enacted laws that automated sources can't match.
- `audit_bill_source_links.py` — Audit every bill's "View Source" link (bills.source_url) and persist the verdict.
- `audit_compliance_links.py` — Audit every "how to comply" link for rot, rebrands, and dead ends.
- `backfill_adjacency.py` — Backfill the `bills.adjacency` scope-provenance tag — transboundary pass.
- `backfill_bill_text.py` — Backfill persisted full bill text into bill_texts — Layer B Step 3 of the full-text search plan.
- `backfill_deadlines.py` — Backfill compliance deadlines for already-classified bills.
- `backfill_deadlines_legiscan.py` — Extract compliance deadlines for the HISTORICAL backfill bills using LegiScan bill text.
- `backfill_federal_actions.py` — Backfill / reclassify federal_actions on the three classifier axes.
- `backfill_foreign_dates.py` — Backfill status_date for dateless foreign bills by deriving a YEAR from data we already hold.
- `backfill_jurisdictions.py` — Seed the Atlas Circular jurisdiction tree and map every bill to its node. Idempotent — safe to
- `backfill_legiscan.py` — Attach legiscan_bill_id to EPR bills for ongoing change-tracking — with a confidence guard.
- `backfill_relevance.py` — Backfill ce_relevant for bills already tagged with a tracked policy instrument.
- `backfill_subnational_state.py` — Backfill `state` with namespaced sub-national codes for foreign federations (CA, AU).
- `build_compliance_pathways.py` — Seed the compliance-entity directory and build a compliance_pathway per enacted law.
- `build_design_guide.py` — Build the shareable Design-for-Circularity guide from persisted bill_design_signal rows.
- `build_federal_seed.py` — Validate + normalize the curated federal circular-economy *enabler* seed.
- `build_historical_seed.py` — Assemble + validate the historical EPR-law seed from researched raw data.
- `build_product_coverage.py` — Backfill covered-product coverage for electronics + battery bills (product-coverage Phase 2).
- `build_r2r_electronics_set.py` — Curated covered-product extraction for the ENACTED consumer-electronics right-to-repair laws.
- `classify_federal.py` — Backfill federal-action enrichment: ce_relevant, preemption_risk, ai_summary, material_categories.
- `classify_stance.py` — Backfill Bill.policy_stance for already-classified (ce_relevant) bills.
- `compute_dump_baseline.py` — Compute the all-bills passage-rate baseline + CE champion roster from a restored OpenStates dump.
- `content_asks.py` — Content-lane asks: run a fixed list of PUBLISHABLE questions through the REAL Ask-the-Atlas
- `corpus_survey_ask.py` — One-off: run a fixed list of corpus-survey questions through the REAL Ask-the-Atlas handler
- `correct_management_model.py` — Accuracy pass over management_model, using two HIGH-PRECISION signals the first
- `coverage_by_region.py` — Report per-region bill counts + full-text coverage + stored language — the scope map.
- `detect_bill_text_collisions.py` — Find bill_texts rows holding the WRONG bill's text (same number, different session).
- `enrich_bill_fees.py` — One-time script to enrich known_epr_laws.json with numeric fee fields.
- `estimate_dispersion.py` — One-time Sonnet estimate of the `dispersion` axis for the seed materials (MATERIAL_PROFILES).
- `export_demo_snapshot.py` — Static demo snapshot exporter.
- `extract_dimensions.py` — Backfill the v2 compliance dimensions (eco_modulation / recycled_content / penalties) across bills.
- `extract_dimensions_batch.py` — Backfill the v5 compliance dimensions across the corpus using the Anthropic Message Batches API
- `extract_fee_citations.py` — Extract fee / threshold citations for bills that already have compliance_details.
- `extract_foreign_compliance.py` — Run the Sonnet compliance extraction over already-classified FOREIGN bills (region-filtered).
- `extract_management_model.py` — Classify the producer-responsibility MANAGEMENT MODEL of enacted EPR laws.
- `extract_responsibility_chain.py` — Extract the heuristic "nearest chain of responsibility" for relevant bills (Tier 1).
- `fetch_legislative_sessions.py` — Generate real legislative session windows for the /beta Legislative Timeline.
- `find_missing_bills.py` — Sweep LegiScan for in-scope bills the DB is missing (ingestion keyword-filter gaps).
- `fix_encoding_data.py`
- `followup_germany_china.py` — Reproduce the founder's exact Germany→China thread through the real /ask handler (post-fix),
- `followup_smoke.py` — End-to-end smoke test for research follow-up threading — drives the real /ask handler in-process
- `foreign_rank_reachability.py` — Prove (or disprove) the foreign full-text RANK-REACHABILITY problem, per region.
- `ga4_admin_check.py` — Dump GA4 (property 529411970) CONFIG -- streams, enhanced measurement, custom dimensions, key events.
- `ga4_journeys.py` — Journey analysis over the GA4 BigQuery export — the questions the GA4 UI can't answer.
- `ga4_report.py` — Query GA4 (property 529411970) via the Data API and print a report to the terminal.
- `generate_codebase_context.py` — Generate a portable codebase summary you can paste into a web/app Claude chat.
- `generate_design_teaser.py` — Generate the free Design Guide teaser (dashboard-next/src/data/designGuideTeaser.ts).
- `hide_docket_shells.py` — Take pre-filing docket shells out of scope (ce_relevant True -> False).
- `hide_negated_labeling_preemption.py` — Hide labeling/preemption bills the classifier itself judged out of scope.
- `hide_untracked_instruments.py` — Hide bills that are only in scope because of an instrument we no longer track.
- `illustration_probe.py` — Exercise the router's illustration-vs-filter lever on purpose-built questions.
- `import_federal_enablers.py` — Insert curated US-FEDERAL circular-economy *enablers* (statutes / CFR / programs / EOs)
- `import_foreign_enablers.py` — Gap-B: import curated EU + UK circular-economy *enablers* (green/sustainable procurement,
- `import_historical_laws.py` — Insert pre-2016 / non-OpenStates historical EPR laws into the bills table.
- `import_openstates_pgdump.py` — Backfill bills from a restored OpenStates PostgreSQL dump.
- `ingest_eurlex.py` — Ingest EU-central circular-economy law from EUR-Lex/CELLAR into the bills table.
- `ingest_foreign.py` — Ingest foreign national circular-economy / EPR law into the bills table (pluggable per region).
- `inspect_design_levers.py` — Measure design-lever coverage in the already-extracted compliance_details.
- `inspect_encoding.py`
- `list_access_requests.py` — List "request access / pricing" leads.
- `list_subscribers.py` — List newsletter / alert subscribers.
- `mark_reviewed.py` — Promote bills to reviewed=True after a human has verified them against the source.
- `materialize_deadlines_from_details.py` — Materialize compliance_deadlines rows from ALREADY-STORED compliance_details JSON.
- `measure_stance_precision.py` — Ground-truth the precision of the "weakens" stance call — the gate behind the public red
- `mirror_regions_to_prod.py` — Mirror the NON-US region corpus (EU + foreign national law) from a source DB (dev) to a target DB
- `normalize_materials.py` — Normalize bills.material_categories to the canonical taxonomy across ALL regions.
- `pregame_oregon_briefs.py` — Pre-generate Oregon exposure briefs for demo.
- `prevalence_scan.py` — Estimate how prevalent each candidate compliance dimension is in the corpus, to prioritize which
- `propose_bill_outcomes.py` — Find documented real-world outcomes of enacted laws — the bill_outcome candidate finder.
- `propose_compliance_links.py` — Layer 3: find the authoritative "how to comply" page for weak links — propose, don't apply.
- `prune_litigation_cases.py` — Re-screen every already-ingested litigation case against the relevance gate.
- `push_bills_to_dev.py` — Mirror the local bills corpus up to the DEV Cloud SQL database, region-scoped and safe for the
- `push_bills_to_prod.py` — One-off / repeatable sync of the local bills table up to production Cloud SQL.
- `recall_enablers.py` — Gap-A enabler recall — re-judge `ce_relevant=false` bills that carry an ENABLER signal
- `recheck_remediation.py` — Re-check whether negative/mixed law outcomes have since been REMEDIATED by a later law.
- `reclassify_decommissioning.py` — Rescue durable-good / infrastructure END-OF-LIFE & DECOMMISSIONING bills that the classifier
- `reclassify_foreign_pending.py` — Classify foreign (FR/UK/JP) bills that were ingested but never classified — e.g. rows written by an
- `reclassify_incentives.py` — Retag in-scope `other`/`budget` bills as `incentives` where the lever is financial.
- `reclassify_other.py` — Mine the in-scope `other` bucket: fix mislabels, and size up new-instrument candidates.
- `reconcile_enacted.py` — Reconcile our bills.status 'enacted' against the OpenStates dump's normalized enacting actions.
- `redate_foreign.py` — Re-date the remaining dateless FOREIGN bills by re-fetching each through its own adapter and reading
- `redate_jp_cn.py` — Re-date the JP/CN residual: bills whose real promulgation date the tier-1 id/title derivation could
- `reextract_deadlines_targeted.py` — Re-extract compliance deadlines for LARGE, under-extracted laws — full-text, not front-windowed.
- `refresh_status_legiscan.py` — Refresh stale bill statuses from LegiScan (free tier).
- `region_balance_ab.py` — Read-only A/B for the relevance-gated region-balanced deep read (_balance_read_set).
- `region_perspective_sweep.py` — Run the /research/ask synthesis pipeline for one comparative question, once per region.
- `render_design_guide.py` — Render tmp/design_guide.md into a branded, print-ready single-file HTML artifact.
- `repair_bill_text_collisions.py` — Repair bill_texts rows holding the WRONG bill's text (see detect_bill_text_collisions.py).
- `rescore_companies.py` — Re-compute all ImpactScore rows using the updated CostEstimator.
- `research_pulse.py` — Timeliness PRE-PASS for the short-form article pipeline — a "social listening" step that runs BEFORE
- `reset_classification.py` — Reset classification on bills so the next classification cycle re-judges them.
- `resync_us_materials.py` — Re-derive US bills.material_categories from a pristine source through the canonical normalizer.
- `scan_bill_polymers.py` — Scan full bill text for named polymers/resins and (optionally) record what's found.
- `seed_bill_outcomes.py` — Seed the bill_outcome table — documented real-world outcomes of enacted laws.
- `seed_companies.py` — Seed the database with curated companies from data/seed/target_companies.json.
- `seed_courtlistener.py` — CourtListener Initial Seed Script
- `seed_database.py` — Seed the database with known EPR laws from data/seed/known_epr_laws.json.
- `seed_test_email_scenario.py` — Seed a self-contained, synthetic scenario for previewing the bill-driven alert emails LOCALLY.
- `seed_watchlist_test.py` — Set up a LOCAL *watchlist* subscription and fire a status-change so you can see the real-time
- `send_deadline_alerts.py` — Generate and (optionally) send event-triggered compliance-deadline reminders.
- `send_digest.py` — Generate and (optionally) send the periodic subscriber digest.
- `send_email_samples.py` — Render EVERY outbound email template in app/alerts/ with SYNTHETIC data and send one
- `send_new_bill_alerts.py` — Generate and (optionally) send event-triggered "new bill" alerts.
- `send_trial_reminders.py` — Generate and (optionally) send trial-ending reminders.
- `send_watchlist_recap.py` — Generate and (optionally) send the recurring watch-list "you added bills" recap.
- `send_welcome.py` — Preview and (optionally) send the one-time welcome email.
- `shadow_router_report.py` — Digest the shadow-mode router-vs-deterministic comparisons captured on every /research/ask.
- `shortform_articles.py` — Distill EXISTING Atlas answers into SHORT-form, publishable article drafts — the quick sibling of
- `show_compliance_pathways.py` — Render the compliance-action view a state page (or a persona feed) would show:
- `sync_enacted_and_stance_to_prod.py` — One bundled, surgical prod write: the reconciled enacted corrections + the policy_stance sync.
- `sync_management_to_prod.py` — Copy the computed management_model classification (bills.compliance_details->'management')
- `synthesize_design_principles.py` — Run the design-lever synthesis over bills that already have compliance_details.
- `test_pipeline.py` — Manual smoke test for the ingestion + classification pipeline.
- `validate_demo_data.py` — Demo readiness validation script.

## Design docs

Longer-form plans and specs live in `docs/`:

- [docs/ASK_LATENCY_PLAN.md](docs/ASK_LATENCY_PLAN.md) — Ask-the-Atlas latency — why answers get lost, and how to fix it for good
- [docs/ASK_SURFACE_SPEC.md](docs/ASK_SURFACE_SPEC.md) — Ask the Atlas gets a real home — routing spec
- [docs/ATLAS_A0_A1_SPEC.md](docs/ATLAS_A0_A1_SPEC.md) — Atlas Circular — A0 + A1 Implementation Spec
- [docs/ATLAS_CIRCULAR_ROADMAP.md](docs/ATLAS_CIRCULAR_ROADMAP.md) — Atlas Circular — Platform Roadmap & Next Major Phase
- [docs/CODEBASE_CONTEXT.md](docs/CODEBASE_CONTEXT.md) — Atlas Circular — Codebase Context
- [docs/DESIGN_REVIEW_BACKLOG.md](docs/DESIGN_REVIEW_BACKLOG.md) — Design Review — Batch 2 & 3 Backlog
- [docs/DIMENSION_EXPANSION_PLAN.md](docs/DIMENSION_EXPANSION_PLAN.md) — Dimension expansion — routing (done) + extraction plan
- [docs/EMAIL_DELIVERABILITY.md](docs/EMAIL_DELIVERABILITY.md) — Email deliverability — keeping our mail out of spam
- [docs/EXPOSURE_CALCULATOR_SPEC.md](docs/EXPOSURE_CALCULATOR_SPEC.md) — Obligation & Exposure Engine (`/exposure`) — Spec v2
- [docs/FEDERATED_EXPANSION_PLAN.md](docs/FEDERATED_EXPANSION_PLAN.md) — Federated-Jurisdiction Expansion Plan — Australia, Canada, China
- [docs/FEE_DATA_API_SPEC.md](docs/FEE_DATA_API_SPEC.md) — Fee Data API — Spec
- [docs/FOCUS.md](docs/FOCUS.md) — Current focus
- [docs/foreign_coverage_tracker.md](docs/foreign_coverage_tracker.md) — Foreign EPR Law — Coverage Tracker
- [docs/FOREIGN_INGESTION_AUTOMATION_PLAN.md](docs/FOREIGN_INGESTION_AUTOMATION_PLAN.md) — Foreign-region ingestion automation plan
- [docs/GAP_A_ENABLER_RECALL_PLAN.md](docs/GAP_A_ENABLER_RECALL_PLAN.md) — Gap-A: Cross-jurisdiction enabler recall pass
- [docs/GAP_B_ENABLER_CURATION_PLAN.md](docs/GAP_B_ENABLER_CURATION_PLAN.md) — Gap-B: Cross-jurisdiction enabler curation (out-of-corpus)
- [docs/PRO_TARIFF_INGESTION_PLAN.md](docs/PRO_TARIFF_INGESTION_PLAN.md) — PRO Tariff Schedule Ingestion — Scoping
- [docs/PUBLIC_AFFAIRS_RESEARCH_DESIGN.md](docs/PUBLIC_AFFAIRS_RESEARCH_DESIGN.md) — Public-Affairs Research Surface — Design Doc
- [docs/SCOPE_FACET_AND_MATERIAL_NAVIGATION.md](docs/SCOPE_FACET_AND_MATERIAL_NAVIGATION.md) — Scope Facet & Material-First Navigation — Spec
- [docs/SEARCH_MODE_TOGGLE_PLAN.md](docs/SEARCH_MODE_TOGGLE_PLAN.md) — Search-mode toggle: Keyword ⇄ Deep Search
- [docs/SECURITY_ASSESSMENT.md](docs/SECURITY_ASSESSMENT.md) — SignalScout / Compliance Scout — Adversarial Security Assessment & Remediation Plan
- [docs/SECURITY_DETECTION.md](docs/SECURITY_DETECTION.md) — Security detection — probing & abuse telemetry
- [docs/SENDGRID_COMPLIANCE_RESPONSE.md](docs/SENDGRID_COMPLIANCE_RESPONSE.md) — SendGrid compliance ticket — response
- [docs/V1_SUMMARY.md](docs/V1_SUMMARY.md) — SignalScout / Compliance Scout — V1 Summary
- [docs/V2_FULLTEXT_SEARCH_PLAN.md](docs/V2_FULLTEXT_SEARCH_PLAN.md) — V2 — Full-Text Bill Search with Material-Attribute Precision & In-Text Highlighting

## Conventions worth knowing

- Bills carry `region` (2-char family: `US`, `EU`, `JP`…) plus `state` (sub-jurisdiction, namespaced for federations: `CA-BC`, `AU-NSW`). `jurisdiction_id` is the normalized tree that supersedes the flat pair.
- Non-US bills key on `celex_id`/`foreign_id`; US bills key on `openstates_id`. That's what makes dev→prod mirroring of foreign rows collision-free.
- Foreign law is enacted-only, so only enacted counts are comparable across borders.
- Classification changes are audit-logged to `classification_changes` with a `run_id` — reclassification scripts must write there so flips can be undone.
- `compliance_details` is a JSONB envelope carrying extracted dimensions (fees, eco-modulation, targets, penalties, lifecycle) with `source_excerpt` provenance.

