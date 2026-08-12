# Packaging EPR — Practitioner Workflow, Data Reality, and Vendor Landscape

**Research pass:** 2026-08-11 · **Method:** web research across vendor material, regulator publications,
law-firm post-mortems and practitioner interviews reported in trade press. · **Status:** point-in-time
snapshot, not maintained.

> **How to use this.** This is the brief that changed the product thesis: it argues that a fee
> calculator is the wrong headline feature. Where the source is inference rather than citation, it says
> so. The honest headline: **a great deal of this genuinely is spreadsheets and email**, and the most
> credible sources — including vendors' own marketing and a regulator's post-mortem — say so.
>
> Drove §0, §6 and §9 of `docs/EXPOSURE_CALCULATOR_SPEC.md`.

---

## 1. The job: the annual cycle

### The structural fact that shapes everything

Amanda Humes, Director of Packaging Stewardship at Conagra, on what the job actually is:

> "figure out how to actually take the individual EPR fees that are assessed on **2023 data, reported in
> 2024, paid in 2025**"

That three-year lag between *placing packaging on market* → *reporting it* → *paying for it* is the
defining feature. Confirmed structurally by CAA's own cycle: Oregon **2025 Data Year → 31 May 2026 report
→ January 2027 payment → Program Year 2027**. The UK is the same shape — 2024 data drove invoices issued
October 2025.

**Implication for tool design:** any product showing "your current EPR cost" is showing three different
years at once. The data year, the reporting year and the cash year are all live simultaneously, and
finance, compliance and procurement each care about a different one.

### Realistic annual cycle for a multi-market QSR

| Period | Activity | Where time goes |
|---|---|---|
| **Jan–Feb** | France Citeo/Citeo Pro declaration window (**1 Jan – 28 Feb**, prior year). Germany LUCID reconciliation. | France demands **per-unit weight in grams × units placed**, per material, per product category — the most granular ask in any market. |
| **Feb–Apr** | UK H2 data submission (**1 April**). US registration/reporting prep. | Chasing supplier spec sheets. The bulk of the year's effort. |
| **15 May** | Germany **Vollständigkeitserklärung** deadline — audited, **cannot be extended**. | External auditor coordination. |
| **31 May** | US common deadline — six of seven states converged on **31 May 2026** for 2025 data. Also Maine, Ontario supply data. | Producer-status determination per state per SKU per channel. |
| **Jun–Sep** | Fee schedules published; internal budget cycle; procurement re-spec. | Modelling next year's exposure against packaging changes. |
| **Oct** | UK pEPR invoices issued (RPD portal). UK H1 data submission. | Reconciling invoice vs accrual. |
| **Nov–Jun** | Payment: UK either in full within **50 days** or four instalments (Nov/Jan/Apr/Jun). France quarterly if contribution >€5,000. | Finance true-up. |
| **Continuous** | Resubmission/recalculation windows, regulator queries, audits. | UK now restricts these to **July, November, March/April**, with a hard stop. |

### Where the time actually goes

Not the arithmetic. Three places:

**1. Determining whether you're obligated at all.** Holland & Knight's post-mortem of the first US
consolidated reporting round found producers "caught off guard with deadlines with little time to conduct
a full applicability analysis." Venable puts it precisely: *"determining 'who the Producer is' is not a
one-time answer, and it can vary by SKU, brand, sales channel, and state."* For a QSR this is genuinely
hard — the California Restaurant Association notes the **"restaurant, franchisor, franchisee, purchasing
cooperative, or brand owner may be treated as the 'producer'"**, and franchise structures require
case-by-case assessment.

**2. Getting component-level packaging weights out of suppliers who don't owe them to you.** Universally
cited as the bottleneck.

**3. Classification judgement calls.** UK household vs non-household is the clearest example, and
gov.uk's own worked example is *literally a fast-food chain*: dine-in packaging (20% of orders) must be
classified **household** because "the consumer is the final user of the packaging not a business."
Meanwhile bulk ingredients delivered to the restaurant kitchen, where packaging is discarded before
serving, can be non-household. **The same chain, same week, splits both ways.**

### What goes wrong — with evidence

- **Data revisions blow holes in the scheme, not just the producer.** PackUK ran a **£63m shortfall** in
  year one, attributed to "subsequent producer resubmissions and significant shifts in obligated
  tonnages" that "exposed financial risks and highlighted the need for stronger data controls."
- **Getting it wrong is now directly priced.** UK 2026: **£2,548** charge for data resubmission; **£386**
  late registration; large producer registration **£2,842**; and — critical for QSR groups — **£690 per
  subsidiary for the first 20**, £172 for 21–100.
- **Penalties are asymmetric and large.** UK late payment: greater of 20% of unpaid fees or **5% of UK
  turnover**. Germany: **€100,000** for a missing/incorrect VE. California: up to **$50,000/day per
  violation**. Oregon: Class 1 violation, up to **$25,000/day**.
- **Estimation cuts both ways.** GA Institute: producers relying on estimation "risk overpayment of
  fees." Under-report and you get back-billed; over-report and you simply pay more, forever, silently.

---

## 2. The data problem

### Where the data comes from — and the QSR-specific trap

For a CPG company the chain is ERP → PLM → packaging specs. For a restaurant chain it is materially
worse, because **the packaging is not a product you make; it is a thing you buy in cases and hand to a
customer.**

Sources, roughly in order of reliability:

1. **Supplier specification sheets** — the gold standard, PDF or Excel, per SKU, per component. Rarely complete.
2. **Distributor purchase reports** — cases purchased by DC, by period. Abundant and reliable *as a
   volume signal*, but contain **no packaging weights**.
3. **Procurement / ERP systems** — case counts and spend, not grams.
4. **GS1 / GDSN** — the one genuine standard (below).
5. **Physical weighing** — the fallback nobody wants.

**A concrete and telling finding:** Bidfood, a major UK foodservice distributor, explains on its EPR page
*who is obligated* and points customers to their compliance scheme — and provides **no packaging data, no
format, and no tonnage conversion methodology**. Their answer is "contact your account manager."

So the restaurant has the case counts and doesn't have the weights; the distributor has neither obligation
nor product to give them. **That gap is the business.**

**Inference (clearly flagged as such):** the practical conversion for a QSR is
`cases purchased per market × units per case × grams per component per unit ÷ 1,000,000 = tonnes`, and
the *only* genuinely hard term is grams-per-component. Everything else the company already has in procurement.

### Cases → tonnes: what the rules actually permit

There is **no published standard methodology**, and this was searched for specifically — it does not
exist as a canonical artefact. What does exist:

- **CAA** tells producers to "select the best available methodology" — and does not prescribe one. Its
  detailed guidance is **gated behind signing the Participant Producer Agreement**, so you cannot read
  the requirements before committing.
- **France permits explicit simplifications**: litres = kilograms for volume-to-weight, and **mean unit
  weight** for variable-weight products (meat, fish).
- **UK** requires data "as accurate as reasonably possible."
- **Vendors fill the gap with proprietary extrapolation.** Ecoveritas' "Factors" derives average packaging
  weights per product category so businesses need not contact suppliers at all — cross-referenced against
  a 3M+ SKU database. Valpak's Global Data Insights uses a **60–65M SKU** reference dataset.

**Skeptical note:** none of these vendors publish sample sizes, category granularity, or error bounds.
Ecoveritas' language is that "all extrapolation assumptions are documented for audit transparency" —
documented *to the client*, not to the market. Given PackUK now charges **£2,548** per resubmission and
has flagged data controls as the cause of a £63m shortfall, **estimate quality is becoming a priced
liability that no vendor quantifies.**

On **waste/spoilage, inter-market transfers, and opening/closing stock**: no authoritative published
guidance found in any market. Germany's VE audit guidelines do test "volume transfers between producers,
zero-sum and retrospective transfers." Ontario's RPRA changed its **ineligible-source deduction guidance
in May 2026** — and deduction methodology is exactly what a verifier tests. Beyond that this appears
genuinely unsettled and handled by local judgement.

### Is there a standard data exchange format? Yes — one, and it's underused

**GS1 GDSN is the real answer**, with a proof point: **Sysco pulled packaging sustainability attributes
from GS1's Global Data Synchronisation Network**, combined them with internal taxonomy, and used **GTINs
at each packaging hierarchy level** to carry material type, weight, and state-specific EPR
classifications — *without needing separate datasets per state*. They then hired a dedicated packaging
engineer.

Sysco's own characterisation of supplier readiness is the important part: **some suppliers (chemicals,
disposables) have better packaging data infrastructure than Sysco itself; smaller regional brands have
essentially none.** They had to build guardrails so suppliers couldn't enter wrong data.

Also live:

- **GS1 in Europe** publishes *"Packaging – Overview of data attributes to answer PPWR requirements"*
  (XLSX) and a **GDSN Implementation Guide for Packaging**.
- **GS1 PPWR Template** (Forum Rezyklat + GS1 Germany) — free, expected August 2026.
- **Sustainable Packaging Data Council (SPDC)** has a US EPR data requirements framework covering
  product-, component- and sales-level fields. ⚠️ SPDC's own site returned 403 — treat as needing verification.

---

## 3. Audit and evidence

The critical strategic insight: **audit regimes differ so fundamentally by market that "audit-ready" is
not one feature.**

| Market | Who verifies | Trigger | Retention | Penalty |
|---|---|---|---|---|
| **UK** | **No independent audit.** Self-certification by an EA-approved person (director/company secretary) | All large producers | **7 years** | Unlimited fine; variable monetary penalties |
| **Germany** | Auditor/tax adviser/sworn accountant **registered in LUCID**, independent | **80t glass / 50t paper / 30t lightweight** | Not stated | **€100,000** for missing/incorrect VE |
| **France** | Independent audit firm **appointed and paid by Citeo** | **Random draw by a huissier** — not threshold-based | Not found | Referral to DGPR → ministerial sanction |
| **Spain** | Auditor agreed-upon-procedures report on Ecoembes declarations | Ecoembes affiliates | **5 years** | Law 7/2022 regime |
| **Netherlands** | Accountant assurance report — **on request, not automatic** | 50,000 kg total | Not found | Not found |
| **Ontario** | Independent auditor under Public Accounting Act 2004 | **Deferred to 2027** (on 2026 data) | **5 years** | AMPs, **published publicly** |
| **California** | Producers appear to require an independent third-party auditor (14 CCR ~§18687) — *low confidence* | — | **5 years**; records within **10 days** of request | SB 54 penalties |
| **Oregon / Minnesota / Maine** | **No producer-report third-party audit found.** Audits attach to end markets or PRO financials | — | Not located | OR: **$25,000/day** |

**The UK/Germany contrast is the sharpest.** The UK requires a *director's signature* and seven years of
records with no external audit. Germany requires an *externally attested* declaration by **15 May**,
deadline non-extendable, where deviations must be **quantified by material type and mass** — a
self-reported reconciliation of under-declaration.

**What happens in a challenge:**

- **UK:** a reg. 110 notice compels named records, and can be served on someone the agency *merely
  believes* is obligated. For PRN/PERN disputes the pack is physical: weighbridge tickets, duty-of-care
  transfer notes, invoices, Annex VII forms, **time-stamped photographs**, proof of payment.
- **France:** 3 months to complete, 1–2 days on site, sampled product references notified in advance.
  Corrections go to the *audit firm*, not Citeo — 3 months for simple, **12 months where the declaration
  process must be rebuilt**. Company may file a *rapport contradictoire*.
- **Ontario is the only market with a public enforcement record** — RPRA publishes **110+ compliance and
  administrative penalty orders** by company name, and penalties can expressly **recover economic benefit
  from non-compliance**, i.e. statutory back-billing.

*Unverified: Italy/CONAI (403), Colorado (403 + unparseable PDF), French and German retention periods,
and the California section numbers.*

---

## 4. The competition

### The incumbents

**Ecoveritas (UK)** — packaging-data **consultancy with a portal**, not a PRO. Differentiator is the
**Factors** extrapolation methodology (average weights per category, avoiding supplier contact). Real
regulatory credential: first EA-approved packaging compliance methodology for online marketplaces. Claims
80+ countries; independent comparison says **30+ with EU "in development"** — a material discrepancy.
Clients are large UK retail (John Lewis, Waitrose, Selfridges, Harrods) despite SME-facing "EPR in days"
messaging. **No pricing published. Zero G2/Capterra/Trustpilot presence.**

**Valpak / Reconomy (UK)** — **a PRO first**, wrapped in consultancy. UK's largest scheme, ~4,000
businesses; absorbed Ecosurety's WEEE/batteries schemes. **Global Data Insights** launched April 2026 on
a 60–65M SKU dataset (customer: Tesco). But it ships with "dedicated support to engage with suppliers on
your behalf" — independent read: *"Not self-serve software; you hand over data rather than retain
control."* A Trustpilot reviewer calls the submission system **"very labour intensive and user unfriendly
in comparison to other compliance schemes."** Fee *taxonomy* published; rates are not.

**Lorax EPI** — **closest to a genuine pure-play SaaS**; platform is **ENVI™**. *Note: no product called
"Chameleon" could be verified — treat that name as an error.* 200+ schemes, 1bn+ transactions. In the
Assent partnership, **Assent does supplier data collection, Lorax does the jurisdiction reporting files
and fee calculation** — a clean signal that Lorax's IP is the reporting engine, not supplier-chasing.
Enterprise pricing, **4–6 month onboarding** (longest found). Clients: Colgate, Newell, Pentland.

**Comply Direct → now Beyondly.** *Correction: rebranded March 2023.* Consultancy that also runs a PRO;
UK core; ~1,700 members (unverified). Not a software vendor.

**"Ecobat / Verity"** — **could not verify either exists in packaging EPR. Recommend dropping from the
competitive set.** Ecobat is a lead/battery recycler; "Verity" appears to be a garbled recollection of
Eco*veritas*.

**Sphera (EC4P)** — enterprise product-stewardship suite; packaging EPR is one module, openly a **managed
service**. 330–360+ schemes. Genuine differentiator no UK vendor matches: **consolidated single invoice**
across obligations, and they pay fees on your behalf. Weakness: packaging isn't broken out from
WEEE/batteries, and the customer base is electronics/pharma (FLIR, Takeda, Thermo Fisher) — a WEEE-shaped
book being sold packaging as an add-on. **Only vendor with real review data: G2 4.0/5 on 11 reviews**,
criticising UI learning curve and implementation complexity.

### Newer software entrants

| Vendor | Type | Coverage | Pricing |
|---|---|---|---|
| **Recyda** (DE) | Software; **€6.3M Series A** (Cusp Capital) | 20+ countries | Not published |
| **Repax** (DK) | Software, self-serve | 30+ EPR categories | **Free / €29 / €59 per month** |
| **ecosistant** (DE) | Software + consulting | EU27 + UK/NO/CH | **DE free; from €24.90/country** |
| **EPR Insights** | Software | European packaging | **~$15/month** |
| **Packgine** (US) | Software, AI-positioned | CA/CO/ME/MD/MN/OR/WA + EU27/UK | Not published |
| **Unpac** (US) | Software — **automated supplier outreach** | Undisclosed | Not published |
| **PCX Markets** | Software + service | **49+ markets** inc. APAC, Turkey, Kenya, ZA | Not published |
| **Assent** | Enterprise SaaS; ~$1.3B valuation | North America (EPR domain **licensed from Lorax**) | Not published |

**Discarded — could not confirm in packaging EPR:** Verdis, Enviu, Circulate, Tundra, Packaging
Collective, Recycle Track Systems, Ecodrive, Greenly, Sustained. **Reath** (reusable-packaging
traceability) and **cirplus** (recycled-plastics marketplace) are real but wrong category. **Sourcemap**
is supply-chain mapping. **Compliance & Risks is now "Adherent"** and does *not* list packaging EPR —
it's a know-the-rule layer, not a file-the-return layer. **Ecochain** does not mention EPR at all on its
product page.

### The free competitor: PRO portals

Under-appreciated and commercially important.

- **Citeo (France)** has three tiers: **<10,000 CSUs → flat fee, "no figures are required," €80/yr**;
  <500,000 CSUs → simplified declaration on 64 product families, **"no detailed data is required"**;
  500,000+ → full declaration mandatory. Plus declaration **simulators**. Citeo has *removed the data
  problem entirely* below 500k CSUs.
- **Der Grüne Punkt (Germany)** does **automatic transfer of sales quantities from ERP** and solves the
  dual DGP/LUCID reporting problem in one go — free.
- **CAA (US)** is a submission endpoint, not a data system. It takes your numbers; it does not source them.

### Where the genuine gap is

**The crowded layer is fee calculation and report generation, and it is commoditising fast.** Twenty-plus
vendors in one directory make near-identical claims. The pricing spread across identical claimed
functionality — **$15/month to demo-gated enterprise** — is what a category looks like just before margins
compress.

Four real gaps:

1. **The upstream data problem.** Every credible source says obtaining component-level weights from
   suppliers is the barrier — Assent's own blog, CAA's post-mortem, Sysco's experience, EY's year-one
   findings. **Unpac is the only vendor whose core pitch is automated supplier outreach, and it is the
   least-funded and least-disclosed company on the list.** The industry has built twenty calculators for a
   problem that is fundamentally about getting the inputs.
2. **Applicability determination.** *Am I the producer here, for this SKU, in this state, through this
   channel?* Fourteen major law firms have built practices around this question. **Zero software vendors
   address it** — every platform assumes you already know you're obligated. And CAA's detailed guidance is
   behind an agreement you must sign before you can read it.
3. **Honest coverage claims.** Nobody distinguishes *"we monitor the regulation"* from *"we can register
   you"* from *"we can file the return."* Ecoveritas says 80+ countries, independent review says 30+.
   Valpak says 195 countries but delivers via partnerships. That three-state distinction, published per
   jurisdiction, would be the most useful competitive artefact in the market.
4. **Foodservice/QSR — verified vendor coverage is zero.** Searched from multiple angles. The obligation
   demonstrably reaches restaurant chains (SB 54 covers single-use plastic foodservice ware; gov.uk's
   household/non-household worked example is a fast-food chain). The nearest thing is **FoodChain ID +
   Unpac**, and it targets food *manufacturers*, not operators. Searching "QSR compliance software"
   returns food-*safety* tools.

Also worth noting: **there is essentially no third-party evidence base.** Buyers choose between enterprise
commitments using nothing but vendor self-reported stats ("97% satisfaction," "100% compliance success
rate," "195 countries").

---

## 5. The output that matters

Four audiences, four genuinely different artefacts.

**For the regulator / PRO — the submission.** Format is market-specific and non-negotiable:

- *UK:* tonnage by material × **household/non-household** × **nation (4-way)** × RAM RAG rating, signed by
  an EA-approved person.
- *France:* **units × grams per material per unit**, by product category — per SKU above 500k CSUs.
- *Germany:* volumes by material, identical to what was reported to the dual system, plus the **audited VE
  by 15 May**.
- *US:* material category weights by state, per CAA's chosen methodology.

Plus the **methodology statement** — CAA's post-mortem cited "inadequate methodology sections" as a named
failure.

**For finance — the accrual schedule.** Needs: annual shipped tonnage by material and state, PRO fee
rates, eco-modulation adjustments, translated to a **monthly run rate** applied to actual volume, with
quarterly reconciliation and **documented assumptions for audit traceability**. The driver: *"PRO invoices
will not arrive monthly. They will come in periodic lump sums tied to prior-year tonnage."* Without this,
quarterly financials swing and you book "large, reactive true-ups that undermine confidence."

**For the board/ESG — exposure and trajectory.** Total fee exposure by market, YoY, plus the modulation
story (what proportion of portfolio is red/amber/green), plus recycled content. Packaging is **10–30% of
COGS**; failure to reprice early costs **50–200 basis points of margin**.

**For procurement — the per-SKU fee delta.** The one output that changes behaviour. Conagra's practice:
put EPR fees on **the P&L of the products that cause them**, not into an EPR bucket, because "those
individual brands and SKUs have to be accountable for those dollars." EY cites an Oregon redesign
achieving **~85% fee reduction**. Fees belong in **should-cost models alongside material and conversion
cost**, as a live sourcing input — not a compliance forecast run once a year.

---

## 6. KISS test

### Minimum viable — day-one useful

1. **A packaging component library keyed to purchasing identifiers.** Component → material → grams,
   joined to the SKU/GTIN the chain already buys on. Everything else is a view over this table. Use GDSN
   where the supplier publishes it.
2. **Cases → tonnes conversion with the assumption stack visible and editable.** Units per case, grams per
   component, market allocation — each with a provenance flag: *measured / supplier-declared / GDSN /
   estimated from category*. **This is the product.** Nobody exposes uncertainty, and uncertainty is now
   priced at £2,548 per resubmission.
3. **Supplier data chase-up with response tracking.** Sysco's lesson: **build guardrails so suppliers
   can't enter wrong data.** The gap-list ("47 SKUs missing lid weight, 12 suppliers unresponsive 30
   days") is more valuable than any dashboard.
4. **A classification rules engine for the judgement calls, with the reasoning recorded.** UK
   household/non-household above all — the dine-in-vs-takeaway split is a per-channel percentage,
   defensible only if the evidence sits next to it for seven years.
5. **The three-clock view.** Data year / report year / cash year, side by side. Everyone else conflates them.
6. **Deadline and obligation calendar with per-entity registration state.** Including subsidiary
   registrations at £690 each.
7. **Immutable submission snapshots.** What was submitted, on what data, under what assumptions, signed by
   whom. The single artefact that survives a reg. 110 notice or a Citeo *contrôle*, and what makes the
   resubmission windows navigable.

### Genuinely useful and cheap: applicability triage

Given zero vendor coverage and fourteen law firms feeding on the ambiguity, a *"are you the producer
here?"* decision tree per market × channel × brand-ownership — recorded, dated, and re-runnable when the
structure changes — would be disproportionately valuable. Especially for franchised QSR, where
franchisor/franchisee/co-op allocation is unresolved.

### Noise — commonly built, low practitioner value

- **Another fee calculator as the headline.** Commoditised, and free below Citeo's 500k CSU threshold and
  inside Der Grüne Punkt's ERP transfer.
- **Regulatory horizon-scanning feeds.** Adherent, law firms and the PROs already flood this.
  Practitioners don't lack awareness; they lack grams.
- **ESG/sustainability score dashboards.** Different buyer, different budget; dilutes the compliance value
  proposition.
- **LCA / carbon footprinting.** Adjacent. Shares the BOM data but answers a different question.
- **"195 countries" breadth claims.** Coverage that doesn't survive contact is a liability once a customer
  tries to file.
- **Auto-submission to portals.** Tempting, but CAA's portal is gated, Citeo's is designed for direct
  producer use, and the resubmission-window regime means the *correction* path matters more than the
  *submission* path.

### The sharpest positioning read

The defensible wedge is **(a) foodservice/QSR as a named vertical, where the obligation is real and vendor
coverage is verifiably zero; (b) the cases-to-tonnes conversion with auditable, quantified uncertainty —
the thing every incumbent does behind a curtain; and (c) applicability determination, which nobody sells.**
Not another reporting engine.

---

## Sources

[Ecoveritas](https://www.ecoveritas.com/services/data-calculation) ·
[Valpak invoicing](https://www.valpak.co.uk/packaging-epr-fees-invoice-guide/) ·
[Valpak GDI launch](https://www.packagingnews.co.uk/news/environment/valpak-launches-global-epr-platform-14-04-2026) ·
[Lorax ENVI](https://www.loraxcompliance.com/blog/envi.html) ·
[Assent EPR launch](https://www.assent.com/newsroom/assent-unveils-extended-producer-responsibility-packaging-solution-to-simplify-compliance-with-expanding-packaging-laws/) ·
[Assent on data barriers](https://www.assent.com/blog/packaging-epr-compliance-challenges/) ·
[Sphera EC4P](https://sphera.ec4p.com/platform/managed-services) ·
[Recyda Series A](https://www.vestbee.com/insights/articles/recyda-raises-6-3-m) ·
[Repax pricing](https://www.repax.io/blog/lorax-epi-alternatives) ·
[ecosistant](https://www.ecosistant.eu/en/) ·
[PCX Markets](https://www.pcxmarkets.com/epr-packaging-compliance) ·
[Unpac](https://www.getunpac.com/) ·
[FoodChain ID](https://www.foodchainid.com/products/extended-producer-responsibility/) ·
[CAA producer reporting](https://circularactionalliance.org/producer-reporting) ·
[Holland & Knight post-mortem](https://www.hklaw.com/en/insights/publications/2026/07/2026-epr-reporting-lessons-learned-initial-consolidated-reporting) ·
[Citeo membership tiers](https://www.citeo.com/en/my-membership/) ·
[Citeo Pro foodservice FAQ](https://www.citeopro.com/faq-emballages-de-la-restauration/) ·
[Citeo contrôles](https://www.citeo.com/vos-controles-reglementaires/) ·
[Der Grüne Punkt](https://www.gruener-punkt.de/en/packaging-licensing/sales-packaging) ·
[ZSVR declaration of completeness](https://www.verpackungsregister.org/en/system-participation-data-reporting/declaration-of-completeness) ·
[§36 VerpackG](https://www.gesetze-im-internet.de/verpackg/__36.html) ·
[gov.uk household/non-household](https://www.gov.uk/guidance/extended-producer-responsibility-for-packaging-how-to-assess-household-and-non-household-packaging) ·
[gov.uk data collection](https://www.gov.uk/guidance/how-to-collect-your-packaging-data-for-extended-producer-responsibility) ·
[PRO Regs 2024 reg. 34](https://www.legislation.gov.uk/uksi/2024/1332/regulation/34/made) ·
[PackUK £63m shortfall](https://www.letsrecycle.com/news/packuk-confirms-shortfall-as-63m-announces-year-2-recovery-target/) ·
[2026 pEPR charges](https://www.letsrecycle.com/news/provisional-pepr-charges-for-2026-published/) ·
[RPRA verification deferral](https://rpra.ca/2024/11/blue-box-producers-will-not-be-required-to-submit-verification-reports-when-submitting-supply-reports-in-2025-and-2026/) ·
[RPRA compliance orders](https://rpra.ca/compliance/) ·
[Packaging Dive: budgeting frontlines](https://www.packagingdive.com/news/extended-producer-responsibility-packaging-managing-costs-csuite-spc/818742/) ·
[CF Team: EPR and the P&L](https://www.thecfteam.com/insights/pandl) ·
[Venable: new P&L line item](https://www.venable.com/insights/publications/2026/03/cpg-brands-meet-your-new-p-and-l-line-item) ·
[EY EPR strategy](https://www.ey.com/en_us/insights/climate-change-sustainability-services/extended-producer-responsibility-and-packaging-strategy) ·
[GS1 Europe packaging](https://gs1.eu/activities/packaging/) ·
[Sysco data strategy](https://www.packworld.com/trends/logistics-supply-chain/article/22968796/master-epr-compliance-syscos-data-strategy-guide) ·
[Bidfood EPR](https://www.bidfood.co.uk/extended-producer-responsibility/) ·
[California Restaurant Association SB 54](https://www.calrest.org/epr-sb-54) ·
[GA Institute data prep](https://ga-institute.com/Sustainability-Update/preparing-your-packaging-data-for-epr-compliance/)
