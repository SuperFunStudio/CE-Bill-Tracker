# SignalScout GCP Bootstrap Script (PowerShell)
# Run from the SignalScout project root:
#   cd C:\Users\kenny\SignalScout
#   .\scripts\bootstrap_gcp.ps1

$PROJECT_ID = "ce-bill-tracker"
$REGION = "us-central1"
$SQL_INSTANCE = "signalscout-db"
$SQL_DB = "signalscout"
$SQL_USER = "signalscout"

# ── Prompt for DB password once ──────────────────────────────────────────────
$DB_PASSWORD = Read-Host "Enter a secure password for the Cloud SQL user" -AsSecureString
$DB_PASSWORD_PLAIN = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DB_PASSWORD)
)

Write-Host "`n=== Setting gcloud project ===" -ForegroundColor Cyan
gcloud config set project $PROJECT_ID

# ── Enable APIs ───────────────────────────────────────────────────────────────
Write-Host "`n=== Enabling GCP APIs ===" -ForegroundColor Cyan
gcloud services enable `
    run.googleapis.com `
    sqladmin.googleapis.com `
    cloudbuild.googleapis.com `
    secretmanager.googleapis.com `
    artifactregistry.googleapis.com

# ── Artifact Registry ─────────────────────────────────────────────────────────
Write-Host "`n=== Creating Artifact Registry repo ===" -ForegroundColor Cyan
gcloud artifacts repositories create signalscout-images `
    --repository-format=docker `
    --location=$REGION `
    --description="SignalScout container images"

# ── Cloud SQL ─────────────────────────────────────────────────────────────────
Write-Host "`n=== Creating Cloud SQL instance (this takes ~5 min) ===" -ForegroundColor Cyan
gcloud sql instances create $SQL_INSTANCE `
    --database-version=POSTGRES_15 `
    --tier=db-f1-micro `
    --region=$REGION

Write-Host "`n=== Creating database and user ===" -ForegroundColor Cyan
gcloud sql databases create $SQL_DB --instance=$SQL_INSTANCE
gcloud sql users create $SQL_USER --instance=$SQL_INSTANCE --password=$DB_PASSWORD_PLAIN

# ── Service Accounts ──────────────────────────────────────────────────────────
Write-Host "`n=== Creating service accounts ===" -ForegroundColor Cyan
gcloud iam service-accounts create signalscout-api --display-name="SignalScout API"
gcloud iam service-accounts create signalscout-dashboard --display-name="SignalScout Dashboard"

$API_SA = "signalscout-api@${PROJECT_ID}.iam.gserviceaccount.com"

Write-Host "`n=== Granting API service account roles ===" -ForegroundColor Cyan
gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member="serviceAccount:$API_SA" `
    --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member="serviceAccount:$API_SA" `
    --role="roles/secretmanager.secretAccessor"

# ── Cloud Build SA roles ───────────────────────────────────────────────────────
Write-Host "`n=== Granting Cloud Build service account roles ===" -ForegroundColor Cyan
$PROJECT_NUMBER = gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
$BUILD_SA = "${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

foreach ($role in @(
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor",
    "roles/run.admin",
    "roles/iam.serviceAccountUser"
)) {
    Write-Host "  Granting $role to Cloud Build SA..."
    gcloud projects add-iam-policy-binding $PROJECT_ID `
        --member="serviceAccount:$BUILD_SA" `
        --role=$role
}

# ── Secret Manager ────────────────────────────────────────────────────────────
Write-Host "`n=== Loading secrets from .env into Secret Manager ===" -ForegroundColor Cyan

# Read values from .env
$envFile = Get-Content .env | Where-Object { $_ -match "=" -and $_ -notmatch "^#" }
$envVars = @{}
foreach ($line in $envFile) {
    $parts = $line -split "=", 2
    if ($parts.Count -eq 2) {
        $envVars[$parts[0].Trim()] = $parts[1].Trim()
    }
}

# DATABASE_URL for Cloud Run uses Unix socket form
$SOCKET_DB_URL = "postgresql://${SQL_USER}:${DB_PASSWORD_PLAIN}@/${SQL_DB}?host=/cloudsql/${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"

$secrets = @{
    "SIGNALSCOUT_DATABASE_URL"    = $SOCKET_DB_URL
    "SIGNALSCOUT_DB_PASSWORD"     = $DB_PASSWORD_PLAIN
    "LEGISCAN_API_KEY"            = $envVars["LEGISCAN_API_KEY"]
    "OPEN_STATES_API_KEY"         = $envVars["OPEN_STATES_API_KEY"].Trim()
    "ANTHROPIC_API_KEY"           = $envVars["ANTHROPIC_API_KEY"]
    "SENDGRID_API_KEY"            = $envVars["SENDGRID_API_KEY"]
    "SENDGRID_FROM_EMAIL"         = $envVars["SENDGRID_FROM_EMAIL"]
    "SLACK_WEBHOOK_URL"           = $envVars["SLACK_WEBHOOK_URL"]
    "COURTLISTENER_API_TOKEN"     = $envVars["COURTLISTENER_API_TOKEN"]
    "COURTLISTENER_WEBHOOK_SECRET" = $envVars["COURTLISTENER_WEBHOOK_SECRET"]
}

foreach ($secretName in $secrets.Keys) {
    $value = $secrets[$secretName]
    if ([string]::IsNullOrEmpty($value)) {
        Write-Host "  SKIPPING $secretName (empty value)" -ForegroundColor Yellow
        continue
    }
    Write-Host "  Creating secret: $secretName"
    $value | gcloud secrets create $secretName --data-file=- 2>$null
    if ($LASTEXITCODE -ne 0) {
        # Secret already exists — add a new version instead
        Write-Host "  Secret exists, updating: $secretName" -ForegroundColor Yellow
        $value | gcloud secrets versions add $secretName --data-file=-
    }
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host "`n=== Bootstrap complete! ===" -ForegroundColor Green
Write-Host @"

Next steps:
  1. Connect your GitHub repo in Cloud Console:
     https://console.cloud.google.com/cloud-build/triggers

  2. Create a build trigger pointing to cloudbuild.yaml on the main branch.

  3. Push to main — Cloud Build will build, migrate, and deploy.

  4. After first deploy, get your service URLs:
     gcloud run services describe signalscout-api --region=$REGION --format="value(status.url)"
     gcloud run services describe signalscout-dashboard --region=$REGION --format="value(status.url)"

  5. Update cloudbuild.yaml _API_URL with the API service URL.
  6. Update firebase.json redirect destination with the dashboard URL.
  7. Run: firebase deploy --only hosting
"@
