# SignalScout / Compliance Scout — Adversarial Security Assessment & Remediation Plan

_Generated 2026-06-17, pre-founding-launch. Three independent adversarial reviews (backend, frontend/infra, architecture) cross-checked, then the launch-blocking claims were verified directly against source._

## Threat model
A paid SaaS ($400/mo Pro) on a **public, `--allow-unauthenticated` Cloud Run API**. The only access barrier is the per-route FastAPI dependency — there is no edge auth (Cloud Armor / IAP / API Gateway). Motivated attackers will try to: **bypass the paywall**, **grant themselves free Pro**, **run up LLM/API cost**, **destroy or corrupt data**, **abuse trials/referrals**, and **exfiltrate customer PII**.

## Posture summary
Infra/secret hygiene is genuinely good — secrets live in Secret Manager and are injected at runtime (not baked into images), `.env` is gitignored **and** `.gcloudignore`'d, no `sk_` secret keys in the frontend, no SQL injection, no `shell=True`, no `dangerouslySetInnerHTML`, and user-owned `/me/*` routes correctly scope by uid (no IDOR there). **The problem is the application-layer access gates: several are missing entirely, and the paywall is cosmetic.** Because the service is public, every missing in-app gate is directly internet-exploitable.

---

## Remediation status (updated 2026-06-17)

Implemented locally (not yet deployed — ships on the next `gcloud builds submit`), typechecked + smoke-tested:

- ✅ **C-1 — paywall now enforced server-side.** `compliance_details` removed from the bulk `BillSummary` (kills the one-call harvest + the CDN `bills.json` leak; it lives only on per-bill `BillDetail` now). `/bills/deadlines/upcoming` is optional-auth: Pro seats get the full server-merged calendar, everyone else gets the soonest **5** rows. New ungated `/bills/deadlines/summary` serves aggregate counts only. The 15s blur is replaced by a real teaser + inline unlock card. Stale leaky CDN snapshots deleted; `build-snapshot.mjs` no longer bakes the deadline rows.
- ✅ **C-2 — `/pipeline/*` router** now requires an admin token (verified 401 anon).
- ✅ **C-3 — `exposure-brief`** (LLM cost) now requires an admin token, matching the admin-only Portfolio tool (verified 401 anon).
- ✅ **C-4 — Stripe + CourtListener webhooks fail closed** when their signing secret is unset.
- ✅ **H-1 — per-IP rate limiting** added (slowapi). Blanket 240/min, plus tighter limits on the abuse-prone POSTs: access-requests 6/min, subscriptions 12/min, referral-attribute 30/hr, signup-trial 15/hr, checkout 20/hr. Webhooks exempt (signature is their guard). Verified: 429 triggers after the cap, webhook exempt. Storage is in-memory (per Cloud Run instance) — approximate global limit; move to Redis if exactness is ever needed.
- ✅ **H-2 — comp Pro grants now require a verified email** (signup trial + referral), and stacked comp days are hard-capped at **180** (bounds referral-farming payoff regardless of account count). Frontend sends a verification email on email/password signup, shows a "check your email" notice, and auto-provisions the trial/referral the moment the address verifies (Google sign-ins are verified out of the gate). Paid Stripe seats are unaffected (verification gates only *free* Pro).
- ✅ **H-3 — `entity-match-queue`** router now requires an admin token (verified 401 anon).
- ✅ **M-1 — admin resolution now requires a verified email** (`is_admin` checks `email_verified`), closing the "controls a Firebase account asserting an admin address → inherits the console" vector. ⚠️ Make sure the admin account's email is verified (Google sign-ins already are; an email/password admin must click the verification link) or it loses `/admin`.
- ✅ **M-2 — exception handler reflects only allowlisted Origins** (shared `ALLOWED_ORIGINS` constant).
- ✅ **M-3 — added `.dockerignore`** mirroring `.gcloudignore`, so `.env`/credentials/bloat can't enter the Docker build context (defense against a future `COPY . .`).
- ✅ **L-1 — admin disable-user error** no longer echoes the backend exception string to the client (logged server-side, generic message returned).
- ✅ **L-2 — Firebase ADC-fallback init** now logs loudly instead of swallowing the exception.
- ✅ **L-3 — pinned** `stripe==15.2.1` and `firebase-admin==7.4.0` (were unpinned floors).

Still open (operational / infra — not code):
- **M-4 — Cloud Armor / IAP in front of `/admin`** (and ideally the whole API) as an edge layer on top of the in-app `require_admin`. Configure in GCP, not the repo.
- Confirm the **Firebase project is set to one-account-per-email** (the default) so email-keyed entitlements can't collide across providers — the operational complement to M-1.
- Operational contingencies from the plan below: provider **spend caps** (Stripe/Anthropic/SendGrid), **Cloud SQL PITR**, and anomaly alerting.

## Findings (by severity)

| ID | Severity | Title | Location |
|----|----------|-------|----------|
| C-1 | 🔴 Critical | Paywall is cosmetic — full Pro dataset is public | `compliance/page.tsx:91`, `bills.py:35`, baked CDN `bills.json`/`deadlines.json` |
| C-2 | 🔴 Critical | Entire `/pipeline/*` router unauthenticated (destructive + LLM-cost) | `app/api/pipeline.py` |
| C-3 | 🔴 Critical | Unauthenticated LLM-generation endpoint (`exposure-brief`) | `companies.py:84` |
| C-4 | 🔴 Critical | Webhooks fail **open** when signing secret unset | `billing.py:237`, `webhooks.py:41` |
| H-1 | 🟠 High | No rate limiting anywhere | `app/main.py` (no limiter) |
| H-2 | 🟠 High | Trial + referral self-dealing → unlimited free Pro | `billing.py:73`, `referrals.py:78`, `auth.py:90` |
| H-3 | 🟠 High | Unauthenticated writes to entity-match-queue | `companies.py:540,556` |
| M-1 | 🟡 Medium | Entitlement keyed on email, not verified uid (also admin allowlist) | `auth.py:71,120` |
| M-2 | 🟡 Medium | Exception handler reflects arbitrary `Origin` | `app/main.py:44` |
| M-3 | 🟡 Medium | No `.dockerignore` — full tree is Docker build context (latent `.env` bake) | repo root |
| M-4 | 🟡 Medium | Customer PII reachable through public ingress (defense-in-depth) | `app/api/admin.py` |
| L-1 | ⚪ Low | Internal error string leaked to admin client | `admin.py:585` |
| L-2 | ⚪ Low | Firebase init exception swallowed | `auth.py:36` |
| L-3 | ⚪ Low | Two unpinned dependency floors (`stripe`, `firebase-admin`) | `requirements.txt` |

---

## Critical findings (launch blockers)

### C-1 — The Pro paywall is cosmetic; the paid data is free 🔴
**Verified.** `/compliance` calls `useDeadlines()` and `useBills({limit:5000})` against `/bills/*`, which take only `Depends(get_db)` — **no auth** (`bills.py:35`). After a 15s timer the page applies a `blur-[6px] pointer-events-none` overlay (`compliance/page.tsx:91`) over data **already in the browser**. Worse, the full `bills.json` (~1.5 MB, 5000 bills incl. `compliance_details`) and `deadlines.json` are **baked into the public Firebase CDN** with no auth.

**Attack:** open DevTools → Network and read the JSON; or hit the API directly; or `GET https://<cdn>/data/bills.json`; or delete one CSS class in the inspector. The CSV "export gate" (`compliance/page.tsx:191`) is the same data in a different wrapper. **The paid product is fully available for free.**

**Fix:** Enforce entitlement **server-side**. Add a token-checked `require_pro` endpoint that returns the full Pro dataset only to entitled callers; return a small teaser/sample to everyone else. Stop baking full `bills.json`/`deadlines.json` into the public snapshot — ship only the free teaser set to the CDN. Keep the blur as polish *on top of* the server gate.

### C-2 — `/pipeline/*` is unauthenticated: anyone can destroy data or burn LLM budget 🔴
**Verified** — `pipeline.py` router has no auth dependency and imports none. A public caller can:
- `POST /pipeline/purge-legiscan` → **deletes rows** from `bills`, `impact_score`, `bill_changes`, `compliance_deadlines`, `exposure_brief`.
- `POST /pipeline/reset-classification` → mass-wipes classification.
- `POST /pipeline/run*` → fires Cloud Run Jobs / background tasks that make Anthropic + external API calls. Per-run caps exist; **nothing caps the number of runs** → unbounded cost.

**Fix:** Mount the whole router behind admin auth — `APIRouter(prefix="/pipeline", dependencies=[Depends(require_admin)])`. Wrap the raw deletes in a transaction with explicit confirmation.

### C-3 — `exposure-brief` triggers Claude Sonnet with no auth 🔴
`GET /companies/{id}/exposure-brief` (`companies.py:84`) has no auth; when `ENABLE_INTERPRETATION=true` it generates a Sonnet brief per uncached (company, bill). An attacker iterating IDs forces thousands of generations = direct Anthropic spend. The prod flag value is **inconsistent in cloudbuild** (true in one block, false in another) — a feature flag must not be the cost gate.

**Fix:** Put `exposure-brief` (and the company-intel surface) behind `require_pro`. Add per-IP rate limiting. Don't rely on the flag.

### C-4 — Stripe & CourtListener webhooks fail **open** 🔴
**Verified** — `billing.py:237` guards signature verification behind `if secret:`. With the secret **unset/rotated/empty**, verification is skipped and the JSON body is trusted: a forged `checkout.session.completed` with arbitrary `metadata.email` + `founding:"true"` **grants anyone free Pro** (`billing.py:251-269`). CourtListener's `_verify_signature` returns `True` when no secret (`webhooks.py:41`) → injected litigation cases + alert spam + LLM cost. Prod *does* set the Stripe secret today, so this is mitigated **in prod** — but it is a fragile fail-open default.

**Fix:** Fail **closed**. If the signing secret is unset, reject the webhook (`503`). Never grant entitlement on an unverified event.

---

## High findings

### H-1 — No rate limiting anywhere 🟠
`app/main.py` has no limiter middleware. Combined with public ingress, every endpoint — the LLM triggers (C-2/C-3), `POST /access-requests` (sends email), `POST /billing/checkout` (creates Stripe objects), `POST /referrals/attribute` — is abusable for cost, spam, and enumeration. **Fix:** add `slowapi` per-IP limits (tighter on unauthenticated POSTs and anything that emails / calls Stripe / calls an LLM), and/or Cloud Armor at the edge.

### H-2 — Trial + referral self-dealing → effectively unlimited free Pro 🟠
Comp grants are keyed on `firebase_uid` / referred email with **no email-verification requirement**. An attacker scripts Firebase signups: each new account gets a 7-day signup trial (`billing.py:73`), and referral grants **stack** 30 days each (`auth.py:90`) with only the *exact same uid* blocked (`referrals.py:95`). A ring of throwaways yields perpetual Pro — a direct revenue bypass on the $400/mo product. **Fix:** require `email_verified` before any comp grant; cap total stacked comp days; velocity-check referral grants per referrer; consider payment/device fingerprinting before unlocking Pro.

### H-3 — Unauthenticated writes to entity-match-queue 🟠
`GET /entity-match-queue` and `PATCH /entity-match-queue/{id}/resolve` (`companies.py:540,556`) have no auth — anyone can mark queue items resolved and link them to arbitrary companies, corrupting entity resolution and hiding items from human review. **Fix:** `Depends(require_admin)` on `queue_router`.

---

## Medium / Low (hardening)

- **M-1** Entitlement & admin resolved by **email only** (`auth.py:71,120`). Require `email_verified`; prefer keying entitlement on uid. The admin allowlist being email-only means any Firebase account verified as `kenny@superfun.studio` becomes admin.
- **M-2** Exception handler echoes any `Origin` (`main.py:44`), defeating the CORS allowlist on error responses. `allow_credentials=False` limits impact. Reflect only allowlisted origins.
- **M-3** No `.dockerignore` — whole tree (incl. `.env`) is the build context. Selective `COPY` saves it today, but any future `COPY . .` silently bakes secrets. Add one mirroring `.gcloudignore`.
- **M-4** Admin PII endpoints are correctly behind `require_admin` but sit on public ingress — add Cloud Armor/IAP on `/admin` as defense-in-depth.
- **L-1** Don't echo backend exception strings to clients (`admin.py:585`). **L-2** Log Firebase-init failures loudly (`auth.py:36`). **L-3** Pin `stripe` and `firebase-admin` floors in `requirements.txt`.

### Verified clean (no action)
No hardcoded secrets in repo or git history; `.env` gitignored + gcloudignored; no SQL injection (raw `text()` uses only hardcoded/internal strings); no `os.system`/`shell=True`; no `dangerouslySetInnerHTML`; `/me/*` correctly uid-scoped (no IDOR); `require_pro` IS enforced server-side on `design-guide` and watchlist routes; no card data stored locally (delegated to Stripe); deploy secrets injected at runtime via Secret Manager, not baked into images.

---

## Remediation plan

### Phase 0 — Launch blockers (do before inviting founding members)
1. **C-1** Server-gate the Pro dataset (`require_pro` endpoint + teaser for anonymous) and remove full `bills.json`/`deadlines.json` from the public CDN snapshot. _Largest effort; this is THE blocker._
2. **C-2** Admin-gate the entire `/pipeline/*` router.
3. **C-3** `require_pro` + rate limit on `exposure-brief` / company-intel.
4. **C-4** Make both webhooks fail closed when their secret is unset.
5. **H-3** Admin-gate `entity-match-queue`.
6. **H-1** Add `slowapi` rate limiting (at minimum on unauthenticated POSTs + LLM/email/Stripe endpoints).

### Phase 1 — Pre-revenue-scale (within first week)
7. **H-2** Require `email_verified` before comp grants; cap stacked comp days; velocity-check referrals.
8. **M-1** Require `email_verified` for entitlement + admin resolution.
9. **M-3** Add `.dockerignore`.
10. **M-2** Allowlist-only Origin reflection in the exception handler.
11. Add endpoint tests for the billing/webhook + entitlement + referral paths (currently zero coverage on the money paths).

### Phase 2 — Hardening (post-launch)
12. **M-4** Cloud Armor / IAP in front of `/admin` (and ideally a WAF rule set on the whole API).
13. **L-1/L-2/L-3** error-string scrub, loud auth-init logging, dependency pins.
14. Re-evaluate `--allow-unauthenticated` vs an API Gateway / IAP boundary for non-public routes.

---

## Contingencies & operational safeguards

**Kill switches (have these ready before launch):**
- A documented one-command way to flip every `ENABLE_*` LLM flag off and redeploy (`cloudbuild-api-only.yaml`) to stop runaway Anthropic spend.
- Stripe + Anthropic + SendGrid: set hard **billing/budget alerts and spend caps** in each provider console so an abuse spike pages you instead of running up an unbounded bill.
- GCP budget alert already exists (per memory) — confirm threshold is tuned for the new paid traffic.

**Monitoring / detection:**
- Alert on anomalous rates of: `/pipeline/*` calls, `exposure-brief` calls, `checkout.session.completed` webhooks, comp-grant creations, and new-signup velocity per IP.
- Log + alert on `stripe_webhook_bad_signature` and any webhook received with no secret configured.
- Watch Anthropic token usage daily during launch week.

**Incident response:**
- If the paywall leak (C-1) is exploited pre-fix: rotate the CDN snapshot to the teaser set immediately; the API gate is the durable fix.
- If free Pro is granted via C-4/H-2: query `Entitlement` for `comp=true` / unverified-email seats and revoke; reconcile against Stripe `customer.subscription` truth.
- Keep a runbook entry for "revoke entitlement by email/uid" (admin endpoints already support grant/revoke).

**Backups / data integrity:**
- Confirm Cloud SQL automated backups + point-in-time recovery are enabled (C-2 could delete data before the fix lands — until `/pipeline/*` is gated, treat PITR as the safety net).

---

## One-line bottom line
**Do not invite founding members or turn on marketing until C-1 is fixed** — today the paid product is fully accessible for free, and C-2/C-3/C-4 expose the system to data destruction, unbounded LLM cost, and free-Pro forgery. All four are small, well-scoped fixes (auth dependencies + a server-gated endpoint + a CDN snapshot change). Everything else is hardening that can follow within the first week.
