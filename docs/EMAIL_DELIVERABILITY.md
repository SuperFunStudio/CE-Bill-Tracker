# Email deliverability — keeping our mail out of spam

**Status:** the SendGrid path is done and working. `alerts@atlascircular.com` is the authenticated
sending identity (`sendgrid_from_email` in `app/config.py`), aligned with the public brand domain, and
the digest/alert cycles have warmed its reputation.

**The principle, for anything new:** spam classification weights sender reputation and domain
authentication far above content. No amount of body tuning overrides an unauthenticated, misaligned
sending domain — and every *additional* sending identity starts cold and has to be authenticated and
warmed separately. So the default answer to "how should this new email go out?" is: through the
existing SendGrid sender, not a new one.

## Click tracking is OFF — and why

SendGrid's click tracking rewrites every `href` to go through the branded click host
`url7082.atlascircular.com`. That host is serving a certificate that doesn't cover it, so a recipient
clicking **any** link in **any** email — "Open your dashboard", a bill deep link, a verification
button — lands on Chrome's full-page `NET::ERR_CERT_COMMON_NAME_INVALID` warning. Every outbound
message was affected, not just one template.

`_apply_tracking()` in `app/alerts/sendgrid_sender.py` now disables click tracking (`enable` and
`enable_text`) on every send, so hrefs go out verbatim. Cost: no SendGrid click stats. Benefit: links
work, and there's one less host mismatch for a spam filter to weigh.

**To re-enable**, fix the cert first — SendGrid → Sender Authentication → **Link Branding**, validate
the branded domain's SSL (the automated-security CNAMEs must resolve and the cert must be issued for
`url7082.atlascircular.com`). Confirm a tracked link loads cleanly in a browser, *then* set
`sendgrid_click_tracking=true`. Don't flip the flag first and check later — the failure mode is a
security interstitial on every link we've ever sent.

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
3. **Unsubscribe is a button, not a buried link** (`unsubscribe_url`), and alert emails carry a
   "Was this forwarded to you?" subscribe line (`subscribe_url`). Making it hard to leave earns spam
   complaints, which cost far more deliverability than the unsubscribe does.

## Attribution without click tracking

Click tracking is off, so SendGrid can't tell us what got clicked. UTM params do the job instead:
`applinks.with_utm()` tags every in-app link as `utm_source=atlas_alert&utm_medium=<channel>&
utm_campaign=<what sent it>`, the frontend's `captureAttribution()` reads them on landing, and GA4
attributes the session. `medium` separates email from Slack for links that go out on both.

Campaigns in use: `litigation_alert`, `litigation_forward`, `bill_alert_forward`. Add one per new
email type rather than reusing an existing name — the campaign IS the report line.

This measures **clicks-through-to-app**, which is the number that matters. It does not measure opens;
SendGrid's open pixel would be served from the same broken branded host, so opens stay dark until the
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
`{"sent": false}` whenever the branded send didn't happen (flag off, SendGrid unconfigured, send
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

1. **Authenticate the domain in SendGrid** — Settings → Sender Authentication → Authenticate Your
   Domain, using `atlascircular.com`. SendGrid issues ~3 CNAMEs (`s1._domainkey`, `s2._domainkey`, and
   the return-path/`em` host); add them at the DNS host and click Verify. This is what establishes
   SPF + DKIM aligned to our domain.
2. **DMARC** — a TXT record at `_dmarc.atlascircular.com`. Start in monitor mode and tighten once
   reports are clean:
   ```
   v=DMARC1; p=none; rua=mailto:dmarc@atlascircular.com; fo=1
   ```
3. **From-address on the authenticated domain** — `SENDGRID_FROM_EMAIL=alerts@atlascircular.com`
   (read at startup, so redeploy after changing). The local-part doesn't matter; the domain does.
   **Reply-To** is separate and points at a monitored human mailbox
   (`sendgrid_reply_to`, default `kenny@atlascircular.com`, applied to every send). Keep the two
   distinct: the From stays on the warmed identity, replies reach a person. Same authenticated
   domain, so a new local-part needs a mailbox but no new DNS.
4. **Link branding** (recommended) — SendGrid → Sender Authentication → Link Branding, so click-tracked
   links use `atlascircular.com` instead of `sendgrid.net`.

`battleofbills.com` 301-redirects to the current domain, so links in already-sent mail still resolve.

## How to verify

- Preview/send every template at once: `venv/Scripts/python.exe scripts/send_email_samples.py` — renders
  all of them to `tmp/email_samples/` and sends one of each to a hardcoded address. The two
  account-security templates render against a synthetic link (minting a real one would email a working
  verify/reset link for a live account).
- In the received message → "Show original" (Gmail) / "View source" (Outlook), confirm `SPF: PASS`,
  `DKIM: PASS`, `DMARC: PASS`, and that the DKIM `d=` domain is `atlascircular.com`, not `sendgrid.net`.
- Run the From-address through https://www.mail-tester.com — aim for 9–10/10.

## What the code already does

Multipart `text/plain` alongside every HTML body, in-app links rather than bare external pages, and
RFC 8058 one-click `List-Unsubscribe` on the recurring/bulk cycles. The account-security emails
deliberately carry **no** List-Unsubscribe — they're transactional, not opt-out-able.
