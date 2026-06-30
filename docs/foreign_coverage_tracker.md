# Foreign EPR Law — Coverage Tracker

Reconciles our scraper coverage against the **UNIDO/Chatham House "Global Stocktake of
National Circular Economy Roadmaps and Strategies: 2025 Update"** (64 countries with adopted
CE frameworks + 14 map-only/pipeline). The stocktake measures *policy intent*; we ingest
*binding EPR law*, so a roadmap ≠ ingestible statute. Archetypes: **A** open/no-auth/structured,
**B** registered/keyed API, **C** HTML scrape (no clean API), **D** PDF/OCR, **E** federated/subnational.

Status legend: **BUILT** (adapter live, in corpus) · **ASSESSED** (portal researched, not built) ·
**TODO** (not yet assessed).

## Summary
- Adopted-framework countries: **64** → BUILT **16 entries / 13 adapters**, ASSESSED **16**, TODO **32**.
- Pipeline countries: **14** → ASSESSED **2** (Philippines, South Africa), TODO **12**.
- Biggest untapped seam: **~12 EU member states never individually assessed**, almost all likely
  Archetype A/B via ELI portals (same pattern as ES/PL/IE/LU) — probable easy wins.

## BUILT (13 adapters → 16 stocktake entries)
| Country (stocktake entries) | Adapter | Archetype | Corpus (local CE-relevant) |
|---|---|---|---|
| Japan | JP (e-Gov) | A | 113 |
| France | FR (Légifrance + Code) | B | 123 |
| United Kingdom + England + Scotland + Wales + Northern Ireland | UK (legislation.gov.uk, incl. devolved) | A | 87 |
| Germany | DE (gesetze-im-internet) | A | 15 |
| Netherlands | NL (wetten/SRU) | A | 30 |
| Spain | ES (BOE) | A | 8 |
| Chile | CL (Ley Chile) | A | 6 |
| Sweden | SE (Riksdagen) | A | 34 |
| Ireland | IE (eISB) | A | 6 |
| Austria | AT (RIS) | A | 5 |
| Brazil | BR (Planalto) | A | 5 |
| Switzerland | CH (Fedlex SPARQL) | A | 5 |
| _(EU — via separate EUR-Lex pipeline, not FOREIGN_CLIENTS)_ | eurlex | A | 8 local / 516 dev |

## ASSESSED, not built (16) — portal known, ranked by value × ease
| Country | Archetype | Portal / entry point | Priority | Note |
|---|---|---|---|---|
| Republic of Korea | B | law.go.kr DRF API (free OC reg) | **HIGH** | strongest Asia EPR; build next |
| Italy | A/B | api.normattiva.it OpenData (AKN/JSON) | **HIGH** | new official API; async token |
| Poland | A | api.sejm.gov.pl/eli REST | **HIGH** | HTML for modern acts; consolidated = PDF |
| Norway | A | api.lovdata.no publicData bulk tar.bz2 | MED | heavy full-corpus download |
| New Zealand | A | data.govt.nz PCO bulk XML | MED | site bot-blocks HTTP; bespoke DTD; English |
| Belgium | C / E (Flanders A) | codex.opendata.api.vlaanderen.be (VLAREMA) | MED | EPR is regional; Flanders clean JSON |
| Australia | E (federal A) | api.prod.legislation.gov.au OData | MED | EPR mostly state CDS |
| Canada | E (BC A) | bclaws CiviX API; federal XML | MED | EPR provincial (ON/BC/QC) |
| China | B | flk.npc.gov.cn JSON (reverse-engineered) | MED | Chinese only; undocumented |
| Turkiye | C | mevzuat.gov.tr (predictable HTML/PDF) | MED | no catalog API |
| Portugal | C | DRE (Angular SPA, needs headless) | LOW | strong EPR but SPA |
| Argentina | C | InfoLEG HTML | LOW | EPR thin/subnational |
| Colombia | C / D | SUIN-Juriscol (PDF resolutions) | LOW | |
| India | C / D | India Code + e-Gazette PDF | LOW | EPR rules are Gazette PDFs |
| Indonesia | D | peraturan.go.id PDF | LOW | |
| Viet Nam | C | vbpl.vn (reCAPTCHA-gated) | LOW | |

## TODO — adopted, NOT yet assessed (32)
### EU members — likely A/B via ELI (probable easy wins, UNVERIFIED) — 12
Denmark (retsinformation.dk), Finland (finlex.fi new API), Greece, Czechia, Estonia, Latvia,
Lithuania, Luxembourg (legilux — JOLux/ELI, same stack as CH Fedlex), Malta, Romania, Slovakia,
Slovenia. → *These are the highest-probability next wins; EU directive layer already in corpus,
value = national implementing decrees (the FR/NL/ES model).*

### Other Europe (Balkans / EFTA / EE) — 5
Albania, Montenegro, Serbia, Republic of Belarus, Republic of Moldova.

### Latin America — 5
Costa Rica, Ecuador, Panama, Peru, Uruguay.

### Africa — 6
Chad, Ethiopia (framework not public), Ghana (framework not public), Mauritius, Nigeria, Rwanda.

### Asia / Gulf / subnational — 4
Cambodia, Malaysia, United Arab Emirates, Portugal (Madeira — subnational region).

## Pipeline / map-only (14) — not confirmed adopted frameworks
- ASSESSED: Philippines (C — LawPhil HTML, English), South Africa (B — Laws.Africa, **pan-African API**).
- TODO: Algeria, Angola, Benin, Cameroon, Côte d'Ivoire, Egypt, Georgia, Oman, Qatar,
  Singapore (likely A — sso.agc.gov.sg, English), Uganda, Ukraine.

## Recommended next research
1. **Assess the 12 EU members** (ELI portals) — fan-out, ~likely 8-10 turn out Archetype A/B.
2. Then the **3 HIGH already-assessed** (Korea, Italy, Poland) are build-ready now.
3. **South Africa / Laws.Africa** as a force multiplier (one B adapter → many African jurisdictions).
