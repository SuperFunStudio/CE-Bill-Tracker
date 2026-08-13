from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:dev@localhost:5432/signalscout"
    test_database_url: str = "postgresql://postgres:dev@localhost:5432/signalscout_test"

    # API Keys
    legiscan_api_key: str = ""
    open_states_api_key: str = ""
    anthropic_api_key: str = ""
    # ── Email ───────────────────────────────────────────────────────────────
    # Which transport puts mail on the wire: "sendgrid" or "postmark". Both are implemented and both
    # sets of credentials can be present at once, because which provider we're on is an operational
    # question (whose account is approved this week), not an architectural one — SendGrid approved
    # the account first, so it is the default; Postmark stays wired so the switch back is this one
    # variable rather than a rewrite.
    #
    # None means "pick whichever key is present" (see _resolve_email_provider), so an environment
    # carrying exactly one provider's key can't send its mail into a provider that has none.
    email_provider: str | None = None
    # The Postmark SERVER API token (Servers → <server> → API Tokens), NOT the account token and NOT
    # the server ID. Every send path gates on `email_configured` below, so an empty key disables the
    # email channel rather than failing sends.
    postmark_api_key: str = ""
    # Not used by the send API — declared only so a .env carrying POSTMARK_SERVER_ID doesn't trip
    # extra='forbid'. Useful when calling the account-level API (servers, bounce streams).
    postmark_server_id: str = ""
    # Postmark refuses to mix transactional and bulk traffic on one stream, and it's the mechanism
    # that keeps a digest opt-out from suppressing password-reset mail. Transactional sends use
    # `postmark_message_stream`; anything carrying a one-click unsubscribe URL (digest, new-bill
    # alerts, watchlist recap, consolidated bill alerts) is bulk and goes out on the broadcast
    # stream. Both streams must exist on the server — the IDs here are Postmark's defaults.
    postmark_message_stream: str = "outbound"
    postmark_broadcast_stream: str = "broadcast"
    # The SendGrid API key (Settings → API Keys, "Mail Send" permission is enough). Live again as of
    # 2026-08-13: SendGrid approved the sending account while Postmark's review is still pending.
    # The other three names are also the fallback source for the email_* identities below — see
    # _inherit_legacy_email_env — so an environment that only ever set SENDGRID_FROM_EMAIL still
    # resolves a From address.
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""
    sendgrid_reply_to: str = ""
    sendgrid_hello_email: str = ""
    # The sending identity. ONE address for everything — a second local-part means a second
    # reputation to warm for no gain at this volume. Falls back to SENDGRID_FROM_EMAIL (see
    # _inherit_legacy_email_env) so the old prod secret keeps working through the Postmark cutover.
    # The domain must be authenticated at whichever provider is active — SendGrid Sender
    # Authentication, or Postmark Sender Signatures → Domains — since only a DOMAIN authorises every
    # local-part; a single verified sender signature would authorise this one address and nothing
    # else. The two providers publish DIFFERENT DKIM/Return-Path records, so both sets have to be
    # live in DNS for the provider switch to be a switch rather than an outage.
    # None means "unset": the validator below fills it. Never None after construction.
    email_from: str | None = None
    # Where replies go. The From stays alerts@ — that's the warmed, domain-authenticated identity and
    # moving bulk sends to a new local-part would throw that reputation away — but four templates end
    # with "or reply to this email" (the cancellation one explicitly asks for churn feedback), and
    # without this those replies land in a send-only mailbox nobody reads. Same authenticated domain,
    # so no extra DNS. Set to "" to send with no Reply-To.
    email_reply_to: str | None = None
    # The founder-voice identity, passed explicitly as `from_email=` by the handful of templates that
    # speak as a person (welcome, cancellation) — never the default. It is the SAME ADDRESS as
    # email_from by default: what differs is the display name, not the mailbox, so there's one
    # reputation and one inbox thread rather than two. Set it to a different address only if you
    # actually want a second identity to warm.
    email_hello_from: str | None = None
    # The display names the inbox shows. Kept here, not in the provider's sender-signature UI, so
    # they're version-controlled and can differ per voice even on one address.
    #
    # The automated cycles send as the brand: a subscriber who signed up for Atlas Circular and gets
    # mail from an unfamiliar first name is being invited to mark it as spam, and recognition only
    # compounds if the name never varies. The founder voice keeps a person's name, because the
    # templates carrying it ask for a reply and a brand name doesn't get one.
    # Changing these churns that recognition, so pick once and leave them.
    email_from_name: str = "Atlas Circular"
    email_hello_from_name: str = "Kenny at Atlas Circular"
    # Link tracking rewrites every href to the provider's click host. On SendGrid that host
    # (url7082.atlascircular.com) served a certificate that didn't cover it, so every link in every
    # email dead-ended on a browser "connection is not private" interstitial — which is why this is
    # OFF, and it is SendGrid we are back on. Re-enable only after clicking a real link end-to-end
    # (SendGrid: Sender Authentication → Link Branding → validate SSL). Off = hrefs go out verbatim,
    # no rewrite, no interstitial, no click stats.
    email_click_tracking: bool = False

    @model_validator(mode="after")
    def _inherit_legacy_email_env(self):
        """Resolve the sending identities, preferring EMAIL_* and falling back to the SendGrid names.

        Done here rather than with a validation alias because both spellings can be present at once
        (prod injects SENDGRID_FROM_EMAIL from Secret Manager; a developer's .env may set either),
        and an alias consumes only one of them — leaving the other as an undeclared env var, which
        extra='forbid' turns into a boot crash. Empty string is a meaningful value for the reply
        address ("send with no Reply-To"), so None is what "unset" means here.
        """
        if self.email_from is None:
            self.email_from = self.sendgrid_from_email or "hello@atlascircular.com"
        if self.email_reply_to is None:
            self.email_reply_to = self.sendgrid_reply_to or "kenny@atlascircular.com"
        # Defaults to email_from, not to a literal: one address unless someone deliberately splits.
        if self.email_hello_from is None:
            self.email_hello_from = self.sendgrid_hello_email or self.email_from
        return self

    @model_validator(mode="after")
    def _resolve_email_provider(self):
        """Settle on one transport, so nothing downstream has to ask "which provider?" twice.

        An explicit EMAIL_PROVIDER always wins — that's the deliberate choice, including the case
        where both keys are present and one account is the one that's approved. With nothing set,
        the provider that HAS a key wins, because the alternative is an environment holding exactly
        one working credential and silently sending nothing through the other. SendGrid breaks the
        tie when both or neither are set: it is the approved account today.
        """
        if self.email_provider:
            self.email_provider = self.email_provider.strip().lower()
            if self.email_provider not in ("sendgrid", "postmark"):
                raise ValueError(
                    f"email_provider must be 'sendgrid' or 'postmark', got {self.email_provider!r}"
                )
        elif self.postmark_api_key and not self.sendgrid_api_key:
            self.email_provider = "postmark"
        else:
            self.email_provider = "sendgrid"
        return self

    @property
    def email_api_key(self) -> str:
        """The credential for whichever transport is active. Deliberately NOT a fallback to the other
        provider's key: a key belongs to one API, and reaching for the wrong one turns a
        misconfiguration into a wall of 401s instead of the clean "email is off" that
        `email_configured` gives every caller."""
        return self.postmark_api_key if self.email_provider == "postmark" else self.sendgrid_api_key

    @property
    def email_configured(self) -> bool:
        """Whether the email channel can send. Every caller gates on this instead of poking at a
        provider-specific key, so swapping providers doesn't mean touching thirty call sites."""
        return bool(self.email_api_key)
    # Légifrance API via PISTE (France national law — app/ingestion/foreign.py LegifranceClient).
    # Free OAuth2 client-credentials from https://piste.gouv.fr/registration. Empty = FR ingest disabled.
    legifrance_client_id: str = ""
    legifrance_client_secret: str = ""
    # law.go.kr DRF Open API (South Korea — app/ingestion/foreign.py KoreaLawGoKrClient).
    # Free "OC" id from https://open.law.go.kr signup (the registered email prefix); the calling
    # IP/domain must also be registered there. Empty = KR ingest disabled.
    lawgokr_oc: str = ""
    # Laws.Africa Indigo Content API (pan-African — app/ingestion/foreign.py LawsAfrica* clients).
    # Free token from https://platform.laws.africa/api-keys/ (sandbox: 100 calls/day, 1 country).
    # NOTE: commons content is CC-BY-NC-SA — clear commercial licensing before full-text ingest.
    # Empty = Africa ingest disabled.
    lawsafrica_token: str = ""
    # NYS Open Legislation API (New York state bills — app/ingestion/nysenate.py NYSenateClient).
    # Free key from https://legislation.nysenate.gov/ (sign up, then confirm via the activation
    # email — the key is rejected with errorCode 701 until confirmed). NY bills' source_url already
    # points at this API, so without a key the source_url rung of the bill-text ladder fails for NY.
    # Empty = NY-direct fetch disabled (ladder falls back to LegiScan/OpenStates as before).
    nys_api_key: str = ""

    # The physical mailing address printed in every email footer. CAN-SPAM §7704(a)(5) requires a
    # valid postal address on commercial mail, and SendGrid enforces it at account review — mail sent
    # without one is what gets a sending account suspended, not just filtered. Deliberately env-only
    # with an empty default so the address isn't in git; set BUSINESS_ADDRESS in .env locally and in
    # the Cloud Run service env in prod. Newlines or " | " separate lines; the footer joins them.
    # Empty = the address line is omitted (renders, doesn't crash) — so a missing env var degrades to
    # a non-compliant footer rather than a failed send. Check it after any deploy that resets env.
    business_address: str = ""

    @field_validator(
        "anthropic_api_key",
        "legiscan_api_key",
        "postmark_api_key",
        "sendgrid_api_key",
        "open_states_api_key",
        "nys_api_key",
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
    # Legacy/stray .env key — the live Africa client reads `lawsafrica_token` (above), not this.
    # Declared for the same reason as nrel_api_key: a shared .env carrying AFRICA_LAWS_API_KEY must
    # not trip extra='forbid' and crash boot.
    africa_laws_api_key: str = ""

    # SEC EDGAR — user-agent required by SEC fair-use policy
    sec_user_agent: str = "AtlasCircular/1.0 contact@atlascircular.com"

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
    # CourtListener's binding limit is 50 requests/HOUR (the 5/min throttle is the burst guard on
    # top of it). Screening a case for relevance costs 4 calls — docket, parties, entries, and the
    # complaint text — so a run that ingests more than ~12 new cases exhausts the hour and every
    # case after that comes back unreadable. Unreadable means "held for review", not "alerted on",
    # so blowing the quota is not dangerous; it just wastes a week's poll. Cap the run instead and
    # let the remainder arrive next cycle.
    max_cl_cases_per_poll: int = 10
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

    # Account-security emails (verify address / reset password) sent through OUR SendGrid identity
    # instead of Firebase's own `noreply@<project>.firebaseapp.com` mailer, so they inherit the
    # brand-aligned, SPF/DKIM-authenticated domain the rest of our mail uses. Deliberately separate
    # from enable_welcome_email: that flag gates marketing-ish lifecycle mail, and turning it off
    # must never take account verification with it. Turning THIS off is safe — the frontend falls
    # back to the Firebase client SDK's send. See app/alerts/auth_emails.py.
    enable_auth_emails: bool = True

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
    # requester. Both sends are best-effort and require email_configured + a verified from-address.
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
    # Atlas Circular membership tiers below Pro.
    # Student is pay-what-you-wish MONTHLY — but Stripe's "customer chooses price" (custom_unit_amount)
    # only works for one-off prices, NOT subscriptions. So we don't use a fixed Price: our UI collects
    # the amount and we mint the monthly price at checkout via `price_data` against this PRODUCT id
    # (prod_…). $0 grants a free comp membership without touching Stripe. Gated to verified educational
    # emails (edu_email_suffixes). The webhook maps this product → the "student" plan.
    stripe_student_product_id: str = ""
    # Research (Founding Supporter) — monthly ($30/mo) or annual ($240/yr, the discounted option we
    # nudge toward), mirroring Pro's two-period model. Both stamp the "research" plan via the webhook.
    stripe_research_monthly_price_id: str = ""
    stripe_research_annual_price_id: str = ""
    stripe_webhook_secret: str = ""
    # Non-secret, baked into the frontend build — not used server-side. Declared only so a shared
    # .env carrying STRIPE_PUBLISHABLE_KEY doesn't trip extra='forbid' and crash the backend.
    stripe_publishable_key: str = ""
    # Email suffixes that qualify for the edu-gated Student tier. Checked (case-insensitive, endswith)
    # against the caller's VERIFIED Firebase email at Student checkout. Override via EDU_EMAIL_SUFFIXES
    # (comma-separated or JSON array) to add institutions without a code change.
    edu_email_suffixes: list[str] = [
        ".edu", ".ac.uk", ".edu.au", ".ac.nz", ".edu.ca", ".ac.jp", ".edu.sg", ".ac.za", ".edu.mx",
    ]

    @field_validator("edu_email_suffixes", mode="before")
    @classmethod
    def split_edu_suffixes(cls, v):
        if isinstance(v, str) and not v.strip().startswith("["):
            return [s.strip().lower() for s in v.split(",") if s.strip()]
        return v

    # Firebase project whose ID tokens we verify on premium routes (firebase-admin).
    firebase_project_id: str = "ce-bill-tracker"
    # Emails allowed into the hidden /admin console (manage sign-ups, grant complimentary Pro, …).
    # Compared case-insensitively against the verified Firebase email. Override in prod via the
    # ADMIN_EMAILS env var — accepts a comma-separated list ("a@x.com,b@y.com") or a JSON array.
    admin_emails: list[str] = ["kenny@superfun.studio"]

    # Our own accounts. They hold complimentary Pro so the paid product can be exercised end-to-end,
    # which means they look exactly like a real comped grant to any query that counts seats — four of
    # them were silently consuming founding seats and showing the public pricing page a lower
    # "remaining" than the truth. Excluded from /billing/founding-seats; deliberately NOT excluded from
    # the comp that grants them access, since the whole point is that they can use the product. Keep
    # this to accounts that are genuinely ours: it moves a number a visitor reads.
    internal_emails: list[str] = [
        "superfuntester@gmail.com",
        "kenny.m.arnold@gmail.com",
        "curiouskenneth@gmail.com",
        "found@thriftspot.app",
    ]

    @field_validator("admin_emails", "internal_emails", mode="before")
    @classmethod
    def split_admin_emails(cls, v):
        # Accept a comma-separated string in addition to pydantic's default JSON-list parsing, so the
        # env var can be set the obvious way ("a@x.com, b@y.com") without JSON quoting.
        if isinstance(v, str) and not v.strip().startswith("["):
            return [e.strip() for e in v.split(",") if e.strip()]
        return v
    # Dashboard origin Stripe Checkout returns to (success/cancel + billing-portal return). The Atlas
    # Circular public domain; override via APP_BASE_URL per environment (e.g. the dev Firebase site).
    app_base_url: str = "https://www.atlascircular.com"
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
