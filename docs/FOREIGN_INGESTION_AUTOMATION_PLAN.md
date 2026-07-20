# Foreign-region ingestion automation plan

**Status:** planned, not built (2026-07-19). EUR-Lex weekly refresh is already wired
(`run_eurlex_cycle`); this generalizes the same pattern to the non-EU foreign adapters in
`app/ingestion/foreign.py`.

## Problem

US bills (LegiScan/OpenStates) and EU law (EUR-Lex) refresh automatically on the in-process
APScheduler (`app/scheduler/jobs.py`, runs inside the always-on API service). The **foreign
national-law corpus** (`FOREIGN_CLIENTS`, 36 region keys, ~800 non-US bills live in prod) has
**no scheduled job** — it was populated by one-off `scripts/ingest_foreign.py --region XX` runs and
only grows when someone re-runs those by hand.

## Key finding: LIVE vs SEED discovery

Scheduling only helps adapters whose `discover()` makes a live catalog/search query. Classification
of all 36 keys:

- **17 LIVE** — `discover()` queries the source catalog + keyword-filters, so a scheduled
  `only_new` refresh surfaces newly-enacted laws:
  `JP, JP_ORD, FR, FR_CODE, UK, DE, NL, SE, PL, KR, ZA, KE, CN, CN_GOV, CA, CA_BC, AU`.
- **19 SEED** — `discover()` returns a hardcoded seed list, so scheduling yields **nothing new**
  until the seed list is hand-expanded:
  `ES, CL, IE, AT, BR, CH, DK, FI, LU, SI, SK, LV, EE, LT, CZ, CA_ON, AU_NSW, AU_QLD, AU_TAS`.

Cross-referenced against what is actually in prod today (`GET /bills/text-coverage?by_region=true`),
the LIVE set splits into three buckets:

| Bucket | Regions | Action |
|--------|---------|--------|
| **A. LIVE + in prod + keyless** | JP (113), UK (88), PL (50), CN (40), SE (34), NL (30), AU (28), CA (17), DE (15) | Schedule now — pure win, no secrets |
| **B. LIVE but blocked/cold** | FR (122, needs PISTE OAuth creds not in prod secrets); KR/ZA/KE (0 in prod, KR needs a key) | Schedule after adding creds / initial bulk load |
| **C. SEED** | the 19 above (~14 already in prod, frozen) | Scheduling is a no-op; needs seed-list growth instead |

## Design (mirror the EUR-Lex path)

1. **Config** (`app/config.py`):
   - `enable_foreign_ingestion: bool = False`
   - `foreign_ingestion_regions: str = "JP,UK,PL,CN,SE,NL,AU,CA,DE"` (bucket A; CSV, parsed to list)
   - `max_foreign_laws_per_run: int = 100` (per region, bounds a runaway)
2. **Scheduler job** (`app/scheduler/jobs.py`): `run_foreign_cycle()` — gated on the flag, loops the
   configured regions, calls `sync_foreign(region, classify=True, only_new=True,
   max_laws=settings.max_foreign_laws_per_run)` with a per-region try/except (one region's source
   hiccup must not abort the rest) and a small `asyncio.sleep` between regions. Register weekly,
   staggered from EUR-Lex (Tue 05:30) — e.g. **Thu 05:30 UTC**.
3. **Deploy** (`cloudbuild.yaml`, `deploy-api` `--set-env-vars`):
   `ENABLE_FOREIGN_INGESTION=true,FOREIGN_INGESTION_REGIONS=JP,UK,PL,CN,SE,NL,AU,CA,DE`.
   The job runs in the API service (same as `run_eurlex_cycle`), so no pipeline-job change needed.
4. **FR later:** add PISTE OAuth secrets (`LEGIFRANCE_CLIENT_ID/SECRET`) to the `deploy-api`
   `--set-secrets`, then append `FR` (and `FR_CODE`) to `FOREIGN_INGESTION_REGIONS`.
5. **KR/ZA/KE later:** these are cold in prod — run a one-time `scripts/ingest_foreign.py --region KR`
   bulk load first (KR needs a law.go.kr key), then add to the scheduled list.

## Caveats

- **Cost:** each newly-discovered law runs Haiku (relevance) + Sonnet (compliance extraction).
  Bounded per region by `max_foreign_laws_per_run`; foreign volumes are low (tens/region) so this is
  modest, but it is real per-run LLM spend.
- **Secrets in prod:** only FR/KR need credentials; the 9 bucket-A regions are keyless.
- **Proxy vs job:** long LLM-heavy runs over a laptop→Cloud SQL proxy drop connections (see
  eu-integration memory). The scheduled in-API job avoids that; ad-hoc bulk loads should prefer a
  Cloud Run job over the laptop proxy.

## Test before wiring

Per the runner's own warning ("do NOT point at prod during the spike"), prove the path against the
**dev** DB with a bounded run of one bucket-A region:

```
venv/Scripts/python scripts/ingest_foreign.py --region JP --only-new --max 12 \
    --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout_dev"
```

Confirm discover → fetch → classify surfaces + tags new laws end-to-end, then wire `run_foreign_cycle`.
