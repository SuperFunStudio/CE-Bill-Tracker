# Email deliverability — stop the welcome/alert emails landing in spam

**Symptom:** the signup welcome (and other transactional emails) consistently land in Gmail/Outlook
spam, so users miss them.

**Root cause is DNS, not code.** The sending address defaults to `alerts@signalscout.io`
(`SENDGRID_FROM_EMAIL`, see `app/config.py`), which (a) does **not** match the public brand domain
`battleofbills.com` and (b) is almost certainly **not domain-authenticated** in SendGrid. Mailbox
providers treat "brand says Battle of the Bills, From-domain is signalscout.io, and that domain has no
SPF/DKIM aligned with SendGrid" as a strong spam signal. No amount of email-body tuning overrides an
unauthenticated, misaligned sending domain.

The code-side mitigations are already in place (every email now ships a `text/plain` alternative part
alongside the HTML, and links point into the app rather than at bare external pages). The remaining
fix is the DNS/SendGrid work below — **this is the part that actually moves mail out of spam.**

## What to do (one-time, ~30 min + DNS propagation)

### 1. Authenticate the sending domain in SendGrid
SendGrid → **Settings → Sender Authentication → Authenticate Your Domain**.

- Use `battleofbills.com` (the public brand domain) as the sending domain so the From-address aligns
  with the brand. Pick a subdomain like `em` or `mail` when prompted (SendGrid's default).
- SendGrid gives you **CNAME records** (typically 3: one for DKIM `s1._domainkey`, one for `s2._domainkey`,
  and one for the return-path/`em` host). Add them at your DNS host for `battleofbills.com`.
- Back in SendGrid, click **Verify**. This sets up **SPF + DKIM** aligned to your domain.

### 2. Add a DMARC record
At your DNS host add a TXT record so providers know how to treat unauthenticated mail and where to
report. Start in monitor mode:

```
Host:  _dmarc.battleofbills.com
Type:  TXT
Value: v=DMARC1; p=none; rua=mailto:dmarc@battleofbills.com; fo=1
```

Once SendGrid auth is verified and you've watched reports for a week or two with no surprises, tighten
to `p=quarantine` and eventually `p=reject`.

### 3. Move the From-address onto the authenticated domain
Set the env var on the API (Cloud Run) so it matches the authenticated domain:

```
SENDGRID_FROM_EMAIL=alerts@battleofbills.com
```

(Or `hello@`, `no-reply@`, etc. — any mailbox on the authenticated domain. The local-part doesn't
matter for auth; the **domain** does.) The code reads this at startup, so redeploy/restart after
setting it. Until this is changed, mail still goes out as `signalscout.io` and stays misaligned.

### 4. (Recommended) Set up a custom return-path / link branding
SendGrid → Sender Authentication → **Link Branding**. Adds CNAMEs so the click-tracking links in
emails use `battleofbills.com` instead of `sendgrid.net`, removing another mismatch signal.

## How to verify it worked
- Send a test (sign up a throwaway account, or run `scripts/send_welcome.py` / `scripts/send_digest.py`).
- Open the received message → "Show original" (Gmail) / "View source" (Outlook) and confirm:
  - `SPF: PASS`, `DKIM: PASS`, `DMARC: PASS`
  - the DKIM `d=` domain is `battleofbills.com` (aligned), not `sendgrid.net`.
- Run the From-address through https://www.mail-tester.com — aim for 9–10/10.
- Confirm the message now lands in **Primary/Inbox**, not Spam.

## Why the code can't fix this alone
Spam classification weights sender reputation and domain authentication far above content. The app
already does its part (multipart text+HTML, real in-app links, one-click List-Unsubscribe headers on
recurring mail). The authentication + From-domain alignment above is the lever that flips deliverability.
