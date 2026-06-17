# SignalScout / Compliance Scout — V1 Summary

_Generated 2026-06-17. Snapshot of the system as it stands going into the founding-member launch._

> Public brand: **Battle of the Bills** (battleofbills.com / ce-bill-tracker.web.app).
> A legislative-intelligence platform tracking US state + federal EPR / circular-economy law:
> ingest bills → classify (keywords + Claude) → score company exposure → synthesize compliance
> guidance → alert subscribers. Monetized as a single **Pro** tier ($400/mo, $3,600/yr) with a
> founding 50%-off-for-life coupon, no-card trials, and share-to-unlock referrals.

---

## 1. Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Uvicorn (async), Python |
| Frontend | Next.js (App Router, static export) → Firebase Hosting |
| Database | PostgreSQL 16 (Cloud SQL), JSONB + `pg_trgm`, SQLAlchemy 2.0 async (asyncpg) |
| Migrations | Alembic (`alembic upgrade head` on every full deploy) |
| LLM | Anthropic Claude — Haiku (classify), Sonnet (extract + briefs) |
| Auth | Firebase Auth (ID tokens) verified server-side via firebase-admin |
| Payments | Stripe (Checkout + Customer Portal + webhooks) |
| Email / alerts | SendGrid (email), Slack webhooks |
| Scheduler | APScheduler (in-process, in the always-on API) + Cloud Run Jobs |
| Hosting | GCP project `ce-bill-tracker`, region `us-central1` |

---

## 2. What is LIVE in production

**Deploy mechanism:** manual `gcloud builds submit` against `cloudbuild.yaml`. There is **no auto-trigger** — deploys ship the **working tree, not git HEAD**. So `.gcloudignore` correctness is a load-bearing security control (see security assessment).

### Prod services
| Service | Source | Notes |
|---------|--------|-------|
| Cloud Run `signalscout-api` | `Dockerfile.api` | Public REST API (`--allow-unauthenticated`); min 1 / max 3 instances; Cloud SQL attached; secrets from Secret Manager |
| Cloud Run Job `signalscout-pipeline` | `Dockerfile.job` (`MODE=ingest`) | Daily ingest + classification |
| Cloud Run Job `signalscout-classify` | `Dockerfile.job` (`MODE=classify`) | Classification-only runs |
| Firebase Hosting | `dashboard-next/out` | Static Next.js export + baked CDN data snapshot |
| Cloud SQL Postgres | `signalscout-pg` | Primary datastore |

> Note: `Dockerfile.dashboard` builds the **legacy Streamlit `dashboard/`** app — not part of the V1 frontend (which is `dashboard-next` on Firebase). It can be retired.

### Prod feature flags (set in `cloudbuild.yaml`)
`ENABLE_LLM_CLASSIFICATION=true`, `ENABLE_SONNET_EXTRACTION=true`, `ENABLE_COURTLISTENER=true`, `ENABLE_OPENSTATES_INGESTION=true`, `ENABLE_LEGISCAN_INGESTION=false`, `ENABLE_TRIAL_REMINDERS=true`, welcome emails on. ⚠️ `ENABLE_INTERPRETATION` is set inconsistently across services in cloudbuild (true at one block, false at another) — **verify which value the public API service actually runs** (it gates an unauthenticated LLM-cost endpoint — see security doc C-2).

### Prod schema
Migrations **001–023** are committed and applied on each deploy. Prod is at **023**. Migration **024 (`bill_outcome`)** is local/untracked and not yet on prod.

### API surface (all internet-reachable; `--allow-unauthenticated`)
`/health` · `/bills` (+ map-summary, timeline, deadlines/upcoming, litigation) · `/federal-actions` + `/litigation-cases` · `/companies` (+ exposure-ranking, exposure-brief, impact-scores, obligations) + `/entity-match-queue` · `/compliance/pathways` · `/design-guide/full` · `/subscriptions` · `/access-requests` · `/billing` (checkout, portal, webhook, signup-trial) · `/referrals` · `/me` (settings/watchlist, Firebase-gated) · `/admin` (email-allowlist gated) · `/webhooks/courtlistener` · `/pipeline/*` (operator triggers).

### Frontend routes (live on Firebase)
`/` Bill Explorer · `/embed` · `/insights` · `/states` + `/states/[abbr]` · `/federal` · `/compliance` (Upcoming Deadlines, "Pro-gated") · `/design-guide` (Pro) · `/company` (access-gated) · `/watchlist` (Pro) · `/account` · `/pricing` · `/about` · `/methodology` · `/admin`, `/beta` (admin-only).

---

## 3. What exists LOCALLY but is NOT yet in prod

Two in-flight features live in the working tree (uncommitted) and will only reach prod on the next full deploy:

**A. "Real-World Impact" layer** (the `BillOutcome` feature)
- `alembic/versions/024_bill_outcome.py` (new table — **needs prod migrate**)
- `scripts/seed_bill_outcomes.py` (new seeder — **needs prod seed**)
- `app/models.py` (+`BillOutcome`), `app/schemas.py` (+`BillOutcomeSummary`), `app/api/bills.py` (+`GET /bills/outcomes`)
- `dashboard-next/.../insights/RealWorldImpact.tsx` (new), `insights/page.tsx`, `lib/api.ts` + `types.ts` (+`fetchBillOutcomes`)

**B. Legislative-session timeline rework**
- `dashboard-next/.../beta/LegislativeTimeline.tsx` (reworked) + `beta/legislative-sessions.json` (new)
- `scripts/fetch_legislative_sessions.py` (reworked)

> Per memory `real-world-impact-layer.md`, the `bill_outcome` table is seeded only in local dev (oyster law) and still needs a research backfill before prod is meaningful.

---

## 4. Data model (core entities)

- **`Bill`** — central record: ingestion fields + classification (`epr_relevant`, `confidence_score`, `material_categories`, `instrument_type`, `policy_stance`) + Sonnet `compliance_details` JSONB + `litigation_risk`. Confidence sentinels: `None`/`-1.0` = unclassified.
- **`BillChange`** — change-detection log feeding alerts. **`ComplianceDeadline`** — extracted deadlines (powers `/compliance`).
- **`BillDesignSignal`, `BillProductCoverage`, `BillFeeCitation`** — per-bill extracted atoms, each with a verbatim `source_excerpt` chain-of-custody.
- **`FederalAction`** — Federal Register docs, 3 classifier axes (friction / instrument / material) + preemption risk.
- **Company impact:** `Company`, `CompanyAlias`, `CompanyMaterial`, `CompanyStatePresence`, `ImpactScore`, `ExposureBrief`, `EntityMatchQueue`.
- **Litigation:** `LitigationCase`, `LitigationEvent`, `CLAlertSubscription`.
- **Accounts / monetization:** `AlertSubscription`, `AccessRequest`, **`Entitlement`** (the paid-seat bridge: Firebase uid ↔ Stripe customer; plan/status/comp/founding/referral_code/signup_trial_used), `Referral`, `UserSettings`, `WatchlistItem`.
- **Compliance action layer:** `ComplianceEntity` (PRO / agency directory) + `CompliancePathway` (one next-action per enacted law).
- **`BillOutcome`** — NEW / local only.

---

## 5. Pipeline subsystems (all real, no stubs)

- **Ingestion** — OpenStates v3 (live authoritative), Federal Register, CourtListener (litigation). LegiScan is **dormant** (purged in migration 004, flag off). Bulk historical backfill via restored PG dump.
- **Classification** — 3 stages: deterministic keywords → Claude Haiku (relevance/material/instrument/stance) → Claude Sonnet (full `compliance_details`). LLM stages flag-gated + per-run call caps.
- **Scoring** — composite ImpactScore = material 0.35 × geographic 0.35 × severity 0.30; grounded $ cost estimates from fee citations (CA SB54 etc.); Sonnet Exposure Briefs (7-day TTL cache).
- **Synthesis** — design-levers, Design-for-EPR guide, fee citations, product-coverage taxonomy (electronics/batteries, in code not DB).
- **Company intel** — EPA FRS → CAA registry → SEC EDGAR enrichment; entity resolution (hard-id → alias → pg_trgm fuzzy → manual queue). ⚠️ CAA scraper is fragile (falls back to a hardcoded 10-producer list silently if the page structure changes).
- **Alerts** — real-time change → email/Slack; digests, deadline/new-bill alerts, trial reminders, welcome emails. Most cadences dormant behind flags (preview-via-script before enabling).
- **Scheduler** — APScheduler cron in the always-on API (daily ingest/classify/score, 6-hourly federal, 30-min alert dispatch, weekly company refresh).

---

## 6. Scripts (~54 in `scripts/`)
Grouped: bill ingest/backfill · historical/seed data · classification & curation · synthesis/extraction · company scoring · email/alert preview-and-send · prod sync/ops (`push_bills_to_prod.py`, `bootstrap_gcp.ps1`, snapshot export) · data hygiene/QA.

---

## 7. Known caveats carried into launch
- `PROJECT_STATUS.md` at repo root is **stale** (dated 2026-03-26, describes the Streamlit dashboard and a LegiScan-first pipeline). This doc supersedes it for the frontend/monetization picture.
- CAA registry scraper fragility (silent fallback).
- No automated test coverage for: cost estimator, exposure-brief generator, alert dispatcher, email senders, **any API endpoint**, billing/webhook paths, referral/trial logic. (Tests exist for keyword classifier, scoring engine, change detector, entity resolver, ingestion.)
- Entitlement is keyed on **email**, while user-owned data is keyed on **uid** (see security doc M-2).

---

_See `docs/SECURITY_ASSESSMENT.md` for the adversarial findings and the remediation / contingency plan._
