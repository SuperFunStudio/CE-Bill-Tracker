# Deploy the DEV lane.
#
# No git guard — dev is the working-tree lane, meant for fast iteration. This
# ships whatever is currently on disk to the isolated dev environment:
#   - service  signalscout-api-dev  (min-instances=0)
#   - database signalscout_dev      (same Cloud SQL instance, separate DB)
#   - hosting  ce-bill-tracker-dev  (https://ce-bill-tracker-dev.web.app)
#   - image tag ':dev'              (prod's ':latest' is never touched)
#
# Usage:  pwsh scripts/deploy-dev.ps1            (run from repo root)

$ErrorActionPreference = "Stop"
$PROJECT = "ce-bill-tracker"

Write-Host "Submitting DEV build (cloudbuild.dev.yaml) — shipping the working tree..." -ForegroundColor Cyan
gcloud builds submit --config=cloudbuild.dev.yaml --project=$PROJECT
