# EU + Member-State Packaging Compliance — Multi-Country QSR Chain

**Research pass:** 2026-08-11 · **Method:** primary-source research (EUR-Lex, national competent
authorities, PRO tariff documents). The 200-call web-search cap was exhausted; direct fetches of BOE,
CONAI, Repak, Legifrance and the Irish Statute Book still worked. · **Status:** point-in-time snapshot.

> **Critical timing note:** this pass was run on 11 August 2026 — **PPWR and Germany's VerpackDG both
> applied from the next day, 12 August 2026.** Several answers differ before/after that date.
>
> Encoded into `app/scoring/producer_attribution.py` (FR, DE, ES, IT, IE, NL entries). See
> `docs/EXPOSURE_CALCULATOR_SPEC.md`.

**One framing correction that changes the data model:** "what's the EPR fee per tonne" is the wrong
primitive in four of six countries. France bills food service **per consumer sales unit and per
delivered order**; the Netherlands bills a **per-1,000-unit** SUP surcharge; Germany stacks a
**per-kilogram federal levy** and a **per-item municipal tax** on top of the tonnage fee; Spain layers a
**per-kilogram tax** that is not EPR at all. Tonnage is one input among five.

---

## Cross-cutting EU layer

### PPWR — Regulation (EU) 2025/40 (citation verified)

Entered into force **11 February 2025**; applies from **12 August 2026**; repeals Directive 94/62/EC
from the same date. ([EUR-Lex](https://eur-lex.europa.eu/eli/reg/2025/40/oj/eng),
[Gleiss Lutz](https://www.gleisslutz.com/en/know-how/new-eu-packaging-regulation-key-requirements-august-2026))

| Date | Article | Obligation |
|---|---|---|
| 12 Aug 2026 | 44 | Producer registration is the **market-access gate** — no registration, no placing on market, per Member State |
| 12 Aug 2026 | 45(3) | **Authorised representative for EPR** mandatory for producers not established in the Member State |
| 12 Aug 2026 | 5 | PFAS restrictions in food-contact packaging |
| 12 Feb 2027 | 32 | HORECA must let customers **bring their own container**, no extra cost |
| 12 Feb 2028 | 33 | HORECA take-away must **offer a reusable option** within a reuse system |
| 12 Aug 2028 | 12 | Harmonised material-composition labelling (or 24 months from the implementing act) |
| 1 Jan 2029 | 50 | **Mandatory DRS** for SUP beverage bottles and metal containers ≤3 L; exemption if ≥80% separate collection in 2026, notified with a plan by 1 Jan 2028 |
| 1 Jan 2030 | 25 + Annex V | **Annex V format bans**, incl. single-use plastic packaging for food/drink **filled and consumed on HORECA premises**, and single-portion condiments/sugar/creamer |
| 1 Jan 2030 | 29(6) | **10% of beverages** in reusable packaging at final distributors; 40% by 2040 |
| 1 Jan 2030 | 7 | Recycled content: 30% contact-sensitive PET · 10% contact-sensitive non-PET · 30% SUP beverage bottles · 35% other plastic |
| 1 Jan 2040 | 7 | 50% · 25% · 65% · 65% |

A **Commission Notice (guidance) published 5 June 2026** clarified that "making available" under Art.
29(6) means final distributors — restaurants and bars — carry the 10% beverage reuse target directly,
and that B2B kegs do not count toward it.
([Packaging Europe](https://packagingeurope.com/news/diving-deeper-into-the-eus-latest-guidance-on-the-ppwr/14387.article))

> ⚠️ **Two live uncertainties — build as flags, not constants.** (1) The Commission **proposed in
> December 2025 suspending the Art. 45 AR obligation** — models discussed include limiting it to non-EU
> firms or to firms above 50 employees / €10m turnover, possibly until 2034. Undecided; the obligation
> is live. (2) 30+ implementing/delegated acts run through 2029; Verpact is openly telling businesses to
> "provisionally continue with the situation as it applied before 12 August."

### SUPD Article 8 (Directive (EU) 2019/904)

Annex **Part E Section I** carries the **full** cost-coverage burden — awareness raising **plus** waste
collection from public bins including infrastructure and operation **plus** litter clean-up and onward
transport/treatment. Section I items are exactly the QSR set: **food containers for immediate
consumption, packets and wrappers, beverage containers ≤3 L, beverage cups, lightweight plastic carrier
bags.** Deadline **31 December 2024** generally; **5 January 2023** for wrappers and pre-existing
schemes. ([EUR-Lex 2019/904](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32019L0904))

**Is it a separate levy? It depends entirely on the country — the single most-often-modelled-wrong item:**

| Country | Mechanism | Separate from packaging EPR? |
|---|---|---|
| **France** | Per-UVC line **inside** the Citeo tariff | **No** — embedded |
| **Spain** | ~**+€0.011/kg** "SUP" variant on every Ecoembes material rate | **No** — embedded |
| **Netherlands** | Verpact **SUP-opslag, €2.10 per 1,000 units** (2026) | Partly — separate line, same invoice |
| **Germany** | **EWKFondsG levy paid to the Umweltbundesamt** | **Yes — separate authority, registration and payment** |

---

## FRANCE

**Headline correction:** the main exposure is **not** the "emballages de la restauration" stream.
Packaging handed to a consumer for takeaway or delivery is **household packaging (emballages ménagers)**
in French law, and the household stream is billed **per UVC, not per tonne**.

### Registration

- **IDU** — 15-character identifier generated by ADEME/SYDEREP, delivered via your éco-organisme within
  ~5 days of adhesion, **one per REP filière**. A QSR chain holds several (ménagers, papiers graphiques,
  professionnels/restauration, plus DEA furniture, DEEE kitchen equipment, TSUU).
  ([ADEME](https://filieres-rep.ademe.fr/en/identifiant-unique))
- Must appear in **CGV, contractual documents and on the website**. Legal bases: arts. L541-10-13,
  L541-10-10, L541-10-9, L541-9-5 C. env. (loi AGEC 2020-105 art. 62), in force **1 Jan 2022**.
- **Penalty confirmed: administrative fine up to €30,000** (art. L541-9-5), **plus astreinte up to
  €20,000/day**.

**Mandataire — YES, and this changed on 10 July 2026.** New **art. L541-10-9-1 C. env.** requires *any*
producer not established in France — EU or third country — to appoint a French-established *mandataire*
by written mandate, **subrogated into all EPR obligations, across all filières including packaging**.
([Legifrance](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000054403121/2026-07-10)) A chain
operating through a French subsidiary that places the packaging does **not** need one — the subsidiary
is the producer.

### Which stream

France created a separate food-service stream (launched March 2024, Citeo Pro, arrêté 20 July 2023) —
now being absorbed into a broader **EPRO professional-packaging stream** (décret 2025-1081 of 17 Nov
2025; Citeo Pro / Léko Pro / Twiice agréés 5 June 2026).
([ADEME EPRO](https://filieres-rep.ademe.fr/filieres-REP/filiere-EPRO))

**The chain pays into both.** Household for everything handed to the consumer; EPRO for B2B flows.

> ⚠️ **Unresolved conflict:** the Ministry says EPRO obligations apply **from 1 January 2027**
> (postponed from 1 July 2026); Citeo Pro's own June 2026 deck is already invoicing an
> "Éco-contribution 2026 = S2 2026." Confirm directly with Citeo Pro.

### Tariffs (2026)

**Citeo Pro / EPRO, €/tonne:** steel 30.20 · aluminium 16.80 · paper-board 40.90 · **plastic 221.10** ·
wood 14.40 · other 14.40. Below 4 t/yr: flat **€145** for H2 2026.
([tariff PDF](https://www.unfea.org/wp-content/uploads/2025/12/CITEO-PRO-offre-et-tarif-11-Juin-2026.pdf))

**Citeo household (the one that matters)** — contribution = (weight × material rate) + per-UVC rate +
litter component + réemploi component, then eco-modulated. Selected 2026 rates in centimes/kg: rigid
PE/PP 77.01 · rigid PET 84.01 · rigid PS/XPS/PSE 80.51 · flexible PE 77.01 · flexible PP 84.01 ·
complexes/other resins 140.01 · **PVC 210.01** · compostable plastic 84.01 (new for 2026) · steel 6.49 ·
aluminium 24.34.

**"Restauration livrée" is priced per ORDER, not per tonne** — seven menu-type codes ranging **€0.0676
to €0.1829 per delivered order**. For a burger chain, budget **~€0.15–0.18/order**. ⚠️ The
code→value mapping beyond "Street Food = 0.1829" could not be confirmed from the PDF text layer; the
range is solid.

Also: **€110 HT minimum billing** on the household contract; **réemploi component 0.0140 ct/UVC** (new 2026).

### Eco-modulation — actual 2026 bands

**Malus:** metallised cartons on all faces **10%** · small beverage formats ≤0.5 L **25%** (up from 10%)
· promotional bundling films **25%** · density mismatches in rigid bottles **50%** · PETg/PLA/PS sleeves
**50%** · aluminium/PVC/silicone associations **100%** · **dark plastics undetectable by optical
sorting, notably carbon black, 100%** · non-soda-lime glass **100%** · glass with non-magnetic steel
closure **100%**. Maluses cumulate *across* levels, not within.

**Bonus:** réemploi (new reusable) **100%** · reduction bonus **proportional to weight reduced** ·
**sensibilisation 4%** (requires real media thresholds: ≥275 GRP TV with ≥3s on screen, ≥1,000 GRP
outdoor, ≥150 GRP press) · Prime Ressources for recycled plastic content in €/kg (⚠️ 2026 arrêté amounts
unverified). Separate **10% décote** for paper-board with >50% recycled fibre.

**Five maluses were removed for 2026** — including the **opaque PET malus** and the PVC bottle malus.
Note for anyone porting last year's rules.

### SUPD Art. 8 in France — embedded, per UVC

Labelled *"contribution au financement du recyclage des déchets abandonnés"*, calculated **per sector by
real litter share** and scaling with the **number of packaging units (UE) per UVC**. Beverages, 2026:
0.1722 ct at 1 UE → 0.6544 ct at 5 UE → 1.4293 ct at 20 UE. New 2026 band for ultra-light units <0.1 g
(0.0062–0.0087 ct) — relevant to sauce sachets and straws. Basis:
[arrêté du 30 septembre 2022](https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000046383895), Ch. IV.7,
in force 1 Jan 2023.

**This is why UE-count matters more than tonnage:** a burger meal — box, cup, lid, straw, bag, sauce
sachet — is 6+ UE on one UVC, multiplying the litter component ~4–5× versus a single-unit item.

### Labelling and AGEC bans

- **Triman + Info-tri**: décret 2021-835, arts. R541-12-17 to -24 C. env. **Mandatory since 1 Jan 2022**.
  Explicitly covers professional/catering packaging. **>20 cm² → physical marking required** (most cups
  and boxes). Sanction reported at €15,000 for a legal person — ⚠️ not confirmed on Legifrance.
- **Reusable tableware for dine-in — in force 1 Jan 2023**, art. D541-342 C. env. Scope: establishments
  seating **or standing ≥20 people**. Applies to disposables of **any** material — cardboard and
  compostable equally banned. Takeaway exempt. Per the government's answer to
  [Question écrite AN n° 4425](https://questions.assemblee-nationale.fr/q16/16-4425QE.htm): fine **up to
  €15,000 plus astreinte up to €1,500/day, cumulative across a chain's non-compliant sites**, with large
  chains explicitly prioritised for enforcement.
- ⚠️ Unverified: plastic kids'-menu toys ban and free-plastic-water-bottle ban (believed AGEC art. 77).

**PPWR is changing who the producer is in France:** Citeo flags that from 2026 *"donneurs d'ordre sont
systématiquement considérés comme les producteurs"*, ending the French exception where the manufacturer
declared private-label packaging. A chain that relied on suppliers declaring its branded packaging **now
declares it itself** — a step-change in declared volume.
([Citeo](https://www.citeo.com/le-mag/economie-circulaire-et-rep-ce-qui-change-en-2026/))

---

## GERMANY

### Registration and the service-packaging mechanic

- **LUCID** registration with ZSVR is **free**; requires all brand names appearing on packaging. §9
  VerpackG; the register is public. Fines: **up to €100,000** for failure to register, **up to €200,000**
  for failure to participate in a system (§36).
  ([ZSVR](https://www.verpackungsregister.org/registrierung/alle-informationen-zur-registrierung),
  [§36](https://www.gesetze-im-internet.de/verpackg/__36.html))
- **Serviceverpackungen** = packaging first filled at the final distributor — expressly includes
  restaurant containers. Key test: filled **at or near the retail location**. Centrally filled and
  trucked to branches = ordinary sales packaging.
  ([ZSVR](https://www.verpackungsregister.org/themen/serviceverpackungen))
- **§7(2) Vorvertreiber rule (regime to 11 Aug 2026):** the restaurant can require its supplier to take
  over system participation and demand written confirmation. The supplier licenses it and embeds the cost
  in the price. **But the restaurant still registers in LUCID itself.**

### 🚨 The single biggest change

Per [ZSVR's PPWR guidance](https://www.verpackungsregister.org/ppwr/serviceverpackungen): from
**12 August 2026 the pre-licensing route largely dies for branded packaging.** If the packaging carries
the company name, logo or brand, the chain is **both *Erzeuger* and *Hersteller*** — it must organise
system participation itself, register and report volumes in LUCID, obtain material/weight data from
suppliers, and hold the conformity documentation. Contracts had to be concluded or expanded **before
12 August 2026**; **no transition period**; non-compliance is a distribution ban.
([own-brand rule](https://www.verpackungsregister.org/ppwr/systembeteiligung-eigenmarken-importe))

A model treating German service packaging as supplier-borne is now wrong for any QSR with a logo on its cups.

### VerpackDG

*Gesetz zur Anpassung des Verpackungsrechts … an die Verordnung (EU) 2025/40*. Published BGBl **17 July
2026**, in force **12 August 2026**, replacing VerpackG. Existing system participations continue **to 31
December 2026**. Registration, system participation and Datenmeldung all persist.
([BMUKN](https://www.bundesumweltministerium.de/gesetz/gesetz-zur-anpassung-des-verpackungsrechts-und-anderer-rechtsbereiche-an-die-verordnung-eu-2025-40),
[ZSVR change page](https://www.verpackungsregister.org/ich-moechte-wissen-was-sich-ab-dem-12-august-2026-aendert))

**Vollständigkeitserklärung thresholds confirmed and unchanged:** glass <80 t · paper/board <50 t ·
**all other materials combined (plastics, ferrous, aluminium, composites) <30 t**. Due annually **15
May**, expert-certified. Scope widens under VerpackDG to capture transport and shipping packaging.
([§11](https://www.gesetze-im-internet.de/verpackg/__11.html))

**Authorised representative:** PPWR Art. 45(3) + §5(2) VerpackDG. Mandatory **12 Aug 2026**; existing
registrants have until **12 Nov 2026** to notify ZSVR. The AR takes on everything **except the
registration itself**, which stays personal to the producer. **A German GmbH means no AR is needed** —
VAT registration alone is insufficient, but a registered business address suffices; a subsidiary does
not cover the parent.

### EWKFondsG — the separate federal levy (Germany only)

Registration in **DIVID** with the Umweltbundesamt; annual report by **15 May**; payment one month after
the Abgabebescheid. Rates per **§2 EWKFondsV** ([source](https://www.gesetze-im-internet.de/ewkfondsv/__2.html)):

| Category | €/kg | ≈€/t |
|---|---|---|
| Food containers | 0.177 | 177 |
| Bags and film wrappings | 0.876 | 876 |
| Non-deposit beverage containers | 0.181 | 181 |
| Deposit beverage containers | 0.001 | 1 |
| **Beverage cups** | **1.236** | **1,236** |
| **Lightweight carrier bags** | **3.801** | **3,801** |

**Is the restaurant liable?** Buying from a German supplier — no, the supplier/importer is. **Importing
its own branded cups and clamshells — yes, the chain is the importer and is liable.**
([§3](https://www.gesetze-im-internet.de/ewkfondsg/__3.html)) Exactly mirrors the PPWR own-brand shift.
⚠️ Whether rates were revised at the 1 Jan 2026 review is unverified; §2 as fetched still shows the above.

### Municipal packaging tax — invisible to any national model

**Tübingen**, in force 1 Jan 2022 — the complainant was a **McDonald's franchisee**. **€0.50** per
single-use packaging (cup), **€0.50** per single-use dish (fries container), **€0.20** per cutlery
item/straw. Upheld by **BVerwG 24 May 2023** and by the **BVerfG, 1 BvR 1726/23, decided 27 Nov 2024,
published 22 Jan 2025** — a lawful local consumption tax under Art. 105(2a) GG.
([BVerfG](https://www.bundesverfassungsgericht.de/SharedDocs/Pressemitteilungen/DE/2025/bvg25-006.html),
[Tübingen](https://www.tuebingen.de/verpackungssteuer))

**Freiburg from 1 Jan 2026**, same rates, **charged per component, no cap** — a burger meal with fries,
utensils and a drink with straw is taxed on every item. ([Freiburg](https://www.freiburg.de/pb/2535005.html))

Konstanz live since Jan 2025. Adopted/decided: **Bonn (1 Jul 2026), Bremen, Köln, Oberhausen, Hameln,
Heidelberg, Rottenburg, Troisdorf and Osnabrück (1 Jan 2027)**. ~144 cities expressed interest in an
April 2025 survey. **Bavaria has banned municipal packaging taxes** effective January 2026, killing
Munich, Nuremberg, Regensburg and others — the only Land to do so.
([kommunal.de](https://kommunal.de/verpackungssteuer-verbot-bayern))

⚠️ The €1.50/meal Tübingen cap appears to have been removed on BVerwG instruction; not fully confirmed.

### Reuse and deposit

- **§33 Mehrwegangebotspflicht, since 1 Jan 2023:** final distributors of single-use plastic food
  containers and **beverage cups of any material** must also offer the same goods in reusable packaging,
  **not at a higher price or worse terms**, with visible signage. **§34 exemption: ≤5 employees AND ≤80
  m²** — irrelevant to a chain. Penalty **up to €10,000**. ⚠️ Carry-forward into VerpackDG is implied but
  not explicitly confirmed.
- **Pfand §31: at least €0.25 incl. VAT**, single-use beverage containers 0.1–3.0 L; **milk drinks
  included from 1 Jan 2024**. Beverages poured into a cup at the counter carry **no** Pfand — but do
  carry the §33 reuse duty and the €1.236/kg EWKFondsG cup levy.

---

## SPAIN

### Registration and stream

**RD 1055/2022** art. 15 — packaging section of the *Registro de Productores de Producto* at MITECO;
number format **ENV/[year]/XXXXXXXXX**; **must appear on invoices and all commercial documentation**.
([BOE](https://www.boe.es/buscar/act.php?id=BOE-A-2022-22690))

**Commercial & industrial EPR is live from 1 January 2025** (DT tercera required systems constituted
before 31 Dec 2024).

**Which stream:** takeaway clamshells, cups, bags and trays are **"envases de servicio"** (art. 2.j —
expressly *bandejas, platos, vasos*), the restaurant is the **envasador** (art. 2.e), and they sit in the
**doméstico** stream financed under art. 28. Packaging the restaurant consumes running itself is
**"envase comercial"**. Two relief valves: **art. 28.1 sub-2** lets suppliers voluntarily discharge the
obligations in the producer's name (most Spanish foodservice suppliers do this); **art. 15.1**
consolidates registration where C&I packaging is under 50,000 kg.

**Authorised representative — mandatory, art. 17.2**, verbatim: producers established in another Member
State or third country marketing in Spain *"deberán designar a una persona física o jurídica en
territorio español como representante autorizado."* **Fallback if none: the first Spanish-established
distributor becomes subsidiarily liable** — a clause your Spanish suppliers will eventually invoke. A
Spanish operating subsidiary that hands packaging to consumers is itself the producer.

### Ecoembes rates

The pricing tool currently publishes **2027** rates (page modified 5 Aug 2026), €/kg, household
([source](https://ecoembesempresas.com/es/precios)): PET trays and rigids 0.682 (SUP 0.693) · HDPE rigid
0.282 (0.293) · other rigid plastics 0.773 (0.784) · film/flexibles 1.269 (1.280) · **paper and board
0.117 (0.128)** · brik 0.544 (0.555) · compostable 0.205 (0.216) · aluminium 0.040 · steel 0.197.

**The ~+€0.011/kg "SUP" delta on every material is the SUPD Art. 8 uplift** — embedded, no separate
invoice. Commercial packaging: 0.0025 €/kg where the outlet privately manages >85% of its commercial
waste, otherwise rigid plastics 0.173 · flexible 0.164 · paper/board 0.037.

⚠️ 2026 (current-year) household schedule and Ecovidrio glass rates unverified — source PDFs behind 403/404.

### Eco-modulation

Criteria are recycled content, colour, label size and recyclability-impairing materials. **One quantified
band confirmed: glass carries a 50% penalty** for ceramic closures, non-soda-lime glass, or
porcelain/stoneware infusibles. ⚠️ The full percentage grid sits in the *Guía de Ecomodulación
2026/2027* PDF, behind a 403 — **unverified**.

### The plastic tax — the biggest uncontrolled exposure

**Impuesto especial sobre los envases de plástico no reutilizables**, Ley 7/2022 arts. 67–83, **in force
1 Jan 2023**, **€0.45/kg of non-recycled plastic**.
([AEAT](https://sede.agenciatributaria.gob.es/Sede/impuestos-especiales-medioambientales/impuesto-especial-sobre-envases-plastico-reutilizables/base-imponible-tipo-impositivo-cuota-tributaria.html))

- **Taxable events: manufacture, importation, intra-EU acquisition.** A chain importing or
  intra-EU-acquiring cups is the **taxpayer directly**. Buying from a Spanish supplier means it is
  embedded in the price and itemised on the invoice.
- **Base is only the non-recycled fraction — but recycled content must be certified under UNE-EN
  15343:2008.** No certificate, whole weight taxed. This is the only real lever.
- **5 kg/month exemption confirmed (art. 75(f))** — but applies **only to importation/intra-EU
  acquisition**, is **monthly**, and is measured on **non-recycled plastic weight**. Irrelevant at chain scale.
- **Registration in the Registro territorial before starting activity** (art. 82.3); **CIP** assigned
  under Orden HFP/1314/2022; quarterly or monthly filing. Failure to register: **€1,000 fixed fine**.
- No foodservice carve-out. **Paying Ecoembes does not discharge it.**

### SUP consumer charge and labelling

- **Ley 7/2022 art. 55.2, since 1 Jan 2023:** a price **must** be charged for each Annex IV Part A item —
  **beverage cups incl. lids, and fast-food containers** — and **itemised separately on the receipt**
  (*"diferenciándolo en el ticket de venta"*). **The amount is not set by law.** Reduction calendar:
  **−50% by 2026, −70% by 2030**.
- Art. 56 bans plastic cutlery, plates, straws, stirrers and **all EPS food/beverage containers and
  cups**. Art. 57.1 tethered caps from 3 July 2024. Art. 57.2 PET bottles ≥25% recycled from 1 Jan 2025,
  30% from 2030. RD 1055/2022 art. 7.5: restaurants must always offer **free unbottled water**.
- **Labelling, RD 1055/2022 art. 13, applicable 1 Jan 2025.** Widely misreported — material
  identification per Decisión 97/129/CE is **voluntary** (13.1). **Mandatory:** reusability and DRS
  symbol where applicable, **household packaging must indicate the fraction/container** (13.2);
  compostable certification to UNE-EN 13432 plus *"no abandonar en el entorno"* (13.5); **beverage cups
  must carry the harmonised SUPD marking per Implementing Regulation (EU) 2020/2151** (13.7). Prohibited:
  "respetuoso con el medio ambiente" claims (13.3). 6-month sell-through for pre-2025 stock.
- **Sanctions, Ley 7/2022 art. 109:** leve up to €2,000 · **grave €2,001–100,000** · **muy grave
  €100,001–3,500,000**, plus disqualification, closure, confiscation, and **uplift to double the benefit
  obtained** where the fine is lower (art. 109.2).

---

## ITALY

### CONAI — and who actually pays

A restaurant chain is an ***utilizzatore***. The decisive rule is **prima cessione** (CONAI Guide §4.1):
there is exactly one first transfer per packaging item on Italian territory.

- **Buying from an Italian supplier** → the supplier declares and pays; **the CAC is embedded in the
  invoice price** (with mandatory CONAI wording). No CONAI declaration by the restaurant.
- **Importing empty packaging** → the restaurant declares on **modulo 6.1**.
- **Importing packaged goods** → **modulo 6.2**.

**No mandatory representative in Italy.** Foreign companies join CONAI **voluntarily** (fixed quota
€5.16); non-EU firms without stable Italian representation must **post guarantees** covering ~12 months
of expected CAC. If the foreign supplier doesn't join, the CAC falls on the Italian party effecting
*immissione al consumo*. Arrangements hold until **RENAP** (art. 178-ter(8) D.Lgs. 152/2006) becomes
operational at MASE. Non-registration fine reported at **€5,000** — ⚠️ unverified against art. 261.

Simplified import options: **0.19% of net purchase value for food products**; or flat **€109.00/t to
30.06.2026, €110.00/t from 01.07.2026**; *forfetario* by turnover only up to €2m (a real chain exceeds it).

### CAC 2026 rates, €/tonne (primary — [CONAI 2026 Guide](https://www.conai.org/download/guida-al-contributo-ambientale-2026/), p. 39)

Steel 5.00 · aluminium 12.00 · wood 10.00 · glass 40.00 · **bioplastic 130.00 to 30.06, then 246.00 from
01.07.2026**.

Paper: monomateriale 45 · compositi A 45 · **B1 certified 55 vs B2 non-certified 70** · CPL 115 ·
**C1 certified 110 vs C2 non-certified 155** · compositi D 285.

Plastic: A1.1 40 · A1.2 87 · **A2 258** · **B1.1 219** · **B1.2 228** · **B2.1 611** · B2.2 724 ·
B2.3 785 · **C 790**.

**Practical QSR mapping:** rigid PP cups/lids/bowls → **B2.1 €611/t** · PET cold cups → **B1.2 €228/t** ·
PE film and bags → **A2 €258/t** · HDPE rigids → **B1.1 €219/t** · PLA/compostable → **€130 → €246/t
mid-year**. **From 2026, PVC and carbon-black items are reclassified into Fascia C (€790/t).**

⚠️ **Discrepancy flag:** several consultancy sites circulate a *different, higher* 2026 plastic table
(A1.1 51, B2.1 639, B2.2 856…). The CONAI Guide figures above are primary; treat the circulating higher
set as unverified.

### Eco-modulation

The plastic band structure **is** the eco-modulation — three bands (2018) → five (2022) → **nine (2023
onward)**, priced by sortability, recyclability, prevailing end-of-life circuit and chain deficit. Paper
went from six to eight bands on 1 July 2025; **Aticelca 501 certification** is the concrete lever moving
composites from €70→€55 and €155→€110/t.

**Carve-out worth knowing:** the CPL band **expressly excludes catering articles** — *"piatti,
bicchieri, vaschette con relativi coperchi"*. Paper cups and lidded board trays are classified as
monomaterial or by paper share, not CPL.

### Labelling — art. 219(5) D.Lgs. 152/2006 (via D.Lgs. 116/2020)

**In force 1 January 2023** after two deferrals. **All packaging incl. B2B:** alphanumeric material code
per **Decisione 97/129/CE**. **Household/consumer channel additionally:** disposal and sorting
instructions. Guidelines: **D.M. n. 360 of 28 September 2022**
([MASE](https://www.mase.gov.it/portale/documents/d/guest/linee_guida_etichettatura_ambientale_27-09-2022-pdf)).
Digital labelling permitted for part of the information.

⚠️ **Penalties — conflicting figures, both unverified:** €5,200–€40,000 (art. 261 comma 3) per one
source; €5,000–€25,000 from 1 Jan 2023 per another. Normattiva returned HTTP 500. Exposure is per-SKU
and compounding either way.

### Plastic tax — NOT in force

MACSI, Legge 160/2019, €0.45/kg. **Never entered into force. Currently deferred to 1 January 2027** by
the 2026 Budget Law (**Legge 199/2025, art. 1 c. 125**) — the **eighth postponement in five years**.
Commentary reads it as a prelude to repeal, but hold a contingent line item.

---

## IRELAND

### Repak

**S.I. No. 282/2014.** "Major producer" test (Reg. 4(3)(a)) — **>10 tonnes packaging AND >€1m
turnover**, both limbs cumulative, both measured on activities within the State.
([Irish Statute Book](https://www.irishstatutebook.ie/eli/2014/si/282/made/en/print))

**Self-compliance was removed on 1 January 2023** (⚠️ date unverified against the amending S.I.), so
**Repak — the only approved body — is the sole route**; Reg. 17 exempts members from the Part III
local-authority registration and reporting.

**The distinction most chains get wrong:** *Scheduled Membership* (flat fee) is only for a
pub/restaurant/hotel that is **neither brandholder nor importer**. A QSR with **branded** cups and bags,
or importing its own packaging, is a **Regular Member** on full weight-based fees. And **for hospitality,
all products consumed on-site count toward the obligation** — the 10 t test is not limited to takeaway.
**Back fees run up to six years**; Local Authorities prosecute.
([Repak Regular Member Guide 2026](https://repak.ie/images/uploads/downloads/Repak_Regular_Member_Guide_2026.pdf))

### Repak fees 2026, €/tonne (total across supply chain; brandholder/importer bears ~97%)

Paper/cardboard **45.60** · glass 23.14 · aluminium (non-DRS) 9.14 · steel (non-DRS) 68.76 · wood 18.18 ·
**recycled rigid and flexible plastic 169.70** · **NON-recycled plastic 620.22** · recycled composite
169.70 · **non-recycled composite 620.22** · non-recycled other 328.06.

**The recycled/non-recycled cliff is the whole story: 3.7×.** It bites hardest exactly where poly-coated
paper cups and lidded board clamshells sit. Eco-modulation exists via Repak's *Prevent & Save* but the
criteria grid is not published in the member guide — ⚠️ unverified.

### The "latte levy" — NOT commenced

Circular Economy and Miscellaneous Provisions Act 2022 provided for a **20 cent** levy per single-use
hot-drink cup; consultation on draft regulations opened October 2022. **Still not commenced as of August
2026.** May 2026 reporting notes the levy "has never been enacted" and that the Government faced an
end-of-June deadline to answer the European Commission on SUPD implementation shortcomings.
([thejournal.ie](https://www.thejournal.ie/ireland-single-use-plastics-takeaway-cups-cultlery-7046760-May2026/))
**Treat as a near-term contingency, not a current obligation** — the infringement pressure is the live catalyst.

### Re-turn DRS — live since 1 February 2024

Scope: **PET bottles and aluminium/steel cans, 150 ml–3 L**. **Excluded: all glass, all dairy.** ⚠️ The
commonly cited **15c/25c** split by size could not be confirmed from a Re-turn primary page.

**What a QSR must do** ([Take-Back Exemptions PDF](https://re-turn.ie/wp-content/uploads/Take-Back-Exemptions.pdf), §5):

- Pubs, restaurants, hotels and cafés **have full retailer obligations** and **must register** —
  registration is not optional.
- **All HORECA are granted a take-back exemption** — running a return point is voluntary. But an
  exemption notice and a **QR-code locator** for the nearest return point must be displayed.
- Hospitality **is charged the deposit on purchase**; there is an **automatic exemption from passing it
  on for on-premises consumption**, but **the deposit must be charged through on takeaway**.

### Labelling

S.I. 282/2014 imposes **no packaging marking obligation** (Schedule 2 governs the format of statutory
notices only). Ireland's marking duties are purely EU-level: SUPD harmonised markings under
**Implementing Regulation (EU) 2020/2151** and the Re-turn logo. **No national analogue** of Italy's art.
219(5) or Spain's art. 13.

---

## NETHERLANDS

### Registration — Verpact

Liable party per **Besluit beheer verpakkingen 2014, art. 1(g)**. Threshold is **50,000 kg per calendar
year as a COMBINED total across all materials**, not per material.
([Verpact](https://www.verpact.nl/nl/de-grens-van-50000-kg-jaar-verpakkingsmateriaal-een-totaal-grens))

**But two carve-outs make a QSR in scope regardless of tonnage: (a) deposit-bearing bottles and cans,
and (b) ALL single-use plastic packaging — report from the first unit.** SUP reporting is by **weight AND
item count**; a container with a loose lid **counts as 2 items**. Declaration via **PackTool**, quarterly
advances at 25% of estimate, final declaration before **1 April**.

**AR:** Dutch law codifies only the *outbound* mirror duty. Inbound, a foreign company without a Dutch
establishment registers **directly with Verpact** today. **PPWR Art. 45 from 12 Aug 2026** bites only on
cross-border distance selling into NL, not on a chain running NL-established outlets.

### Verpact tariffs 2026, €/kg excl. VAT ([source](https://www.verpact.nl/nl/tarieven))

Glass 0.100 · paper/board 0.017 · **rigid plastic 1.220** · **flexible plastic 1.320** · aluminium 0.340
(up from 0.300) · other metals 0.360 · wood 0.015 · **beverage cartons 0.920** (up from 0.880) · reusable
packaging 0.015 · **reusable drinking cups 0.280**.

**SUP-opslag: €2.10 per 1,000 units for 2026** (2025: €2.30) — covering cups, beverage packaging ≤3 L,
rigid and flexible SUP food packaging, and bags <50 µm. **This per-unit surcharge is the whole of the
Dutch SUPD Art. 8 charge — there is no separate per-kg litter rate.** Recyclability modulation offers
discounts up to €0.60/kg.

### 🚨 The Dutch SUP charge is going the OPPOSITE way to everywhere else

- **Takeaway meerprijs (art. 2.2, in force 1 July 2023):** a SUP cup or container for off-premises
  consumption must be supplied *"voor een meerprijs"*, itemised separately on the receipt, VAT following
  the accompanying product, operator keeps the revenue. **The amount is NOT set in law.**
- **The €0.25 fix never took effect** — the Regeling's current text is still the 1 Jan 2024 version.
- **ILT does not enforce the meerprijs, through end-2026** — *"de Inspectie Leefomgeving en Transport
  handhaaft niet op de meerprijs. Dit geldt tot eind 2026."*
  ([afvalcirculair](https://afvalcirculair.nl/minder-wegwerpplastic/veelgestelde-vragen/aanpassingen-regelgeving/))
- **The obligation is being ABOLISHED, planned 1 January 2027**, retaining the reusable-option duty and
  explicitly allowing bring-your-own discounts.
  ([Ondernemersplein](https://ondernemersplein.overheid.nl/wetswijzigingen/meerprijs-wegwerpbekers-en-bakjes-verdwijnt/))
  Amendment still needs parliamentary passage — date not final.

⚠️ The €0.50 meal-container and €0.05 portion-pack figures circulating elsewhere could not be sourced
anywhere. **Do not use them.**

- **On-site consumption (art. 2.1, in force 1 Jan 2024) — the real operational constraint.** Offering SUP
  cups/containers for consumption at the location is **prohibited unless** the operator demonstrates
  separate collection for high-quality recycling at: **2024 75% · 2025 80% · 2026 85% · 2027+ 90%**.
  **Prior notification to ILT required**, records kept ≥3 years. From 2027 the "high-quality" qualifier
  drops (opening the door to plastic-coated paper) and offices/education lose the exception while
  hospitality keeps it.

### DRS — statiegeld

Regeling beheer verpakkingen art. 6: **plastic bottles ≤1 L €0.15 · plastic bottles >1 L to 3 L €0.25 ·
cans ≤3 L €0.15**. Small bottles from 1 July 2021, cans from 1 April 2023.

**Hospitality has NO take-back obligation** (*"De horeca heeft geen innameplicht"*) — the duty rests on
producer/importer. Charge the deposit through, optionally register as a return point, recover via the
wholesaler. **If the chain imports deposit-bearing drinks itself, it becomes the producer/importer and
declares from the first unit.**

On **27 November 2025** the State Secretary **rejected raising the deposit**, taking Verpact expansion
commitments instead (supermarket return points 7,600 → 10,500 by end-2026). Producer contribution on cans
rises to **1.0 eurocent for 2026** from 0.2.

---

## What a naive "EPR fee per tonne" calculator gets materially wrong

1. **Tonnage is not the billing unit in half these markets.** France bills household packaging **per
   UVC** and delivered food **per order**. Netherlands bills **per 1,000 units**. Germany's municipal tax
   is **per item**.
2. **It misses the three non-EPR charges entirely.** Spain's **€0.45/kg plastic tax**. Germany's
   **EWKFondsG levy** to a different authority — **€1.236/kg on cups**. Germany's **municipal
   Verpackungssteuer** — uncapped in Freiburg, which alone can exceed **€1.50 on a single meal**. Italy's
   MACSI is deferred to 2027 but must be a contingent line.
3. **It assumes the chain is the fee payer, when that flips on establishment and branding.** Germany:
   from 12 Aug 2026 own-branded packaging makes the chain the producer, with no transition period. Italy:
   buying domestically embeds the CAC; importing makes the chain liable. Spain: art. 28.1 lets suppliers
   voluntarily discharge. France: *donneurs d'ordre* are now systematically the producer. **Whether the
   chain owes anything at all is a function of sourcing structure, not volume.**
4. **Authorised-representative status is a four-way split, not a yes/no.** Legally required in **France**,
   **Germany** and **Spain** (with the **first Spanish distributor subsidiarily liable** if none).
   **Not required in Italy.** A local operating subsidiary moots it everywhere — so the real input is
   **entity structure per country**.
5. **Eco-modulation is where the money is, and it is not a percentage tweak.** Ireland: **€169.70 vs
   €620.22/t** — 3.7×. Italy: PP cup B2.1 €611/t vs PET B1.2 €228/t — a 63% cut from one material swap;
   Aticelca 501 moves paper composites €70→€55; **PVC and carbon black drop into Fascia C at €790/t in
   2026**; **bioplastic nearly doubles mid-year**. France: carbon-black or dark plastics carry a **100%
   malus**. These are design decisions, not fee decisions.
6. **France's litter component scales with packaging-unit count, not weight.** A burger meal is 6+ *unités
   d'emballage* on one UVC, multiplying the litter charge ~4–5×.
7. **It assumes obligations only ratchet up.** The Netherlands is **abolishing** its takeaway charge
   (planned 1 Jan 2027) and **not enforcing it through end-2026**, while tightening the dine-in
   prohibition to 90% collection. Ireland's latte levy has been "imminent" since 2021. France removed
   **five maluses for 2026**. A tool that only adds rules will overstate exposure.
8. **Minimum fees and flat charges dominate at low volume.** France: **€110 HT** household minimum and
   **€145** Citeo Pro forfait below 4 t. Italy: forfetario bands from €275.
9. **Capex dwarfs opex on the reuse mandates.** France's dine-in reusable-tableware rule (≥20 covers,
   since 1 Jan 2023, **any material**) means dishwashing infrastructure at every site, with fines
   **cumulative across a chain's sites** and large chains explicitly prioritised. Germany's §33 and PPWR
   Art. 33 (Feb 2028) point the same way. None of this is an EPR fee.
10. **One tonne is several registrations.** A French QSR holds separate IDUs for ménagers, papiers
    graphiques, professionnels — plus DEA, DEEE, TSUU, huiles usagées. Germany adds LUCID + dual system
    contract + DIVID + the **Vollständigkeitserklärung**. Ireland charges **six years of back fees**.

---

## Confidence and open items

**Solid:** PPWR citation, dates and article mapping; SUPD Art. 8 Part E scope; French IDU/mandataire law
and 2026 Citeo eco-modulation; German EWKFondsG rates, VerpackDG dates, ZSVR own-brand guidance, BVerfG
ruling; Spanish RD 1055/2022 art. 17.2 and Ley 7/2022 tax/charge/sanctions; CONAI 2026 rates from the
primary Guide; Repak 2026 fee table; Verpact 2026 tariffs; Dutch meerprijs non-enforcement and planned
abolition.

**Verify before coding into a calculator:**

- **France:** whether H2-2026 EPRO contributions are due; the *restauration livrée* menu-code→tariff
  mapping; Prime Ressources €/kg; Triman fine amount.
- **Germany:** whether EWKFondsV rates were revised at the 1 Jan 2026 review; whether the Tübingen €1.50
  cap is formally gone; whether VerpackDG carries §§33–34 forward verbatim; the **live Commission
  proposal to suspend PPWR Art. 45**.
- **Spain:** Ecoembes 2026 (not 2027) household schedule; the full eco-modulation grid (PDF 403);
  Ecovidrio rates.
- **Italy:** art. 261 D.Lgs. 152/2006 fine bands (two conflicting figures, normattiva down); the
  competing higher 2026 plastic table circulating in trade press.
- **Ireland:** Re-turn deposit amounts by size band; the S.I. that removed self-compliance; Repak's
  eco-modulation criteria.
- **Netherlands:** no source found for the €0.50/€0.05 charge figures — **do not use**.
