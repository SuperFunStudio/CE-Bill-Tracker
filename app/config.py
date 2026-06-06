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

    @field_validator(
        "anthropic_api_key",
        "legiscan_api_key",
        "sendgrid_api_key",
        "open_states_api_key",
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

    # GCP project config (used to trigger Cloud Run Jobs)
    google_cloud_project: str = "ce-bill-tracker"
    cloud_run_region: str = "us-central1"

    # Scheduler intervals
    legiscan_poll_interval_hours: int = 24
    federal_register_poll_interval_hours: int = 6

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
