from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:dev@localhost:5432/signalscout"
    test_database_url: str = "postgresql://postgres:dev@localhost:5432/signalscout_test"

    # API Keys
    legiscan_api_key: str = ""
    open_states_api_key: str = ""
    anthropic_api_key: str = ""
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "alerts@signalscout.io"
    # Légifrance API via PISTE (France national law — app/ingestion/foreign.py LegifranceClient).
    # Free OAuth2 client-credentials from https://piste.gouv.fr/registration. Empty = FR ingest disabled.
    legifrance_client_id: str = ""
    legifrance_client_secret: str = ""
    # law.go.kr DRF Open API (South Korea — app/ingestion/foreign.py KoreaLawGoKrClient).
    # Free "OC" id from https://open.law.go.kr signup (the registered email prefix); the calling
    # IP/domain must also be registered there. Empty = KR ingest disabled.
    lawgokr_oc: str = ""

    @field_validator(
        "anthropic_api_key",
        "legiscan_api_key",
        "sendgrid_api_key",
        "open_states_api_key",
        "stripe_secret_key",
        "stripe_pro_monthly_price_id",
        "stripe_pro_annual_price_id",
        "stripe_founding_coupon_id",
        "stripe_webhook_secret",
        mode="before",
    )
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v
    slack_webhook_url: str | None = None

    # Optional future API keys
    fmp_api_key: str = ""
    fred_api_key: str = ""
    comtrade_api_key: str = ""
    newsapi_key: str = ""
    # NREL incentives panel (state-profile Phase 2). Declared so a shared .env carrying
    # NREL_API_KEY doesn't trip extra='forbid' and crash the backend.
    nrel_api_key: str = ""

    # SEC EDGAR — user-agent required by SEC fair-use policy
    sec_user_agent: str = "SignalScout/1.0 contact@signalscout.io"

    # Phase 3 feature flags — gate external data source calls
    enable_epa_frs: bool = True
    enable_caa_registry: bool = True
    enable_sec_edgar: bool = True
    max_edgar_companies_per_run: int = 50

    # Open States ingestion — authoritative live source (LegiScan free tier is unusable, see below).
    enable_openstates_ingestion: bool = True
    max_openstates_calls_per_run: int = 5000
    # Free tier throttles aggressively — 1s spacing returns HTTP 429; ~6s ran clean in testing.
    openstates_request_delay_seconds: float = 6.0
    openstates_recent_window_days: int = 2

    # EUR-Lex / CELLAR — EU-central circular-economy law (region="EU"). When on, run_eurlex_cycle
    # weekly re-runs the SPARQL discovery and ingests newly-published in-force acts (only_new mode),
    # classifying them with the region-aware pipeline. Dormant by default; the one-time bulk backfill
    # is scripts/ingest_eurlex.py --bulk. Member-state national law (Spain RD 1055/2022, etc.) is a
    # separate per-country source — NOT covered here (CELLAR is EU-central only). See eu-integration.
    enable_eurlex_ingestion: bool = False
    # Restrict discovery to currently-valid acts (compliance focus). False = include repealed/historical.
    eurlex_in_force_only: bool = True
    # Bound the weekly cycle (only_new mode finds few, but cap a first/backfill run via the script's --max).
    max_eurlex_acts_per_run: int = 400

    # LegiScan — DORMANT. Free tier returns WV session-1 data for every state queried,
    # so all LegiScan rows were purged (alembic migration 004). Kept flag-gated in case a
    # paid API key is added later. Disabled until then.
    enable_legiscan_ingestion: bool = False
    max_legiscan_calls_per_run: int = 5000

    # Feature flags — keep False to avoid LLM costs during development
    enable_llm_classification: bool = False
    enable_sonnet_extraction: bool = False
    max_haiku_calls_per_run: int = 100
    max_sonnet_calls_per_run: int = 20

    # Scoring weights (must sum to 1.0)
    scoring_material_weight: float = 0.35
    scoring_geographic_weight: float = 0.35
    scoring_severity_weight: float = 0.30

    # Interpretation / exposure brief generation (Claude Sonnet)
    enable_interpretation: bool = False
    max_interpretation_calls_per_run: int = 10
    interpretation_brief_ttl_days: int = 7

    # CourtListener judicial monitoring
    courtlistener_api_token: str = ""
    courtlistener_base_url: str = "https://www.courtlistener.com/api/rest/v4"
    courtlistener_webhook_secret: str = ""
    enable_courtlistener: bool = False
    max_cl_cases_per_seed_run: int = 50
    # Spacing between successive CourtListener /search/ calls, to reduce how often the seed
    # sweep trips CL's strict search rate limit. Spacing alone can't fully avoid 429s (the
    # throttle window is long), so search_epr_cases also retries patiently on 429; this just
    # thins the burst.
    courtlistener_request_delay_seconds: float = 5.0

    # GCP project config (used to trigger Cloud Run Jobs)
    google_cloud_project: str = "ce-bill-tracker"
    cloud_run_region: str = "us-central1"

    # Scheduler intervals
    legiscan_poll_interval_hours: int = 24
    federal_register_poll_interval_hours: int = 6

    # Monthly subscriber digest. Dormant until previewed via scripts/send_digest.py and
    # explicitly enabled (DIGEST_ENABLED=true). When on, run_digest_cycle emails each active
    # subscriber a roundup of the prior month's movement on their topics + jurisdictions.
    enable_digest: bool = False
    digest_window_days: int = 30

    # Weekly digest — the habit-cadence half of the alert loop. Same builder/renderer as the monthly
    # digest, just a 7-day window on a weekly schedule. Independent flag so the predictable weekly
    # roundup can run without (or alongside) the monthly one. Dormant by default.
    enable_weekly_digest: bool = False
    weekly_digest_window_days: int = 7

    # Event-triggered deadline alerts — the loss-triggered half of the alert loop. When on,
    # run_deadline_alert_cycle emails subscribers when a compliance deadline they follow falls within
    # one of the reminder thresholds (days out), once per deadline (reminder_sent guards re-send).
    # Dormant by default; preview via scripts/send_deadline_alerts.py before enabling.
    enable_deadline_alerts: bool = False
    deadline_reminder_days: list[int] = [30, 7]

    # Event-triggered "new bill" alerts — the "something moved" trigger. When on,
    # run_new_bill_alert_cycle emails subscribers when a newly-tracked, relevant bill matches their
    # topics + jurisdictions, once per bill (new_bill_alert_sent guards re-send). Bounded to bills
    # created in the last new_bill_alert_window_days so flipping the flag can't blast a backfill.
    # Dormant by default; preview via scripts/send_new_bill_alerts.py before enabling.
    enable_new_bill_alerts: bool = False
    new_bill_alert_window_days: int = 7

    # Trial-ending reminder — the conversion nudge for no-card comp trials (7-day signup + 30-day
    # referral) that would otherwise lapse silently. When on, run_trial_reminder_cycle emails each
    # account whose comp grant expires within trial_reminder_lead_days, once per trial expiry
    # (trial_reminder_sent_for guards re-send; a re-granted/extended trial re-qualifies). Stripe's own
    # 90-day trial is card-on-file + auto-converts, so it's excluded. Dormant by default; preview via
    # scripts/send_trial_reminders.py before enabling.
    enable_trial_reminders: bool = False
    trial_reminder_lead_days: int = 2

    # One-time welcome email on signup. When on, create_subscription fires a best-effort background
    # send confirming the subscriber's scope + a cumulative "state of play" snapshot (enacted vs.
    # active bills across their topics + jurisdictions). Dormant by default; preview via
    # scripts/send_welcome.py before enabling. enable_welcome_recap separately gates the optional
    # one-paragraph LLM "championship recap" flourish (needs anthropic_api_key) — the email renders
    # fine without it, so the recap can stay off until its voice has been reviewed.
    enable_welcome_email: bool = True
    enable_welcome_recap: bool = True

    # Recurring watch-list recap: when an already-onboarded user adds more bills, run_watchlist_recap_cycle
    # batches a 30-min burst into one "you added N bills" email pointing to My Portfolio. Idempotent via
    # watchlist_recap_sent_at. Dormant by default; preview via scripts/send_watchlist_recap.py --dry-run
    # before enabling, so the new email's copy/cadence can be reviewed first.
    enable_watchlist_recap: bool = False

    # Source-link health audit — pings each bill's "View Source" URL and records the verdict
    # (source_url_status/_final/_checked_at) so the UI can fall back to a working link instead of
    # dropping the user on a connection error. When on, run_source_link_audit_cycle re-checks the
    # most-stale batch weekly. Bounded per run (link_audit_batch_size) so flipping it on can't fan
    # out across the whole table at once. Dormant by default; preview via
    # scripts/audit_bill_source_links.py --dry-run before enabling.
    enable_link_audit: bool = False
    link_audit_batch_size: int = 400

    # Full-text search index refresh (Layer B). When on, run_bill_text_refresh_cycle fetches text for
    # bills that have no bill_texts row yet or whose change_hash has moved since last indexed, and
    # upserts it (the generated tsvector + GIN index keep search current). Bounded per run
    # (bill_text_refresh_batch_size) so flipping it on can't fan out across the corpus / LegiScan
    # quota at once. Dormant by default; the one-time corpus load is scripts/backfill_bill_text.py.
    enable_bill_text_refresh: bool = False
    bill_text_refresh_batch_size: int = 200
    # By default the refresh cycle only fetches text for ce_relevant bills (what search / Sonnet /
    # the classifier actually use). Set true to sweep ALL bills with a fetchable source, including
    # currently out-of-scope ones — so reclassification can re-judge borderline drops on real text
    # rather than a bare title. Used for the one-time US corpus backfill (dev bill_texts was empty
    # for US — text was only ever fetched live at Sonnet time, never persisted).
    bill_text_refresh_all_bills: bool = False

    # Where "request access / pricing" lead notifications go. Each capture also auto-replies to the
    # requester. Both sends are best-effort and require sendgrid_api_key + a verified from-address.
    access_request_notify_email: str = "kenny@superfun.studio"

    # Stripe premium-seat billing + Firebase Auth. Dev reads sandbox keys from .env; prod pulls
    # STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET from Secret Manager (see cloudbuild --set-secrets).
    # See gating-and-monetization-plan.
    stripe_secret_key: str = ""
    # One self-serve Pro tier with two billing periods — monthly ($400/mo) and annual ($4,500/yr, the
    # cheaper-per-month option we nudge toward). The founding launch offer is applied at Checkout for
    # either period (see app/api/billing.py): the founding coupon (stripe_founding_coupon_id, "forever"
    # duration = 50% off for life) plus a 90-day free trial (card required). The founding *window* is
    # capped by the coupon's Stripe redeem-by date (closes Nov); once it lapses, checkout catches the
    # rejection and falls back to full price. The Bespoke column is a consulting inquiry, not a price.
    stripe_pro_monthly_price_id: str = ""
    stripe_pro_annual_price_id: str = ""
    stripe_founding_coupon_id: str = ""
    stripe_founding_trial_days: int = 90
    stripe_webhook_secret: str = ""
    # Non-secret, baked into the frontend build — not used server-side. Declared only so a shared
    # .env carrying STRIPE_PUBLISHABLE_KEY doesn't trip extra='forbid' and crash the backend.
    stripe_publishable_key: str = ""
    # Firebase project whose ID tokens we verify on premium routes (firebase-admin).
    firebase_project_id: str = "ce-bill-tracker"
    # Emails allowed into the hidden /admin console (manage sign-ups, grant complimentary Pro, …).
    # Compared case-insensitively against the verified Firebase email. Override in prod via the
    # ADMIN_EMAILS env var — accepts a comma-separated list ("a@x.com,b@y.com") or a JSON array.
    admin_emails: list[str] = ["kenny@superfun.studio"]

    @field_validator("admin_emails", mode="before")
    @classmethod
    def split_admin_emails(cls, v):
        # Accept a comma-separated string in addition to pydantic's default JSON-list parsing, so the
        # env var can be set the obvious way ("a@x.com, b@y.com") without JSON quoting.
        if isinstance(v, str) and not v.strip().startswith("["):
            return [e.strip() for e in v.split(",") if e.strip()]
        return v
    # Dashboard origin Stripe Checkout returns to (success/cancel) and that we allow for auth.
    app_base_url: str = "https://ce-bill-tracker.web.app"
    # Public origin of THIS API (Cloud Run), used to build absolute links into the backend from emails
    # — e.g. the one-click unsubscribe endpoint. The frontend is a static SPA, so it can't proxy these.
    api_base_url: str = "https://signalscout-api-pes3nxocda-uc.a.run.app"
    # HMAC key for signing one-click unsubscribe tokens. Falls back to stripe_webhook_secret (always set
    # in prod) when unset, so unsubscribe links work without provisioning a new secret. See
    # app/alerts/unsubscribe.py.
    unsubscribe_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
