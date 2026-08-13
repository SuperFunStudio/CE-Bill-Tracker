# Email deliverability — keeping our mail out of spam

**Provider: SendGrid** (`EMAIL_PROVIDER=sendgrid`, the default). Postmark is fully wired and idle:
its account is still in review, SendGrid's was approved first, so the live transport is SendGrid and
the switch back is one environment variable.

**Two transports, one seam.** `app/alerts/email_sender.py` builds a provider-neutral message
(`_build_message`) and a `_Transport` renders, sends, and reads the verdict — SendGrid via a Bearer
key to `https://api.sendgrid.com/v3/mail/send`, Postmark via the **server** token to
`https://api.postmarkapp.com/email`. Neither needs an SDK. Nothing above `_post` names a provider;
every caller gates on `settings.email_configured`, which reports on whichever provider is active.
`settings.email_provider` picks; unset, it falls to whichever API key is present, so an environment
carrying one credential can't send into the provider that has none.

`hello@atlascircular.com` is the single sending identity (`email_from` in `app/config.py`), aligned
with the public brand domain. One address for everything: a second local-part is a second reputation
to warm for no gain at this volume. What varies is the **display name**, not the mailbox —
`email_from_name` ("Atlas Circular") on the automated cycles, `email_hello_from_name` ("Kenny at
Atlas Circular") on the templates that ask for a reply. `_from_parts()` picks by what the caller
asked for rather than by address, since both resolve to the same mailbox; each transport then
formats it (Postmark wants one header string, SendGrid `{email, name}`).

**Reputation does not migrate — in either direction.** The warmth the digest/alert cycles built on
SendGrid belongs to SendGrid's IPs. Coming back to it after a fortnight away is the cheap direction;
going the other way starts the domain from its authenticated DNS and nothing else. Either way, ramp
volume rather than resuming the old cadence in one cycle.

**What success looks like differs, which is the whole risk of a switch.**

- **SendGrid: `202`, empty body.** Anything else is a failure; the messages live under `errors[]`.
  A `403` reading "does not match a verified Sender Identity" is the one to know — check domain
  authentication first.
- **Postmark: `200` is not success.** It answers `200` for rejected messages too; the verdict is the
  body's `ErrorCode`, which must be `0`. `406` means the recipient is on the server's suppression
  list (hard bounce or spam complaint) and retrying won't help; `300` is an unverified From-address;
  `412` is **account pending approval**, where every recipient must be on the From domain — seen live
  on 2026-08-12, when a send to `kenny@superfun.studio` was refused while `@atlascircular.com`
  delivered.

Reading either provider's status line the other's way reports every rejection as delivered.
`tests/test_alerts/test_email_transport.py` pins both verdicts against the other's shape, so a switch
fails in CI rather than in the inbox.

**Message streams (Postmark only).** Postmark refuses to mix transactional and bulk traffic on one
stream, and the separation is what stops a digest opt-out from suppressing a password-reset email.
`_stream_for()` picks the stream from one signal: a send carrying a one-click unsubscribe URL is bulk
and goes on `postmark_broadcast_stream`, everything else on `postmark_message_stream`. Both streams
must exist on the server or those sends 422. SendGrid has no equivalent — the same unsubscribe URL
only sets its RFC 8058 headers, which is why the neutral message records the URL rather than a
resolved stream name.

**The principle, for anything new:** spam classification weights sender reputation and domain
authentication far above content. No amount of body tuning overrides an unauthenticated, misaligned
sending domain — and every *additional* sending identity starts cold and has to be authenticated and
warmed separately. So the default answer to "how should this new email go out?" is: through the
existing sender, not a new one.

## Click tracking is OFF — and why

The provider's click tracking rewrites every `href` to go through a branded click host. On SendGrid
that host (`url7082.atlascircular.com`) served a certificate that didn't cover it, so a recipient
clicking **any** link in **any** email — "Open your dashboard", a bill deep link, a verification
button — landed on Chrome's full-page `NET::ERR_CERT_COMMON_NAME_INVALID` warning. Every outbound
message was affected, not just one template. **And SendGrid is what we are back on**, so this is a
live hazard again, not a historical note.

Each transport reads `email_click_tracking` and defaults it off: SendGrid gets
`click_tracking.enable=false` **with `enable_text=false`** (disabling only the HTML rewrite leaves
the plain-text part pointing at the broken host), Postmark gets `TrackLinks: "None"`. Hrefs go out
verbatim. Cost: no click stats. Benefit: links work, and there's one less host mismatch for a spam
filter to weigh.

**To re-enable**, fix the click host at the active provider first — SendGrid: Sender Authentication →
Link Branding → validate SSL; Postmark: Servers → Message Streams → Settings, plus DNS if you brand
the host. Confirm a tracked link loads cleanly in a browser, *then* set `email_click_tracking=true`.
Don't flip the flag first and check later — the failure mode is a security interstitial on every link
we've ever sent.

## Masthead, preheader, footer

`app/alerts/email_shell.py` owns the chrome every email wears. Three rules, all learned the hard way:

1. **No publisher byline.** The kicker above the wordmark used to read "SUPERFUN STUDIO · PRESENTS"
   on every send. It spent the reader's first glance on us instead of on the news, and — because it
   was the first text in `<body>` — it was also the *preheader*, so the inbox row next to the subject
   read "SUPERFUN STU…". The kicker is now an **edition line** supplied per email
   (`LITIGATION ALERT · 18 JUNE 2026`): classification plus freshness, both scannable at a glance.
   Pass `kicker=None` when there's nothing worth putting there — no line beats an empty one.
2. **Always pass a `preheader`** on anything a recipient chooses whether to open. It's the highest-
   leverage copy in the message and the only line that competes with the subject. Keep it under ~90
   characters and spend it on what the reader decides on — for litigation alerts that's the
   *jurisdiction* (they subscribed by state) and whether enforcement is affected, not the court.
   Without one, the client scrapes the top of the body and you get whatever the masthead says.
3. **The identity block is not optional and not per-template.** `_identity_block()` renders on every
   email `render_shell` produces — brand, publisher byline linking to superfun.studio, the postal
   address, Privacy Policy and Terms. Don't add these per-template and don't add a way to switch them
   off; a new template inherits compliance by going through the shell, which is the whole point.
   See "Sender identity and the postal address" below for why.
4. **Unsubscribe is a button, not a buried link** (`unsubscribe_url`), and alert emails carry a
   "Was this forwarded to you?" subscribe line (`subscribe_url`). Making it hard to leave earns spam
   complaints, which cost far more deliverability than the unsubscribe does.

## Sender identity and the postal address

**Why this exists.** When the SendGrid free trial ended and we applied to upgrade, SendGrid opened a
compliance ticket rather than just taking the money. Their review is of the *account*, and the thing
our mail was missing was a physical mailing address — CAN-SPAM §7704(a)(5) requires one on commercial
mail, and an account that sends without it is an account they suspend. We had already added the
unsubscribe; the address and the Privacy Policy link were the gap.

**What renders.** `_identity_block()` in `app/alerts/email_shell.py`, appended inside `render_shell`
after the footer actions, on **every** email including transactional ones:

```
Atlas Circular
a SUPERFUN STUDIO project        ← links to https://www.superfun.studio
1924 … · San Diego, CA …         ← from BUSINESS_ADDRESS; omitted if unset
Privacy Policy · Terms
```

Brand first, publisher under it in smaller type carrying the link: the reader sees the publication
they subscribed to, and can still verify a real company stands behind it.

Transactional mail carries it too. CAN-SPAM only compels the address on commercial messages, but the
line SendGrid's review draws is at the account, not the message — and the cost on a password reset is
four lines of 11px grey.

**Where the address lives.** `BUSINESS_ADDRESS` (`settings.business_address`), env-only with an empty
default so the address is never committed. Lines separate on `|` or newline.

- Local: in `.env` (gitignored).
- Prod: **Secret Manager**, not `--set-env-vars`. `cloudbuild.yaml` passes
  `BUSINESS_ADDRESS=BUSINESS_ADDRESS:latest` in `--set-secrets` on both the API service and the
  pipeline job — the secret *name* is in git, the value isn't. `signalscout-api@` has
  `secretAccessor` on it. Deploy fails loudly if the secret is missing, which is the right failure.

Unset degrades to a footer without the address rather than an exception — a missing env var must not
take down every outbound email. `tests/test_alerts/test_email_compliance_footer.py` covers both paths
and asserts the block survives on the barest transactional shell.

**Plain text too.** Bodies derived from the HTML pick it up via `html_to_text`. The two senders that
hand-build a `text/plain` part append `identity_text()` explicitly — divergent MIME parts are
themselves a spam signal.

**Verifying without sending.** `scripts/send_email_samples.py --render-only` renders all 21 templates
to `tmp/email_samples/` and makes zero API calls. Use it for any chrome change; a render check has no
business touching a sending reputation that's under review.

## Attribution without click tracking

Click tracking is off, so the ESP can't tell us what got clicked. UTM params do the job instead:
`applinks.with_utm()` tags every in-app link as `utm_source=atlas_alert&utm_medium=<channel>&
utm_campaign=<what sent it>`, the frontend's `captureAttribution()` reads them on landing, and GA4
attributes the session. `medium` separates email from Slack for links that go out on both.

Campaigns in use: `litigation_alert`, `litigation_forward`, `bill_alert_forward`. Add one per new
email type rather than reusing an existing name — the campaign IS the report line.

This measures **clicks-through-to-app**, which is the number that matters. It does not measure opens;
Open tracking rides on the same click host, so opens stay dark until the
cert is fixed.

## Where email links should point

In-app first, primary source second. Every email links to Atlas Circular — the bill panel, the case
page, the deadlines timeline — and the outbound link to the legislature site or CourtListener lives on
*that* page. Two reasons: the reader gets our analysis rather than a raw docket, and a cold external
domain in the body is another thing for a spam filter to weigh. `app/alerts/applinks.py` holds the URL
builders (`bill_url`, `litigation_case_url`, `state_url`) so the scheme lives in one place.

Litigation alerts follow this via `app/alerts/litigation_alerts.py`, which is also where the
channel-neutral body rule lives: the same string goes to Slack (mrkdwn) and to an HTML email, so the
body carries **no markdown** (email printed the literal `**asterisks**`) and **no URLs** (the email
renders a CTA button; Slack gets the link appended).

## Account-security emails (verify address / reset password)

These used to be the exception. The frontend called the Firebase client SDK directly, so they went out
from `noreply@ce-bill-tracker.firebaseapp.com` — a second, cold sending identity, unauthenticated
against `atlascircular.com`, with a firebaseapp.com link and none of our branding. They were the most
spam-prone mail we sent *and* the two messages a user is most likely to be waiting on.

They now route through our own pipeline instead (`app/alerts/auth_emails.py`,
`app/api/auth_email.py`): firebase-admin still mints the action link — same one-time `oobCode`,
same expiry and single-use semantics — and we render it in the shared masthead and send it from our
own authenticated identity (`email_from`, `hello@atlascircular.com`).

Fail-soft by design. `POST /auth/send-verification` and `POST /auth/send-password-reset` return
`{"sent": false}` whenever the branded send didnt happen (flag off, email unconfigured, send
failed), and the frontend falls back to the Firebase SDK's own send. Losing the pretty email must
never mean a user can't verify an address or recover an account. Kill switch: `enable_auth_emails`
(deliberately separate from `enable_welcome_email`, so turning off lifecycle mail can't take account
verification with it).

**Still open — the link domain.** The action link still points at
`ce-bill-tracker.firebaseapp.com/__/auth/action`, because Firebase builds it from the project's
authDomain. Cosmetic for deliverability now that the From-domain is aligned, but a firebaseapp.com URL
in an otherwise-branded email is a jarring trust moment. To close it:

1. Add `atlascircular.com` (or `auth.atlascircular.com`) as a custom domain on the `ce-bill-tracker`
   Firebase Hosting site — Hosting auto-serves the `/__/auth/` handler on any attached domain.
2. Add it under Authentication → Settings → **Authorized domains**.
3. Change `authDomain` in `dashboard-next/src/lib/firebase.ts`.

Do them in that order: flipping `authDomain` before the domain is live and authorized breaks the
Google/Microsoft sign-in redirect.

## The DNS foundation (one-time, already in place)

Recorded here because it's the part that actually moves mail out of spam, and any future sending
domain needs the same treatment.

1. **Authenticate the domain at the provider** — always the apex `atlascircular.com`, **not**
   `www.atlascircular.com`; a `www` entry authorises nothing for `hello@atlascircular.com`. Verifying
   a *signature* (one address) is not the same thing: it covers only that address and skips the
   Return-Path, so do the domain even if `hello@` already works.

   - **SendGrid** — Sender Authentication → Authenticate Your Domain, which issues `s1`/`s2`
     `._domainkey` CNAMEs plus a Return-Path CNAME (`emXXXX` → `uXXXX.wl.sendgrid.net`).
   - **Postmark** — Sender Signatures → **Domains** → Add Domain, which issues a DKIM TXT record
     (`<selector>._domainkey.atlascircular.com`) and a Return-Path CNAME (`pm-bounces` →
     `pm.mtasv.net`).

   **Keep both sets live in DNS while both providers are wired.** They don't collide — different
   selectors, different Return-Path hosts — and each provider signs only with its own. Deleting the
   idle provider's records is what turns `EMAIL_PROVIDER=<other>` from a switch into an outage: mail
   goes out unsigned and DMARC fails. Prune only after deciding a provider is gone for good.
2. **DMARC** — a TXT record at `_dmarc.atlascircular.com`. Live value, verified 2026-08-11:
   ```
   v=DMARC1; p=none; rua=mailto:kenny@atlascircular.com; fo=1
   ```
   Two things follow from this that are easy to misread:

   - **The daily XML mail from Google et al. is this record working**, not a failure. `rua` points at
     a human inbox, so every receiver's aggregate report lands there unparsed. Send it to a free
     DMARC parser (Postmark's DMARC Digest, URIports) instead — the reports are only worth
     requesting if something reads them.
   - **`p=none` enforces nothing.** It's monitor mode, and it has been for long enough that the
     reports should be clean. Tighten to `p=quarantine` once a parser confirms that — an enforcing
     policy is also a favorable signal in an ESP compliance review.

   Alignment rides on **DKIM**, not the apex SPF record: the provider's DKIM record makes mail signed
   `d=atlascircular.com`, and DMARC passes on that alone. This is also what makes the provider switch
   invisible to DMARC — the signature domain is ours either way. The apex SPF record is
   `v=spf1 include:_spf.google.com ~all` and deliberately does **not** list either ESP — each custom
   Return-Path subdomain carries its own SPF, which is what SPF alignment is checked against. Adding
   `include:sendgrid.net` or `include:spf.mtasv.net` at the apex would buy nothing and spend the
   permitted DNS lookups.
3. **From-address on the authenticated domain** — `EMAIL_FROM=hello@atlascircular.com`, set as a
   plain env var in `cloudbuild.yaml` (an address isn't a secret) and read at startup, so redeploy
   after changing. `SENDGRID_FROM_EMAIL` is still accepted as a fallback for environments that
   predate it. The local-part doesn't matter; the domain does. **Reply-To** is
   separate and points at a monitored human mailbox (`email_reply_to`, default
   `kenny@atlascircular.com`, applied to every send). Keep the two distinct: the From stays on the
   warmed identity, replies reach a person. Same verified domain, so a new local-part needs a
   mailbox but no new DNS.
4. **Link tracking** (optional) — off by default, see above.

`battleofbills.com` 301-redirects to the current domain, so links in already-sent mail still resolve.

## How to verify

- Preview only, no sends: `venv/Scripts/python.exe scripts/send_email_samples.py --render-only`.
- Preview/send every template at once: `venv/Scripts/python.exe scripts/send_email_samples.py` — renders
  all of them to `tmp/email_samples/` and sends one of each to a hardcoded address. The two
  account-security templates render against a synthetic link (minting a real one would email a working
  verify/reset link for a live account).
- In the received message → "Show original" (Gmail) / "View source" (Outlook), confirm `SPF: PASS`,
  `DKIM: PASS`, `DMARC: PASS`, and that the DKIM `d=` domain is `atlascircular.com` — not
  `sendgrid.net`, not `pm.mtasv.net`. A provider's own domain in `d=` means the send fell back to
  their signature because ours isn't authenticated.
- Run the From-address through https://www.mail-tester.com — aim for 9–10/10.

## Switching providers

The switch is `EMAIL_PROVIDER` — `sendgrid` or `postmark` — plus the matching API key. Everything
else (templates, identities, unsubscribe wiring, the footer) is provider-neutral by construction.

1. Confirm the target provider's DNS is still live (see the DNS section) and its account isn't in a
   review that restricts recipients — Postmark's `412` means every recipient must be on the From
   domain, which looks exactly like "email is broken for customers".
2. Confirm the key: `gcloud secrets versions access latest --secret=SENDGRID_API_KEY` /
   `POSTMARK_API_KEY`. Both secrets exist and `signalscout-api@` reads them via a project-level
   `secretAccessor` binding. Watch for a trailing newline in the stored payload — it reads back as a
   401. Write with `[IO.File]::WriteAllText($p, $t, (New-Object Text.UTF8Encoding $false))`, never
   `"token" | gcloud secrets versions add --data-file=-`, which appends CRLF in PowerShell.
3. Flip `EMAIL_PROVIDER` in `cloudbuild.yaml` (both the API service and the pipeline job) and deploy.
4. Send yourself one of each stream: `scripts/send_email_samples.py` covers all 21 templates,
   including the founder-voice and unsubscribe-carrying ones, which is what exercises the bulk path.
5. Suppression lists, opens, and click stats are **per provider** and do not transfer. A recipient
   suppressed on the provider you left is not suppressed on the one you moved to.

## What the code already does

Multipart `text/plain` alongside every HTML body, in-app links rather than bare external pages, and
RFC 8058 one-click `List-Unsubscribe` on the recurring/bulk cycles. The account-security emails
deliberately carry **no** List-Unsubscribe — they're transactional, not opt-out-able.
