# Foreign EPR Law — Coverage Tracker

Reconciles our scraper coverage against the **UNIDO/Chatham House "Global Stocktake of
National Circular Economy Roadmaps and Strategies: 2025 Update"** (64 countries with adopted
CE frameworks + 14 map-only/pipeline). The stocktake measures *policy intent*; we ingest
*binding EPR law*, so a roadmap ≠ ingestible statute. Archetypes: **A** open/no-auth/structured,
**B** registered/keyed API, **C** HTML scrape (no clean API), **D** PDF/OCR, **E** federated/subnational.

Status legend: **BUILT** (adapter live, in corpus) · **ASSESSED** (portal researched, not built) ·
**TODO** (not yet assessed).

## Summary (updated after the EU fan-out)
- BUILT jurisdictions: **23** — JP, FR, UK(+devolved), DE, NL, ES, CL, SE, IE, AT, BR, CH, PL,
  **DK, FI, LU, EE, LV, SK, LT, SI, CZ** (the 9 EU members added in the fan-out). EU directive layer
  via the separate EUR-Lex pipeline.
- STAGED-DORMANT (need account/licensing): **KR** (law.go.kr OC), **ZA + KE** via laws.africa
  (Bearer token + CC-BY-NC-SA commercial-licensing decision).
- DEFERRED (no clean full-text path): Italy (SPA/async export), Malta (PDF text-layer), Greece (OCR
  snippets), Romania (geo-firewall), Portugal (SPA), + the C/D/E tail (AU, CA, BE, CN, TR, AR, CO,
  IN, ID, VN, MX, …).
- The EU fan-out closed the "12 unassessed EU members" seam: **9 built, 3 deferred** (Malta/Greece/
  Romania). Remaining adopted-country TODO is now the non-EU tail (Balkans, LatAm, Africa, Gulf).

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
| Australia | A (fed/QLD/TAS) – C (VIC) | api.prod.legislation.gov.au OData + per-state portals | **BUILT (P1)** | AU/AU_QLD/AU_TAS live; AU_NSW blocked (Cloudflare TLS). See FEDERATED_EXPANSION_PLAN.md |
| Canada | A (fed/BC/ON) – D (AB/SK) | Justice XML, CiviX, e-Laws JSON API | **BUILT (P1)** | CA/CA_BC/CA_ON live + validated. See FEDERATED_EXPANSION_PLAN.md |
| China | A- | flk.npc.gov.cn (verified: no auth/captcha/geo-block) | **BUILT (P1)** | CN (flk DOCX) + CN_GOV live + validated. See FEDERATED_EXPANSION_PLAN.md |
| Turkiye | C | mevzuat.gov.tr (predictable HTML/PDF) | MED | no catalog API |
| Portugal | C | DRE (Angular SPA, needs headless) | LOW | strong EPR but SPA |
| Argentina | C | InfoLEG HTML | LOW | EPR thin/subnational |
| Colombia | C / D | SUIN-Juriscol (PDF resolutions) | LOW | |
| India | **A- (via FAOLEX)** | faolex.fao.org/docs/pdf/ind{ID}.pdf | **BUILT (P1)** | IN client, 5 seed rules (PWM 2016+2024, E-Waste 2016+2022, SWM 2016), all classify epr 0.85–0.99. Native CPCB/moef/indiacode geo/UA/cert-gated; FAOLEX PDF mirror is reachable+deterministic. English-native (no prompt change). Battery 2022 + EP Act = documented gap (url-override ready). Local-verified; prod ingest+deploy pending |
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
