<#
Create log-based metrics + alert policies for security/probing detection on the Atlas Circular API.
PowerShell (Windows PowerShell 5.1 compatible). Idempotent. See docs/SECURITY_DETECTION.md.

Prereqs:
  - gcloud authed to the project (gcloud auth login)
  - a notification channel id (create one, see below)

Create a channel once (returns projects/ce-bill-tracker/notificationChannels/NNN):
  gcloud beta monitoring channels create --project=ce-bill-tracker `
    --display-name="Security alerts" --type=email `
    --channel-labels=email_address=kenny@superfun.studio

Then run:
  .\scripts\setup_security_alerts.ps1 -Channel "projects/ce-bill-tracker/notificationChannels/NNN"
#>
param(
  [string]$Channel = $env:SEC_ALERT_CHANNEL,
  [string]$Project = "ce-bill-tracker",
  [string]$Service = "signalscout-api"
)

# NOTE: do NOT set $ErrorActionPreference = "Stop" here. In Windows PowerShell 5.1 a native command
# (gcloud) writing to stderr is wrapped as a terminating NativeCommandError under Stop mode — which
# would abort on gcloud's benign "not found" probes. We check exit codes explicitly instead.

if (-not $Channel -or $Channel -match 'notificationChannels/NNN$') {
  Write-Error "Set -Channel (or `$env:SEC_ALERT_CHANNEL) to a REAL notification channel id (projects/$Project/notificationChannels/<number>), not the NNN placeholder. See this script's header for how to create one."
  exit 1
}

$base = 'resource.type="cloud_run_revision" resource.labels.service_name="' + $Service + '"'
$tmp = Join-Path $env:TEMP "sec_alerts"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

# --- log-based metrics (config written to file so no PowerShell quoting of the filter is needed) ---
# Fetch existing metric names ONCE so we never call `describe` (which errors-by-design when absent).
$existingMetrics = gcloud logging metrics list --project=$Project --format='value(name)' 2>$null

function Set-Metric {
  param([string]$Name, [string]$Desc, [string]$Filter)
  $file = Join-Path $tmp "$Name.yaml"
  # LogMetric config. Filter is single-quoted for YAML (our filters contain " but no '), so it's literal.
  $yaml = "name: $Name`ndescription: `"$Desc`"`nfilter: '$Filter'`n"
  # ASCII, no BOM — gcloud's YAML parser dislikes a UTF-8 BOM.
  [System.IO.File]::WriteAllText($file, $yaml, [System.Text.Encoding]::ASCII)

  if ($existingMetrics -contains $Name) {
    Write-Host "updating metric $Name"
    gcloud logging metrics update $Name --config-from-file=$file --project=$Project | Out-Null
  } else {
    Write-Host "creating metric $Name"
    gcloud logging metrics create $Name --config-from-file=$file --project=$Project | Out-Null
  }
  if ($LASTEXITCODE -ne 0) { Write-Warning "metric $Name : gcloud exited $LASTEXITCODE" }
}

Set-Metric "sec_ratelimit_429"   "Rate-limit 429 responses"               "$base jsonPayload.message=""http_request"" jsonPayload.status=429"
Set-Metric "sec_server_errors"   "5xx server errors"                      "$base jsonPayload.message=""http_request"" jsonPayload.status>=500"
Set-Metric "sec_client_errors"   "4xx client errors (enumeration signal)" "$base jsonPayload.message=""http_request"" jsonPayload.status>=400 jsonPayload.status<500"
Set-Metric "sec_auth_failures"   "Invalid Firebase tokens"                "$base jsonPayload.message=""firebase_token_invalid"""
Set-Metric "sec_webhook_forgery" "Bad webhook signatures"                 "$base (jsonPayload.message=""stripe_webhook_bad_signature"" OR jsonPayload.message=""cl_webhook_invalid_signature"")"
Set-Metric "sec_sensitive_probe" "Anon hits on /pipeline or /admin"       "$base jsonPayload.message=""http_request"" jsonPayload.path=~""^/(pipeline|admin)"" (jsonPayload.status=401 OR jsonPayload.status=403)"

# --- alert policies (JSON written to file, applied with --policy-from-file) ---
# NOTE: monitoring *policies* live only under the `alpha` track (unlike `channels`, which is in `beta`).
$existingPolicies = gcloud alpha monitoring policies list --project=$Project --format='value(displayName)' 2>$null

function Set-Policy {
  param([string]$Metric, [string]$Display, [int]$Threshold)
  if ($existingPolicies -contains $Display) {
    Write-Host "policy '$Display' exists - skipping"
    return
  }
  Write-Host "creating policy '$Display' (threshold $Threshold / 5min)"
  $file = Join-Path $tmp ($Metric + "_policy.json")
  $policy = @{
    displayName = $Display
    combiner    = "OR"
    conditions  = @(@{
      displayName        = $Display
      conditionThreshold = @{
        filter         = 'resource.type="cloud_run_revision" AND metric.type="logging.googleapis.com/user/' + $Metric + '"'
        comparison     = "COMPARISON_GT"
        thresholdValue = $Threshold
        duration       = "0s"
        trigger        = @{ count = 1 }
        aggregations   = @(@{ alignmentPeriod = "300s"; perSeriesAligner = "ALIGN_SUM" })
      }
    })
    alertStrategy        = @{ autoClose = "3600s" }
    notificationChannels = @($Channel)
  }
  $json = $policy | ConvertTo-Json -Depth 10
  [System.IO.File]::WriteAllText($file, $json, [System.Text.Encoding]::ASCII)
  gcloud alpha monitoring policies create --project=$Project --policy-from-file=$file | Out-Null
  if ($LASTEXITCODE -ne 0) { Write-Warning "policy '$Display' : gcloud exited $LASTEXITCODE" }
}

Set-Policy "sec_webhook_forgery" "SEC: webhook forgery attempt"        0
Set-Policy "sec_sensitive_probe" "SEC: anon probe on /pipeline|/admin" 0
Set-Policy "sec_ratelimit_429"   "SEC: rate-limit flood"               50
Set-Policy "sec_auth_failures"   "SEC: credential spraying"            30
Set-Policy "sec_client_errors"   "SEC: enumeration / scanning"         200
Set-Policy "sec_server_errors"   "SEC: server-error spike"             20

Write-Host ""
Write-Host "Done. Review policies at: https://console.cloud.google.com/monitoring/alerting/policies?project=$Project"
