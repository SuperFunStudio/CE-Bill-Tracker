#!/usr/bin/env bash
# Create log-based metrics + alert policies for security/probing detection on the Atlas Circular API.
# Idempotent: skips metrics/policies that already exist. See docs/SECURITY_DETECTION.md.
#
# Prereqs:
#   - gcloud authed to the project (gcloud auth login)
#   - a notification channel id in $SEC_ALERT_CHANNEL (create one, see below), OR pass --channel
#
# Create a channel once:
#   gcloud beta monitoring channels create --project=ce-bill-tracker \
#     --display-name="Security alerts" --type=email \
#     --channel-labels=email_address=kenny@superfun.studio
#   export SEC_ALERT_CHANNEL="projects/ce-bill-tracker/notificationChannels/NNN"
#
# Usage: SEC_ALERT_CHANNEL=projects/.../NNN bash scripts/setup_security_alerts.sh
set -euo pipefail

PROJECT="${SEC_ALERT_PROJECT:-ce-bill-tracker}"
SERVICE="${SEC_ALERT_SERVICE:-signalscout-api}"
CHANNEL="${SEC_ALERT_CHANNEL:-}"
BASE="resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${SERVICE}\""

if [[ -z "$CHANNEL" ]]; then
  echo "ERROR: set SEC_ALERT_CHANNEL to a notification channel id (projects/${PROJECT}/notificationChannels/NNN)." >&2
  echo "See the header of this script for how to create one." >&2
  exit 1
fi

metric() {  # name  description  filter
  local name="$1" desc="$2" filter="$3"
  if gcloud logging metrics describe "$name" --project="$PROJECT" >/dev/null 2>&1; then
    echo "metric $name exists — updating filter"
    gcloud logging metrics update "$name" --project="$PROJECT" --log-filter="$filter" >/dev/null
  else
    echo "creating metric $name"
    gcloud logging metrics create "$name" --project="$PROJECT" --description="$desc" --log-filter="$filter" >/dev/null
  fi
}

metric sec_ratelimit_429   "Rate-limit 429 responses"               "$BASE jsonPayload.message=\"http_request\" jsonPayload.status=429"
metric sec_server_errors   "5xx server errors"                      "$BASE jsonPayload.message=\"http_request\" jsonPayload.status>=500"
metric sec_client_errors   "4xx client errors (enumeration signal)" "$BASE jsonPayload.message=\"http_request\" jsonPayload.status>=400 jsonPayload.status<500"
metric sec_auth_failures   "Invalid Firebase tokens"                "$BASE jsonPayload.message=\"firebase_token_invalid\""
metric sec_webhook_forgery "Bad webhook signatures"                 "$BASE (jsonPayload.message=\"stripe_webhook_bad_signature\" OR jsonPayload.message=\"cl_webhook_invalid_signature\")"
metric sec_sensitive_probe "Anon hits on /pipeline or /admin"       "$BASE jsonPayload.message=\"http_request\" jsonPayload.path=~\"^/(pipeline|admin)\" (jsonPayload.status=401 OR jsonPayload.status=403)"

# policy  metric-name  display  threshold-per-5min
policy() {
  local mname="$1" display="$2" threshold="$3"
  if gcloud alpha monitoring policies list --project="$PROJECT" --filter="displayName=\"$display\"" --format="value(name)" 2>/dev/null | grep -q .; then
    echo "policy '$display' exists — skipping"
    return
  fi
  echo "creating policy '$display' (threshold $threshold / 5min)"
  local tmp; tmp="$(mktemp)"
  cat > "$tmp" <<JSON
{
  "displayName": "$display",
  "combiner": "OR",
  "conditions": [{
    "displayName": "$display",
    "conditionThreshold": {
      "filter": "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/$mname\"",
      "comparison": "COMPARISON_GT",
      "thresholdValue": $threshold,
      "duration": "0s",
      "trigger": {"count": 1},
      "aggregations": [{"alignmentPeriod": "300s", "perSeriesAligner": "ALIGN_SUM"}]
    }
  }],
  "alertStrategy": {"autoClose": "3600s"},
  "notificationChannels": ["$CHANNEL"]
}
JSON
  gcloud alpha monitoring policies create --project="$PROJECT" --policy-from-file="$tmp" >/dev/null
  rm -f "$tmp"
}

policy sec_webhook_forgery "SEC: webhook forgery attempt"       0
policy sec_sensitive_probe "SEC: anon probe on /pipeline|/admin" 0
policy sec_ratelimit_429   "SEC: rate-limit flood"              50
policy sec_auth_failures   "SEC: credential spraying"           30
policy sec_client_errors   "SEC: enumeration / scanning"       200
policy sec_server_errors   "SEC: server-error spike"            20

echo "Done. Review policies at: https://console.cloud.google.com/monitoring/alerting/policies?project=$PROJECT"
