# Email deliverability — keeping our mail out of spam

**Provider: Postmark** (migrated off SendGrid). `app/alerts/email_sender.py` posts to
`https://api.postmarkapp.com/email` with the **server** API token (`POSTMARK_API_KEY`); there's no
SDK. `hello@atlascircular.com` is the single sending identity (`email_from` in `app/config.py`),
aligned with the public brand domain. One address for everything: a second local-part is a second
reputation to warm for no gain at this volume. What varies is the **display name**, not the mailbox
— `email_from_name` ("Atlas Circular") on the automated cycles, `email_hello_from_name` ("Kenny from
Atlas Circular") on the templates that ask for a reply. `_from_header()` picks by what the caller
asked for rather than by address, since both resolve to the same mailbox.

**Reputation does not migrate.** The warmth the digest/alert cycles built on SendGrid belonged to
SendGrid's IPs, not to us. On a new provider the domain starts from its authenticated DNS and
nothing else, so ramp volume rather than resuming the old cadence in one cycle.

**Message streams.** Postmark refuses to mix transactional and bulk traffic on one stream, and the
separation is what stops a digest opt-out from suppressing a password-reset email. `_stream_for()`
picks the stream from one signal: a send carrying a one-click unsubscribe URL is bulk and goes on
`postmark_broadcast_stream`; everything else is transactional and goes on `postmark_message_stream`.
Both streams must exist on the server or those sends 422.

**200 is not success.** Postmark answers `200` for rejected messages too — the verdict is the body's
`ErrorCode`, which must be `0`. `406` means the recipient is on the server's suppression list (hard
bounce or spam complaint) and retrying won't help; `300` is an unverified From-address; `412` is
**account pending approval**, where every recipient must be on the From domain — verified live on
2026-08-12, when a send to `kenny@superfun.studio` was refused while `@atlascircular.com` delivered.
`tests/test_alerts/test_postmark_transport.py` pins the contract.

**The principle, for anything new:** spam classification weights sender reputation and domain
authentication far above content. No amount of body tuning overrides an unauthenticated, misaligned
sending domain — and every *additional* sending identity starts cold and has to be authenticated and
warmed separately. So the default answer to "how should this new email go out?" is: through the
existing sender, not a new one.

## Click tracking is OFF — and why

The provider's click tracking rewrites every `href` to go through a branded click host. Under
SendGrid that host (`url7082.atlascircular.com`) served a certificate that didn't cover it, so a
recipient clicking **any** link in **any** email — "Open your dashboard", a bill deep link, a
verification button — landed on Chrome's full-page `NET::ERR_CERT_COMMON_NAME_INVALID` warning.
Every outbound message was affected, not just one template.

`_build_payload()` in `app/alerts/email_sender.py` sends `TrackLinks: "None"` unless
`email_click_tracking` is set, so hrefs go out verbatim. Cost: no click stats. Benefit: links work,
and there's one less host mismatch for a spam filter to weigh.

**To re-enable**, set up link tracking in Postmark first (Servers → Message Streams → Settings), and
if you brand the click host, add its DNS and let Postmark issue the cert. Confirm a tracked link
loads cleanly in a browser, *then* set `email_click_tracking=true`. Don't flip the flag first and
check later — the failure mode is a security interstitial on every link we've ever sent.

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
same expiry and single-use semantics — and we render it in the shared masthead and send it as
`alerts@atlascircular.com`.

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

1. **Verify the domain at the provider** — Postmark → Sender Signatures → **Domains** → Add Domain,
   using `atlascircular.com` (the apex — **not** `www.atlascircular.com`; a `www` entry authorises
   nothing for `alerts@atlascircular.com`). Postmark issues a DKIM TXT record
   (`<selector>._domainkey.atlascircular.com`) and a Return-Path CNAME (e.g. `pm-bounces` →
   `pm.mtasv.net`). Add both, click Verify. This is what establishes DKIM — and, via the custom
   Return-Path, SPF alignment. A verified *signature* (one address) is not the same thing: it covers
   only that address and skips the Return-Path, so verify the domain even if `hello@` already works.

   Historic: the SendGrid equivalent was Sender Authentication → Authenticate Your Domain, which
   issued `s1`/`s2._domainkey` CNAMEs. Those records are dead once the cutover is done and can be
   removed from DNS after the last SendGrid send has left the queue.
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

   Alignment rides on **DKIM**, not the apex SPF record: the provider's DKIM TXT record makes mail
   signed `d=atlascircular.com`, and DMARC passes on that alone. The apex SPF record is
   `v=spf1 include:_spf.google.com ~all` and deliberately does **not** list the ESP — the custom
   Return-Path subdomain carries its own SPF, which is what SPF alignment is checked against. Adding
   `include:spf.mtasv.net` at the apex would buy nothing and spend one of the ten permitted DNS
   lookups.
3. **From-address on the verified domain** — `EMAIL_FROM=hello@atlascircular.com`, set as a plain
   env var in `cloudbuild.yaml` (an address isn't a secret) and read at startup, so redeploy after
   changing. `SENDGRID_FROM_EMAIL` is still accepted as a fallback for environments that predate the
   cutover. The local-part doesn't matter; the domain does. **Reply-To** is
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
  `DKIM: PASS`, `DMARC: PASS`, and that the DKIM `d=` domain is `atlascircular.com`, not `pm.mtasv.net`.
- Run the From-address through https://www.mail-tester.com — aim for 9–10/10.

## What the code already does

Multipart `text/plain` alongside every HTML body, in-app links rather than bare external pages, and
RFC 8058 one-click `List-Unsubscribe` on the recurring/bulk cycles. The account-security emails
deliberately carry **no** List-Unsubscribe — they're transactional, not opt-out-able.
