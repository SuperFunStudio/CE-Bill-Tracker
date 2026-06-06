# SignalScout — Project Status (2026-03-26)

## What It Is

SignalScout is a legislative intelligence platform monitoring US state-level **EPR (Extended Producer Responsibility)** and environmental regulations. It ingests bills from multiple sources, classifies them using keyword matching and Claude LLM, scores company compliance exposure, generates AI-powered advisory briefs, and alerts subscribers when bills change. A Streamlit dashboard visualizes bills, company impact rankings, deadlines, and federal preemption risk.

**Hard deadline:** Oregon NAW trial — **July 13, 2026**. Demo-ready MVP must be live by **June 15, 2026**.

---

## Module Implementation Status

Everything listed here has been reviewed against actual source code. No stubs, no `NotImplementedError`, no hardcoded dummy data.

### Ingestion

| Module | File | Status | Notes |
|--------|------|--------|-------|
| LegiScan client | [app/ingestion/legiscan.py](app/ingestion/legiscan.py) | ✅ Full | Real API, retry/backoff, base64 bill text decode |
| Federal Register client | [app/ingestion/federal_register.py](app/ingestion/federal_register.py) | ✅ Full | No auth required, paginated, EPR term list |
| Open States client | [app/ingestion/openstates.py](app/ingestion/openstates.py) | ✅ Full | Real API w/ auth, 2-day incremental window |
| Ingestion coordinator | [app/ingestion/coordinator.py](app/ingestion/coordinator.py) | ✅ Full | All 3 sources, change-hash dedup, ON CONFLICT upsert |

### Classification (3-Stage Pipeline)

| Stage | File | Status | Notes |
|-------|------|--------|-------|
| Stage 1: Keywords | [app/classification/keywords.py](app/classification/keywords.py) | ✅ Full | Regex, weighted scoring (primary=1.0, material=0.8, policy=0.4), exclusions=-2.0 |
| Stage 2: Haiku | [app/classification/haiku_classifier.py](app/classification/haiku_classifier.py) | ✅ Full | Real `claude-haiku-4-5` API, JSON output, batch support. **Gated by `ENABLE_LLM_CLASSIFICATION`** |
| Stage 3: Sonnet | [app/classification/sonnet_extractor.py](app/classification/sonnet_extractor.py) | ✅ Full | Real `claude-sonnet-4-6` API, 14-field extraction. **Gated by `ENABLE_SONNET_EXTRACTION`** |
| Orchestrator | [app/classification/pipeline.py](app/classification/pipeline.py) | ✅ Full | Chains all 3 stages, fetches full bill text for Sonnet, creates ComplianceDeadline rows |

### Scoring

| Module | File | Status | Notes |
|--------|------|--------|-------|
| Scoring engine | [app/scoring/engine.py](app/scoring/engine.py) | ✅ Full | Material (volume-weighted) + geographic (presence-type) + severity (likelihood×0.4 + impact×0.6) |
| Cost estimator | [app/scoring/cost_estimator.py](app/scoring/cost_estimator.py) | ✅ Full | Real fee structures (calrecycle, paintcare, MRC), category benchmarks as fallback |
| Exposure brief generator | [app/scoring/interpreter.py](app/scoring/interpreter.py) | ✅ Full | Real `claude-sonnet-4-6`, structured 5-section JSON, 7-day TTL cache. **Gated by `ENABLE_INTERPRETATION`** |

### Company Intel & Entity Resolution

| Module | File | Status | Notes |
|--------|------|--------|-------|
| Entity resolver | [app/company_intel/resolver.py](app/company_intel/resolver.py) | ✅ Full | 5-step: DUNS/CIK/EPA ID → exact alias → pg_trgm fuzzy (0.85) → queue → manual |
| EPA FRS enrichment | [app/company_intel/epa_frs.py](app/company_intel/epa_frs.py) | ✅ Full | Real public API, SIC code → presence_type mapping |
| CAA Registry scraper | [app/company_intel/state_registries.py](app/company_intel/state_registries.py) | ⚠️ Partial | Live HTML scrape with regex parsing. Falls back to hardcoded 10-item producer list on failure. Fragile if CAA changes page structure. |
| SEC EDGAR enrichment | [app/company_intel/sec_edgar.py](app/company_intel/sec_edgar.py) | ✅ Full | Real EDGAR API, 10-K text extraction, volume regex, rate-limited to 8 req/s |
| Company intel coordinator | [app/company_intel/coordinator.py](app/company_intel/coordinator.py) | ✅ Full | EPA FRS → CAA → EDGAR in sequence, error isolation per source |

### Alerts

| Module | File | Status | Notes |
|--------|------|--------|-------|
| Change detector | [app/alerts/detector.py](app/alerts/detector.py) | ✅ Full | Status changes, text hash updates, score delta ≥10 pts |
| Alert dispatcher | [app/alerts/dispatcher.py](app/alerts/dispatcher.py) | ✅ Full | Subscription matching by state + material category, litigation context enrichment |
| SendGrid sender | [app/alerts/sendgrid_sender.py](app/alerts/sendgrid_sender.py) | ✅ Full | Real SendGrid API, styled HTML email templates |
| Slack sender | [app/alerts/slack_sender.py](app/alerts/slack_sender.py) | ✅ Full | Real webhook, Block Kit formatting, retry/backoff |

### API Endpoints

| File | Endpoints | Status |
|------|-----------|--------|
| [app/api/health.py](app/api/health.py) | `GET /health` | ✅ Full |
| [app/api/bills.py](app/api/bills.py) | `GET /bills`, `/bills/{id}`, `/bills/map-summary`, `/bills/deadlines/upcoming` | ✅ Full |
| [app/api/companies.py](app/api/companies.py) | `/companies`, `/companies/{id}`, `/companies/{id}/impact-scores`, `/companies/{id}/exposure-brief`, `/companies/exposure-ranking`, `/bills/{id}/company-exposure`, `/entity-match-queue`, `PATCH /entity-match-queue/{id}/resolve` | ✅ Full |
| [app/api/alerts.py](app/api/alerts.py) | `POST /subscriptions`, `DELETE /subscriptions/{id}` | ✅ Full |
| [app/api/federal.py](app/api/federal.py) | `GET /federal-actions`, `/litigation-cases`, `/litigation-cases/{id}` | ✅ Full |
| [app/api/pipeline.py](app/api/pipeline.py) | `POST /pipeline/run`, `/pipeline/run-openstates`, `/pipeline/run-federal`, `/pipeline/seed` | ✅ Full |
| [app/api/webhooks.py](app/api/webhooks.py) | CourtListener webhook receiver (HMAC verification, docket/search alert processing) | ✅ Full |

### Dashboard Pages

| File | Purpose | Status |
|------|---------|--------|
| [dashboard/pages/01_map.py](dashboard/pages/01_map.py) | Choropleth state map of EPR activity | ✅ Full — real API |
| [dashboard/pages/02_bill_tracker.py](dashboard/pages/02_bill_tracker.py) | Bill search, filter, detail view (fee structure, deadlines, PRO requirements) | ✅ Full — real API |
| [dashboard/pages/03_compliance_cal.py](dashboard/pages/03_compliance_cal.py) | Upcoming compliance deadlines, Plotly timeline | ✅ Full — real API |
| [dashboard/pages/04_federal.py](dashboard/pages/04_federal.py) | Federal Register actions, litigation cases, event timelines | ✅ Full — real API |
| [dashboard/pages/05_company_impact.py](dashboard/pages/05_company_impact.py) | Company exposure ranking, per-bill cost charts, Exposure Brief display | ✅ Full — real API |

### Scheduler Jobs

All jobs are wired in [app/scheduler/jobs.py](app/scheduler/jobs.py) — none are stubs.

| Time (UTC) | Job | Notes |
|------------|-----|-------|
| 2:00 AM daily | `run_ingestion_cycle()` | LegiScan + Open States + Federal Register + Classification |
| 3:00 AM daily | `run_scoring_cycle()` | Recompute all ImpactScore rows, detect deltas ≥10 pts |
| 4:00 AM daily | `run_interpretation_cycle()` | Generate expired/missing ExposureBriefs (requires `ENABLE_INTERPRETATION=true`) |
| 7:30 AM daily | `refresh_active_cases()` | CourtListener case refresh (requires `ENABLE_COURTLISTENER=true`) |
| Every 6h | `run_federal_cycle()` | Federal Register poll only |
| Every 30m (8–18 UTC) | `run_alert_dispatch()` | Dispatch pending BillChange records to subscribers |
| Sunday 4:00 AM | `run_company_refresh()` | EPA FRS + CAA Registry + SEC EDGAR enrichment |
| Monday 6:00 AM | `poll_courtlistener_new_cases()` | New litigation case ingestion |

---

## Pipeline Run Sequence

### Cold Start (First Time)

```bash
# 1. Apply DB migrations (001 bills schema + 002 company impact schema)
venv/Scripts/alembic upgrade head

# 2. Seed ~30 manually-verified EPR laws
venv/Scripts/python scripts/seed_database.py

# 3. Seed 100+ curated companies (Oregon-focused)
venv/Scripts/python scripts/seed_companies.py

# 4. (Optional) Backfill LegiScan — matches seeded known laws to live bill IDs
venv/Scripts/python scripts/backfill_legiscan.py

# 5. Start the API
uvicorn app.main:app --reload

# 6. Trigger ingestion (or wait for 2AM scheduler)
#    Runs LegiScan + Open States + Federal Register + Classification pipeline
curl -X POST http://localhost:8000/pipeline/run

# 7. Trigger scoring (or wait for 3AM scheduler)
venv/Scripts/python -c "import asyncio; from app.scheduler.jobs import run_scoring_cycle; asyncio.run(run_scoring_cycle())"

# 8. Trigger company enrichment (or wait for Sunday 4AM scheduler)
#    Runs EPA FRS → CAA Registry → SEC EDGAR in sequence
venv/Scripts/python -c "import asyncio; from app.scheduler.jobs import run_company_refresh; asyncio.run(run_company_refresh())"

# 9. (Optional) Pre-generate exposure briefs for demo
#    Requires ENABLE_INTERPRETATION=true in .env
venv/Scripts/python scripts/pregame_oregon_briefs.py

# 10. Run pre-demo validation checklist
venv/Scripts/python scripts/validate_demo_data.py
```

### Ongoing Operation

Once running, the APScheduler in `app/main.py` handles all jobs automatically. Manual triggers available via `POST /pipeline/run*` endpoints.

### Dashboard

```bash
# Standard
streamlit run dashboard/app.py

# Oregon demo mode (filters to OR bills, shows demo banner)
DEMO_MODE=true streamlit run dashboard/app.py
```

> **Windows note:** Always use `venv\Scripts\python.exe`, not system Python. The venv directory is `venv/` (not `.venv/`).

---

## Feature Flags

All LLM and paid-API features default to `False` to protect costs during development. Must be explicitly enabled in `.env`.

| Flag | Default | Effect |
|------|---------|--------|
| `ENABLE_LLM_CLASSIFICATION` | `false` | Gates Claude Haiku calls in classification pipeline |
| `ENABLE_SONNET_EXTRACTION` | `false` | Gates Claude Sonnet compliance detail extraction |
| `ENABLE_INTERPRETATION` | `false` | Gates Exposure Brief generation (Claude Sonnet) |
| `ENABLE_COURTLISTENER` | `false` | Gates litigation case polling and webhook processing |
| `ENABLE_OPENSTATES_INGESTION` | `true` | Open States supplementary ingestion in daily cycle |
| `ENABLE_EPA_FRS` | `true` | EPA FRS facility ingestion in weekly company refresh |
| `ENABLE_CAA_REGISTRY` | `true` | CAA Oregon registry scraper in weekly company refresh |
| `ENABLE_SEC_EDGAR` | `true` | SEC EDGAR 10-K volume extraction in weekly company refresh |
| `MAX_HAIKU_CALLS_PER_RUN` | `100` | API call cap per ingestion cycle |
| `MAX_SONNET_CALLS_PER_RUN` | `20` | API call cap per ingestion cycle |
| `MAX_INTERPRETATION_CALLS_PER_RUN` | `10` | Brief generation cap per daily cycle |
| `INTERPRETATION_BRIEF_TTL_DAYS` | `7` | Days before cached Exposure Brief expires |
| `MAX_EDGAR_COMPANIES_PER_RUN` | `50` | Companies searched per EDGAR run (SEC rate limit) |

---

## Known Caveats

### CAA Registry Scraper (`app/company_intel/state_registries.py`)
Live HTML scraping of the Circular Action Alliance registry with regex-based table parsing. If the live fetch fails or returns empty, falls back to a hardcoded list of 10 curated Oregon producers. The scraper will break silently if CAA changes their page structure — the fallback list will kick in and `is_live=False` will be logged.

### CORS Configuration (`app/main.py`)
`http://localhost:3000` is hardcoded in the CORS allowed origins list. Move to an env var before production deployment.

### LLM Flags Default Off
`ENABLE_LLM_CLASSIFICATION`, `ENABLE_SONNET_EXTRACTION`, and `ENABLE_INTERPRETATION` all default to `False`. With all three off, the system produces usable keyword-scored bills and composite impact scores, but no Haiku relevance classification, no Sonnet compliance detail extraction, and no Exposure Briefs. Enable them in `.env` for a real run.

---

## Test Coverage

| Area | Test File | Status |
|------|-----------|--------|
| Keyword classifier | [tests/test_classification/test_keywords.py](tests/test_classification/test_keywords.py) | ✅ Covered |
| Scoring engine | [tests/test_scoring/test_engine.py](tests/test_scoring/test_engine.py) | ✅ Covered |
| Change detector | [tests/test_alerts/test_detector.py](tests/test_alerts/test_detector.py) | ✅ Covered |
| Entity resolver | [tests/test_company_intel/](tests/test_company_intel/) | ✅ Covered (resolver, EPA FRS, EDGAR, state registries, coordinator) |
| Ingestion | [tests/test_ingestion/](tests/test_ingestion/) | ✅ Directory exists |
| Cost estimator | — | ❌ No tests |
| Exposure brief generator | — | ❌ No tests |
| Alert dispatcher | — | ❌ No tests |
| SendGrid / Slack senders | — | ❌ No tests |
| All API endpoints | — | ❌ No tests |
| CourtListener webhook | — | ❌ No tests |

---

## Pre-Demo Checklist (Before July 13 Trial)

1. `venv/Scripts/python scripts/seed_companies.py` — confirm 100+ companies seeded
2. Trigger weekly company refresh — wires EPA FRS + CAA + EDGAR data
3. Review `GET /entity-match-queue` — **must be zero unresolved before demo**
4. Set `ENABLE_INTERPRETATION=true`, run `scripts/pregame_oregon_briefs.py` — pre-generate top-50 OR SB 582 briefs
5. `venv/Scripts/python scripts/validate_demo_data.py` — confirm all checks pass
6. `venv/Scripts/python scripts/export_demo_snapshot.py` — generate static JSON backup fallback

---

## Essential Files

### Entry Points
| File | Purpose |
|------|---------|
| [app/main.py](app/main.py) | FastAPI app + APScheduler lifespan management |
| [app/config.py](app/config.py) | All settings (env vars, feature flags, API keys, scoring weights) |
| [dashboard/app.py](dashboard/app.py) | Streamlit landing page |

### Data Layer
| File | Purpose |
|------|---------|
| [app/models.py](app/models.py) | All ORM models: `Bill`, `BillChange`, `AlertSubscription`, `FederalAction`, `ComplianceDeadline`, `Company`, `CompanyAlias`, `CompanyMaterial`, `CompanyStatePresence`, `ImpactScore`, `EntityMatchQueue`, `ExposureBrief`, `LitigationCase`, `LitigationEvent` |
| [app/schemas.py](app/schemas.py) | Pydantic response schemas — controls what the API returns |
| [app/database.py](app/database.py) | Async SQLAlchemy engine + session factory |
| [alembic/versions/001_initial_schema.py](alembic/versions/001_initial_schema.py) | Bills, alerts, deadlines, federal actions schema |
| [alembic/versions/002_company_impact_schema.py](alembic/versions/002_company_impact_schema.py) | Company scoring schema: 7 new tables + pg_trgm fuzzy index |

### Seed Data & Scripts
| File | Purpose |
|------|---------|
| [data/seed/known_epr_laws.json](data/seed/known_epr_laws.json) | ~30 manually-verified EPR laws with full compliance metadata |
| [data/seed/target_companies.json](data/seed/target_companies.json) | 100+ curated companies with materials, state presences, volume estimates |
| [data/seed/epr_keywords.json](data/seed/epr_keywords.json) | Keyword thesaurus (primary, material, policy, preemption, exclusion keywords) |
| [scripts/seed_database.py](scripts/seed_database.py) | Idempotent bill/law seeder |
| [scripts/seed_companies.py](scripts/seed_companies.py) | Idempotent company seeder with entity resolution |
| [scripts/backfill_legiscan.py](scripts/backfill_legiscan.py) | Match seeded known laws to live LegiScan bill IDs |
| [scripts/rescore_companies.py](scripts/rescore_companies.py) | Recompute all ImpactScore rows from scratch |
| [scripts/validate_demo_data.py](scripts/validate_demo_data.py) | Pre-demo pass/fail checklist |
| [scripts/pregame_oregon_briefs.py](scripts/pregame_oregon_briefs.py) | Pre-generate top-50 OR exposure briefs |
| [scripts/export_demo_snapshot.py](scripts/export_demo_snapshot.py) | Export static JSON backup to `data/demo_snapshot/` |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI + Uvicorn |
| Database | PostgreSQL 16 + JSONB + pg_trgm extension |
| ORM | SQLAlchemy 2.0 (async, asyncpg driver) |
| Migrations | Alembic |
| LLM | Anthropic Claude — Haiku (classify), Sonnet (extract compliance details + generate Exposure Briefs) |
| Scheduler | APScheduler (AsyncIOScheduler) |
| HTTP client | httpx + tenacity (retry/backoff) |
| Notifications | SendGrid (email), Slack webhooks |
| Dashboard | Streamlit + Plotly |
| Config | Pydantic Settings + python-dotenv |
| Logging | structlog (structured JSON) |
| Testing | pytest + pytest-asyncio + respx |

---

## Scoring Engine Summary

**Composite score = material × 0.35 + geographic × 0.35 + severity × 0.30** (weights configurable in `app/config.py`)

| Sub-score | Method |
|-----------|--------|
| **Material** | Volume-weighted overlap of company materials vs bill's covered materials. Falls back to count-based if volume data is absent. |
| **Geographic** | Max presence-type weight for the bill's state: manufacturing (100), distribution (85), HQ (80), retail (60), registered agent (30), sales (20). Returns 0 if no presence in bill's state. |
| **Severity** | Likelihood (introduced=20, committee=40, one-chamber=60, signed=100) × 0.4 + Impact (fee_per_ton/500 capped at 100, fallback to 50 or 30) × 0.6 |

---

## Environment Variables

See `.env` (not tracked in git). Minimum required:

```
DATABASE_URL=postgresql+asyncpg://...
ANTHROPIC_API_KEY=...
LEGISCAN_API_KEY=...
```

Optional:
```
OPEN_STATES_API_KEY=...          # Required for ENABLE_OPENSTATES_INGESTION=true
SENDGRID_API_KEY=...
SLACK_WEBHOOK_URL=...
COURTLISTENER_API_KEY=...        # Required for ENABLE_COURTLISTENER=true
COURTLISTENER_WEBHOOK_SECRET=... # Required for webhook signature verification
ENABLE_LLM_CLASSIFICATION=true
ENABLE_SONNET_EXTRACTION=true
ENABLE_INTERPRETATION=true
DEMO_MODE=true
SEC_USER_AGENT=SignalScout/1.0 contact@signalscout.io
```

---

## Known Gotchas

- `BillSummary` schema (`app/schemas.py`) controls list API output — fields absent from `BillSummary` are silently absent in dashboard responses even if in the DB
- `source_url` was missing from `BillSummary` (only in `BillDetail`) — fixed 2026-03-16
- Literal Unicode characters (em-dash `—`, smart quotes) in Python strings cause `SyntaxError` — use `\u2014`, `\u2019` escapes
- Dashboard fetches all 500 bills client-side and filters in Python (intentional for this data scale)
- Alembic `env.py` strips `+asyncpg` from `DATABASE_URL` (Alembic needs sync driver)
- `exposure-ranking` route in `app/api/companies.py` must be declared **before** `/{company_id}` — FastAPI resolves routes in registration order
- `pg_trgm` extension must be enabled before the `company_alias` GIN index works — Migration 002 runs `CREATE EXTENSION IF NOT EXISTS pg_trgm` automatically
- `all_companies_volumes` dict in `run_scoring_cycle` maps `company_id → company's own total volume`; the engine normalizes by `sum(all_companies_volumes.values())` for market-share weighting
