# Deploy the PRODUCTION lane.
#
# Guard: refuses to deploy unless the working tree is clean, you are on 'main',
# and local 'main' matches origin/main. Because `gcloud builds submit` uploads the
# WORKING TREE (not a git commit), this guard is what guarantees "what's live"
# always equals a committed main commit — it stops uncommitted/experimental code
# from shipping to production.
#
# Usage:  pwsh scripts/deploy-prod.ps1            (run from repo root)
#         pwsh scripts/deploy-prod.ps1 -Force     (skip guard — emergency only)

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$PROJECT = "ce-bill-tracker"

function Fail($msg) {
    Write-Host "PROD DEPLOY BLOCKED: $msg" -ForegroundColor Red
    Write-Host "Use the dev lane (scripts/deploy-dev.ps1) to test uncommitted work, or pass -Force to override." -ForegroundColor Yellow
    exit 1
}

if (-not $Force) {
    # 1. Must be on main
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "current branch is '$branch', not 'main'."
    }

    # 2. Working tree must be clean (no staged/unstaged/untracked changes)
    $dirty = git status --porcelain
    if ($dirty) {
        Write-Host $dirty
        Fail "working tree is dirty. Commit or stash before deploying to prod."
    }

    # 3. Local main must be up to date with origin/main
    git fetch origin main --quiet
    $local  = (git rev-parse "@").Trim()
    $remote = (git rev-parse "@{u}").Trim()
    if ($local -ne $remote) {
        Fail "local main ($($local.Substring(0,8))) differs from origin/main ($($remote.Substring(0,8))). Pull/push to sync first."
    }

    Write-Host "Guard passed: clean main @ $($local.Substring(0,8)), in sync with origin." -ForegroundColor Green
} else {
    Write-Host "WARNING: -Force set — skipping clean-main guard. Shipping the working tree as-is." -ForegroundColor Yellow
}

Write-Host "Submitting PROD build (cloudbuild.yaml)..." -ForegroundColor Cyan
gcloud builds submit --config=cloudbuild.yaml --project=$PROJECT
