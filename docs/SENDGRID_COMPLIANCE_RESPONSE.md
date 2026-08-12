# SendGrid compliance ticket — response

Draft reply for the account-review ticket SendGrid opened when we applied to upgrade off the free
trial. Kept in the repo because the same questions come back at every ESP review (and at Postmark /
Mailgun if we ever move), and because the answers are claims about the product that should stay in
sync with what we actually ship.

**Before sending, fill the two `«…»` placeholders.** Everything else is verified against the code.

**What changed in the product because of this ticket** (so the reply is true when it's sent):

- Every outbound email now carries a footer identity block: brand, publisher byline linking to
  superfun.studio, our physical mailing address, and links to the Privacy Policy and Terms
  (`app/alerts/email_shell.py`, `_identity_block`). The unsubscribe button was already there.
- The subscribe form now states the consent terms and links the Privacy Policy at the point of
  submission (`dashboard-next/src/components/about/SubscribeForm.tsx`).

---

## Reply

Thanks — answers below, in your order.

**1. Official website**

https://www.atlascircular.com

**2. Business model and what we provide**

Atlas Circular is a subscription research service that tracks circular-economy legislation and
regulation — extended producer responsibility (EPR), right to repair, deposit-return schemes,
recycled-content mandates, and packaging labeling rules — across US states, the EU, and a growing set
of other national jurisdictions.

We ingest primary legal sources (state legislature APIs, the Federal Register, EUR-Lex, and national
law portals), classify and structure each measure, and present it to subscribers as a searchable
atlas with compliance obligations, deadlines, and fee schedules attached. Customers are packaging and
consumer-goods companies, sustainability and compliance teams, trade associations, and public-affairs
professionals who need to know which obligations apply to them and by when.

Revenue is a SaaS subscription (a free tier plus a paid Pro tier, billed through Stripe). We do not
sell, rent, or share subscriber email addresses, and we do not send mail on behalf of third parties —
every message we send is our own content to people who asked us for it.

**3. Name and affiliation**

Kenny «LAST NAME», founder and operator of Atlas Circular, a project of SUPERFUN STUDIO
(https://www.superfun.studio). I am the sole person responsible for this SendGrid account.

Publicly verifiable: «LINKEDIN PROFILE URL»

**4. What we send, and opt-in**

Both transactional and opt-in marketing/editorial mail, all from `alerts@atlascircular.com` on our
own domain-authenticated sending identity (SPF/DKIM/DMARC aligned to atlascircular.com):

*Transactional* — email verification, password reset, subscription welcome and receipt, payment
failure, cancellation confirmation. Sent only in response to an action the recipient took. These
deliberately carry no List-Unsubscribe, as they are not opt-out-able account mail.

*Opt-in editorial and alerts* — a periodic digest of new legislation matching the jurisdictions,
materials, and policy topics the subscriber selected; deadline reminders; and alerts when a bill the
subscriber is following moves. All of these are explicitly requested at sign-up, carry a visible
unsubscribe button in the body, and send RFC 8058 one-click `List-Unsubscribe` headers.

Opt-in page: **https://www.atlascircular.com/about#get-updates** (the same form also appears on our
homepage at https://www.atlascircular.com). The subscriber enters their own address, chooses which
jurisdictions, materials, and topics they want to hear about, and the form states before submission
what they will receive, that every email includes an unsubscribe link, and where our Privacy Policy
is. There is no pre-checked consent box, no purchased list, and no address is ever added to a mailing
by anyone other than its owner.

**5. Content sample**

«ATTACH the .eml or a screenshot — see "How to produce the sample" below.»

The sample shows all three required elements in the footer:

- **Unsubscribe link** — the bordered "Unsubscribe from these alerts" button.
- **Privacy Policy link** — https://www.atlascircular.com/privacy (Terms alongside it).
- **Physical mailing address** — directly under the "a SUPERFUN STUDIO project" line.

Our Privacy Policy is public at https://www.atlascircular.com/privacy and our Terms at
https://www.atlascircular.com/terms.

---

## How to produce the sample

The account is suspended pending this review, so the API key returns **401 Unauthorized** — we cannot
mail ourselves a sample until they restore it. Render locally instead; the output is identical, since
the same renderer produces both.

1. `venv/Scripts/python.exe scripts/send_email_samples.py --render-only`
2. Open `tmp/email_samples/index.html` — a contact sheet of **all 21 templates** in one page, each in
   a self-contained iframe. Print it to PDF and attach that; it answers "what do you send" and "show
   me the footer" in one artifact.
3. For a single-email sample, `tmp/email_samples/digest.html` is the best one — the digest is the
   recurring editorial email their question is really about.
4. `tmp/atlas-email-samples.zip` (built with `Compress-Archive`) is the whole folder, if they'd
   rather have the raw files than a PDF.

Once the account is live again, the send pass (no `--render-only`) mails one of each to the hardcoded
`kenny@superfun.studio` — never a subscriber address. Worth doing then as a real end-to-end check of
rendering in an actual client, but there's no reason to attempt it while sends are 401ing.
