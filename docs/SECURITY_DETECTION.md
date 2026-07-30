# Security detection — probing & abuse telemetry

How to tell if bad actors are poking at the Atlas Circular website/APIs. This covers (1) the app-level
telemetry that now exists, (2) queries to run for on-demand triage, and (3) log-based alert policies so
GCP pages you automatically. Companion to `docs/SECURITY_ASSESSMENT.md` (which flagged detection/alerting
as the open operational gap).

Project: `ce-bill-tracker` · Cloud Run service: `signalscout-api` · region: `us-central1`.

---

## 1. What the app now emits

As of the request-logging change, the API writes **one structured JSON line per request** to stdout,
which Cloud Run forwards to Cloud Logging as `jsonPayload`. Relevant fields:

| field | meaning |
|-------|---------|
| `message` | `"http_request"` for the access log; also carries named events like `firebase_token_invalid`, `stripe_webhook_bad_signature` |
| `status` | HTTP status code |
| `path` | request path (e.g. `/.env`, `/pipeline/reset`) |
| `query` | query string, truncated to 200 chars (SQLi/XSS payloads show here) |
| `client_ip` | spoof-resistant client IP (X-Forwarded-For read from the right) |
| `user_agent` | request UA (`sqlmap`, `nikto`, empty UA = suspicious) |
| `severity` | `WARNING` for 429s and 5xx, else `INFO` |
| `request_id` | correlates the access line with any event a handler logged mid-request |

`configure_logging()` (app/utils/logging_config.py) is now called at boot, so these land as queryable
`jsonPayload` fields — not unstructured text. On Cloud Run it auto-selects JSON; locally it renders the
human console format. Override with `LOG_FORMAT=json|console`.

---

## 2. On-demand triage — Logs Explorer queries

Paste into GCP Console → Logging → Logs Explorer. All assume the service filter:

```
resource.type="cloud_run_revision" resource.labels.service_name="signalscout-api"
```

**Endpoint enumeration / path fuzzing** (bursts of 404/403):
```
jsonPayload.message="http_request" jsonPayload.status>=400 jsonPayload.status<500
```
Then group by `jsonPayload.client_ip` — one IP generating many = a scanner.

**Scanner tooling by user-agent:**
```
jsonPayload.message="http_request" (jsonPayload.user_agent=~"(?i)(sqlmap|nikto|nmap|masscan|dirbuster|gobuster|python-requests|curl)" OR jsonPayload.user_agent="")
```

**SQLi / XSS attempts in query strings:**
```
jsonPayload.message="http_request" jsonPayload.query=~"(?i)(union select|or 1=1|<script|onerror=|\.\./|/etc/passwd|%27)"
```

**Probing sensitive endpoints anonymously** (401/403 = someone hit an admin/pipeline route with no token):
```
jsonPayload.message="http_request" jsonPayload.path=~"^/(pipeline|admin)" (jsonPayload.status=401 OR jsonPayload.status=403)
```

**Rate-limit floods:**
```
jsonPayload.message="http_request" jsonPayload.status=429
```

**Credential probing / bad tokens:**
```
jsonPayload.message="firebase_token_invalid"
```

**Webhook forgery attempts:**
```
jsonPayload.message="stripe_webhook_bad_signature" OR jsonPayload.message="cl_webhook_invalid_signature"
```

---

## 3. Automated alerting (log-based metrics + policies)

One-time setup so GCP alerts you instead of you having to look. Run `scripts/setup_security_alerts.sh`
(idempotent; needs `gcloud` authed to `ce-bill-tracker`), or run the commands below by hand.

### 3a. Create a notification channel (once)

```
gcloud beta monitoring channels create --project=ce-bill-tracker --display-name="Security alerts" --type=email --channel-labels=email_address=kenny@superfun.studio
```
Grab the returned channel id (`projects/ce-bill-tracker/notificationChannels/NNN`) — the script reads it
from `$SEC_ALERT_CHANNEL`, or pass it to each policy below.

### 3b. Log-based metrics

Counter metrics over the same filters as §2. Single-line, paste-safe:

```
gcloud logging metrics create sec_ratelimit_429 --project=ce-bill-tracker --description="Rate-limit 429 responses" --log-filter="resource.type=\"cloud_run_revision\" resource.labels.service_name=\"signalscout-api\" jsonPayload.message=\"http_request\" jsonPayload.status=429"
```
```
gcloud logging metrics create sec_server_errors --project=ce-bill-tracker --description="5xx server errors" --log-filter="resource.type=\"cloud_run_revision\" resource.labels.service_name=\"signalscout-api\" jsonPayload.message=\"http_request\" jsonPayload.status>=500"
```
```
gcloud logging metrics create sec_client_errors --project=ce-bill-tracker --description="4xx client errors (enumeration signal)" --log-filter="resource.type=\"cloud_run_revision\" resource.labels.service_name=\"signalscout-api\" jsonPayload.message=\"http_request\" jsonPayload.status>=400 jsonPayload.status<500"
```
```
gcloud logging metrics create sec_auth_failures --project=ce-bill-tracker --description="Invalid Firebase tokens" --log-filter="resource.type=\"cloud_run_revision\" resource.labels.service_name=\"signalscout-api\" jsonPayload.message=\"firebase_token_invalid\""
```
```
gcloud logging metrics create sec_webhook_forgery --project=ce-bill-tracker --description="Bad webhook signatures" --log-filter="resource.type=\"cloud_run_revision\" resource.labels.service_name=\"signalscout-api\" (jsonPayload.message=\"stripe_webhook_bad_signature\" OR jsonPayload.message=\"cl_webhook_invalid_signature\")"
```
```
gcloud logging metrics create sec_sensitive_probe --project=ce-bill-tracker --description="Anon hits on /pipeline or /admin" --log-filter="resource.type=\"cloud_run_revision\" resource.labels.service_name=\"signalscout-api\" jsonPayload.message=\"http_request\" jsonPayload.path=~\"^/(pipeline|admin)\" (jsonPayload.status=401 OR jsonPayload.status=403)"
```

### 3c. Alert policies

Alert policies over log metrics fire when the metric crosses a threshold in a rolling window. The
`scripts/setup_security_alerts.sh` script builds these from JSON (thresholds parameterized). Suggested
starting thresholds (tune after a week of baseline):

| metric | condition | rationale |
|--------|-----------|-----------|
| `sec_webhook_forgery` | **any** > 0 in 5 min | should never be non-zero; forged webhooks = attack |
| `sec_sensitive_probe` | > 0 in 5 min | nobody should hit /pipeline or /admin unauth'd |
| `sec_ratelimit_429` | > 50 in 5 min | someone is hammering past the limiter |
| `sec_auth_failures` | > 30 in 5 min | credential spraying |
| `sec_client_errors` | > 200 in 5 min | broad enumeration/scanning |
| `sec_server_errors` | > 20 in 5 min | attack triggering errors, or breakage |

> **Per-IP grouping (advanced):** the aggregate 4xx alert catches a broad sweep but not a single slow
> scanner. To alert per-IP, recreate `sec_client_errors` with a `client_ip` label extractor
> (`--config-from-file` with `labelExtractors: {client_ip: 'EXTRACT(jsonPayload.client_ip)'}`) and set
> the alert's `aggregations.groupByFields` to that label so each IP is its own time series.

---

## 4. Next layer — Cloud Armor (edge detection & blocking)

Everything above is *detection* on an app that's directly `--allow-unauthenticated`. To **detect and
block at the edge**, put an external HTTPS load balancer + Cloud Armor in front of Cloud Run:
preconfigured WAF rules (SQLi/XSS/scanner signatures), per-IP rate rules, geo/IP allow-deny, and
Adaptive Protection (ML volumetric-anomaly detection). This is the open `M-4` item in the security
assessment and the durable answer to blocking bad actors before they reach the app.
