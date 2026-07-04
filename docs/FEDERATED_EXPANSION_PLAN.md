# Federated-Jurisdiction Expansion Plan — Australia, Canada, China

Research date: 2026-07-03. All endpoints below were **live-verified** (status code + body
inspected) from a US IP, not just read from docs. This plan unlocks the "Defer E" bucket
(subnational EPR) plus China, which turned out far more accessible than assumed.

Headline: the old archetype grades were too pessimistic. Every jurisdiction that matters is
reachable; the work is ~9 new adapters + 3 shared text-extraction helpers.

---

## BUILD STATUS — Phase 1 shipped 2026-07-03 (LOCAL, uncommitted)

All in `app/ingestion/foreign.py`; registered in `FOREIGN_CLIENTS`; classifier `REGION_LABELS`
updated for CN/CA/AU in both haiku_classifier.py + sonnet_extractor.py. Added `docx_to_text()` helper.
Every adapter below was validated end-to-end through `sync_foreign` against the local DB (discover →
fetch → upsert bills+bill_texts), and the classify path was confirmed on AU_TAS (region label plumbs
through, row marked CE-relevant).

| Registry key | Adapter | Live probe result |
|---|---|---|
| `CN` | ChinaFlkClient | ✅ 69 discovered; Solid Waste Law fetched, 18.9k chars (DOCX chain works) |
| `CN_GOV` | ChinaGovCnClient | ✅ 7 discovered; EPR Implementation Plan, 5.5k chars |
| `CA` | CanadaJusticeClient | ✅ 88 discovered; CEPA 553k chars |
| `CA_BC` | CanadaBcLawsClient | ✅ 9 discovered; Recycling Regulation 62k chars |
| `CA_ON` | CanadaOntarioClient | ✅ RRCEA 145k chars (seed `statute/16r19` didn't resolve — drop/fix it) |
| `AU` | AustraliaFederalClient | ✅ 43 discovered; RAWR Act 62k chars |
| `AU_QLD` | AustraliaQldClient | ✅ WRR Act 2011, 525k chars (official XML) |
| `AU_TAS` | AustraliaTasClient | ✅ Container Refund Scheme Act, 50k chars |
| `AU_NSW` | AustraliaNswClient | ✅ via curl_cffi (WARR Act 2001 67k chars; both seed acts) |

**NSW — SOLVED with curl_cffi.** legislation.nsw.gov.au sits behind a Cloudflare "Just a moment…"
challenge that fingerprints the TLS ClientHello: system `curl` passes but plain `httpx` gets a hard 403
regardless of headers / HTTP1-vs-2 / www-vs-apex. Fix = `impersonate_get()` (module-level helper) uses
`curl_cffi`'s browser-TLS `AsyncSession(impersonate="chrome")`; the `AustraliaEnActClient` base gained
an `impersonate` flag (NSW sets it True, QLD/TAS stay on httpx). Cloudflare returns transient 52x
sporadically, so `impersonate_get` retries 3×. `curl_cffi>=0.7` added to requirements.txt. The same
helper is the escape hatch for any future Cloudflare-fronted portal (e.g. SA's flaky WAF).

**Full backfill + classify DONE (local, 2026-07-03).** `--no-classify` ingest per region, then
`reclassify_foreign_pending.py --region {CN,CA,AU}` (Haiku-only). Result — **84 CE-relevant** of 204
ingested: **CN 40** (flk 33/56 + govcn 7/7), **CA 17** (bclaws 9/9 + elaws 5/5 + justice 3/80 — the
federal keyword-scan over-discovers, classifier prunes as designed), **AU 27** (federal 23/43 + nsw 2 +
qld 1 + tas 1). Curated provincial/state adapters are ~100% relevant; federal scans are noisy-by-design.

**Remaining next steps:** drop the dead ON `statute/16r19` seed; optionally tighten CA_FED_KEYWORDS
(80 fetched → 3 relevant is a lot of stored noise); commit; then the still-pending prod deploy of the
whole foreign corpus (+ a frontend region filter for CN/CA/AU). Phase 2/3 (below) unbuilt.

---

---

## Architecture decisions (before any adapter)

### 1. Region modeling for subnational jurisdictions
Precedent: UK devolved acts (Scotland/Wales/NI) all live under `region="UK"` with the
source/source_id carrying the distinction. Recommendation — same pattern:

- One country region each: `AU`, `CA`, `CN` (drives the frontend region filter as-is).
- One client per subnational jurisdiction, distinguished by `source` tag:
  `AU:nsw:act-2001-058`, `CA:bclaws:449_2004`, `CA:elaws:regulation/210391`, `CN:flk:<bbbs>`.
- If the UI later needs per-province filtering, carry a namespaced code in `state`
  (e.g. `AU-NSW`, `CA-BC`). **Never bare codes** — Western Australia `WA` collides with
  Washington state, Ontario `ON`/South Australia `SA` are ambiguous.

### 2. Shared helpers needed (unblock multiple jurisdictions each)
| Helper | Unlocks | Notes |
|---|---|---|
| `docx_to_text()` | CN (flk), AU-VIC, AU-ACT | stdlib only: `zipfile` → `word/document.xml` → existing `_strip_tags` |
| `rtf_to_text()` | AU-SA | `striprtf` lib or a small regex stripper |
| `pdf_to_text()` | CA-AB, CA-SK, (also un-defers Malta) | `pypdf`/`pdfminer.six` dep — a framework decision, decide once |
| retry-once-on-403 + full Chrome UA | AU-NSW, AU-SA, CA-QC | extend `_BROWSER_HEADERS` default; SA/QC WAFs are flaky not hostile |

Legacy binary `.doc` (AU-NT) needs LibreOffice/antiword — **defer NT** (smallest jurisdiction).

### 3. Classifier
Add `REGION_LABELS` for CN / CA / AU (both haiku_classifier + federal_classifier).
Chinese-language full text is fine — JP precedent; no translation layer.

---

## CHINA — 3-part adapter, ~16–24 h, risk medium-low

The official National Laws & Regulations Database (flk.npc.gov.cn) is **Grade A-**: no auth,
no captcha on the read path, no US geo-block, no UA requirement. Site was rebuilt ~2025 as a
Vue SPA — all pre-2025 scraping prior art is dead; endpoints below were reverse-engineered
from the current JS bundle and verified end-to-end.

### CN-1: `ChinaFlkClient` (laws + State Council regs + provincial regs) — 6–10 h
- **Discover**: `POST https://flk.npc.gov.cn/law-search/search/list` JSON body
  `{"searchContent":"<term>","searchRange":1,"searchType":1,"pageNum":N,"pageSize":10}`.
  `searchType:1` = precise (use it; fuzzy is noisy). Category filter `"flfgCodeId":[155]`
  (=生态环境法) with empty searchContent = full-category enumeration.
  **Omit `orderByParam` entirely** (empty string → Jackson 500).
  Category tree: `GET /law-search/search/enumData`.
- **Fetch** (3 hops): `GET /law-search/search/flfgDetails?bbbs=<id>` (metadata + amendment
  lineage `lsyg` + TOC — titles only, NO body) → `GET /law-search/download/pc?format=docx&bbbs=<id>&fileId=`
  → returns presigned OBS URL (~1 h expiry, **fetch immediately**) → DOCX → `docx_to_text()`.
- **Status field `sxx`**: 3=in force, 2=superseded, 4=adopted-not-yet-effective, 1=repealed.
- **Seed bbbs (verified present)**:
  - 固体废物污染环境防治法 2020 rev (Solid Waste Law, THE EPR mandate): `ff808081729c65d801729d455fad04be`
  - 循环经济促进法 2018 rev (CE Promotion Law): `ff8080816f135f46016f1d06082912c2`
  - 清洁生产促进法 (Cleaner Production): `2c909fdd678bf17901678bf737800631`
  - 废弃电器电子产品回收处理管理条例 (WEEE reg): `ff8080816f3e9784016f424f1b4a04d9` (DOCX chain verified end-to-end)
  - 生态环境法典 (Eco-Environment Code, adopted 2026-03, `sxx=4` not yet in force) — **watch item**,
    will consolidate/supersede several environmental statutes.
- **Risk**: endpoint churn (one rebuild already killed all prior scrapers). Mitigate: ≤1 rps,
  treat any non-JSON response as a backoff/alarm signal.

### CN-2: `ChinaGovCnClient` (State Council policy instruments) — 4–6 h
- Discover: `GET https://sousuo.www.gov.cn/search-gov/data?t=zhengcelibrary_gw&q=<term>&searchfield=title&type=gwyzcwjk&p=1&n=5`
  (needs Referer `https://sousuo.www.gov.cn/` + UA) → JSON with `pcode` (国办发〔2016〕99号 style).
- Fetch: server-rendered HTML, text in `<div id="UCAP-CONTENT">`.
- Seed: EPR implementation plan 生产者责任延伸制度推行方案 —
  `https://www.gov.cn/zhengce/content/2017-01/03/content_5156043.htm` (verified, 7.7k chars).

### CN-3: NDRC/MEE curated-seed HTML fetcher — 6–10 h, lowest priority
- Both server-rendered (TRS CMS), fetchable from US. No API; curated seeds recommended.
- Seed: NDRC plastics opinion 发改环资〔2020〕80号 —
  `https://www.ndrc.gov.cn/xxgk/zcfb/tz/202001/t20200119_1219275.html` (verified).

**Licensing**: PRC Copyright Law art. 5(1) excludes laws/regulations from copyright —
commercial reuse OK. Skip official English translations (stale, incomplete, CDN-broken) and
commercial aggregators (pkulaw translations ARE copyrighted — riskier than Chinese originals).
GitHub corpus LawRefBook/Laws is useful for QA cross-checks only.

---

## CANADA — federal + 3 core provinces first, ~14–20 h core

| Jurisdiction | Grade | Fetch | Effort |
|---|---|---|---|
| Federal | A | per-doc XML | 4–6 h |
| BC | A | CiviX XML | 4–6 h |
| Ontario | A- | undocumented JSON API | 6–8 h |
| Manitoba | C | server HTML | 4–5 h |
| Québec | C | server HTML (UA/redirect quirks) | 8–10 h |
| Alberta | D | free PDF | 3–8 h (needs pdf path) |
| Saskatchewan | D | free PDF via JSON catalog | 4–6 h |
| Nova Scotia | C | server HTML | **licence-blocked** (non-commercial only) |
| CanLII | E | — | **do not build** (bulk prohibited, litigated: CanLII v. Caseway 2024) |

### CA-1: `CanadaJusticeClient` (federal) — Grade A
- Discover: `https://laws-lois.justice.gc.ca/eng/XML/Legis.xml` — single 5.3 MB catalog of ALL
  consolidated acts+regs with `<LinkToXML>` and act→reg cross-refs (`<RegsMadeUnderAct>`).
- Fetch: `https://laws-lois.justice.gc.ca/eng/XML/{id}.xml` (e.g. `C-15.31` = CEPA 1999,
  `SOR-2022-138` = Single-use Plastics Prohibition Regs). **Gotcha: regulation XML has a UTF-8
  BOM** — strip before parsing.
- Licence: Reproduction of Federal Law Order SI/97-5 — commercial OK.

### CA-2: `CanadaBcLawsClient` (BC) — Grade A
- Fetch: `https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/{id}/xml`
  (`449_2004` = Recycling Regulation — THE founding provincial EPR reg).
- Multi-part acts: `{id}_00` = HTML TOC, parts fetch as `{id}_01../xml` (EMA = `03053_*`) —
  enumerate parts from the TOC.
- Discover: `GET /civix/search/complete/fullsearch?q=<term>&s=0&e=20&nFrag=1&lFrag=100` → XML results.
- Licence: BC King's Printer licence — explicit commercial OK.

### CA-3: `CanadaOntarioClient` (Ontario) — Grade A-
- e-Laws HTML pages are a React SPA shell — **do not crawl the pages.** The SPA's backend JSON
  API is open/no-auth (reverse-engineered + verified):
  - Full text: `https://www.ontario.ca/laws/api/v2/legislation/en/doc-search/{type}/{code}` →
    JSON with `content` = full consolidated text as HTML string (Word-derived markup, needs a
    cleanup pass — `MsoNormal` classes, `\r` litter).
  - Discovery: `/laws/api/v2/laws/autocomplete?term=<t>` + bulk CSV tables
    `/laws/csv/3_regulations_e.csv`.
- Seeds: RRCEA 2016 = `statute/16r12`; Blue Box = `regulation/210391`; Batteries =
  `regulation/200522`; EEE = `regulation/200542`; Hazardous = `regulation/210449`
  (ID pattern `{yy}{padded reg num}` — confirm each via autocomplete).
- Licence: King's Printer permits reproduction of statutes/regs without permission — commercial OK.
- **Risk**: undocumented internal API — add a health check.

### CA second wave
- **Manitoba** (`web2.gov.mb.ca/laws`): clean HTML. Statute `statutes/ccsm/w040.php?lang=en`
  (WRAP Act), regs `regs/current/195-2008.php?lang=en`; discovery via `regs/index.php`
  (846 KB parseable index). OpenMB licence — permissive.
- **Québec** (LégisQuébec): server HTML, no XML. Patterns `/en/document/cs/Q-2` (EQA),
  `/en/document/cr/Q-2,%20r.%2040.1` (REP reg). Gotchas: EN URLs 307-redirect to `/fr/` path
  with `?langCont=en` (follow redirects); bare `Mozilla/5.0` UA intermittently 403s — use a
  full Chrome UA + throttle. Licence unclear (no reproduction order) — **flag for counsel**,
  build anyway for analysis use.
- **Alberta**: King's Printer digital PDFs are FREE (paywall is print-only, contrary to old
  intel): `kings-printer.alberta.ca/documents/Regs/2022_194.pdf` = EPR Regulation AR 194/2022.
  Licence explicit commercial-OK. Needs `pdf_to_text()`.
- **Saskatchewan**: JSON catalog API `publications.saskatchewan.ca/api/v1/products/{id}` →
  `/formats/{fid}/download` (PDF). Search param broken — curated seeds. Licence unverified.
- **Nova Scotia**: HTML is trivial (3–4 h) but site terms = non-commercial only — **hold until
  licensing is resolved.**

---

## AUSTRALIA — federal + shared-grammar states first, ~10–14 h core

| Jurisdiction | Grade | Fetch | Effort |
|---|---|---|---|
| Federal | A | OData API + HTML text view | 4–6 h |
| NSW + QLD + TAS | A/B | ONE shared adapter (same URL grammar) | 6–8 h total |
| ACT | B | DOCX | 4–6 h |
| WA | B | HTML (Lotus-Notes quirks) | 5–7 h |
| SA | B- | RTF + flaky WAF | 6–9 h |
| VIC | C | DOCX, **restrictive licence** | 6–8 h + legal review |
| NT | C | legacy .doc | defer |
| AustLII | E | Cloudflare-blocked + bulk prohibited | **do not build** |

### AU-1: `AustraliaFederalClient` — Grade A
- Discover: `https://api.prod.legislation.gov.au/v1/titles?$filter=contains(name,'<term>')&$select=id,name,collection,status,isInForce`
  (OData v4, no auth; Swagger at `/swagger/index.html`). Instruments in collection
  `LegislativeInstrument`, same API.
- Version: `GET /v1/versions?$filter=titleId eq '<id>' and isLatest eq true`
  (**the `titles('<id>')/versions` navigation path 404s** — use the entity set).
- Fetch: the API's document `contents` stream is broken — use the website text view:
  `https://www.legislation.gov.au/{registerId}/latest/text` (verified 199 KB server HTML, no UA needed).
- Seeds: Recycling and Waste Reduction Act 2020 `C2020A00119`; Charges Acts `C2020A00121/122/123`;
  RAWR Fees Rules `F2020L01627`; PS Accreditation Rules `F2020L01628`.
- Licence: CC BY 4.0, attribution "Sourced from the Federal Register of Legislation at [date]".

### AU-2: `AustraliaEnActClient` (shared base → NSW/QLD/TAS) — the big win
- Shared URL grammar: `/view/whole/{html|xml}/inforce/current/act-YYYY-NNN`
  (**always `whole`** — the non-whole path returns a TOC fragment).
- **QLD**: XML works — `legislation.qld.gov.au/view/whole/xml/inforce/current/act-2011-031`
  (Waste Reduction and Recycling Act 2011, 2.19 MB official XML; contains both the container
  refund scheme and the plastics bans). No UA needed.
- **TAS**: XML works — `legislation.tas.gov.au/view/whole/xml/inforce/current/act-2022-005`
  (Container Refund Scheme Act 2022). No UA needed.
- **NSW**: HTML only (XML export is a JS form) + **requires browser UA** (403 without) —
  `legislation.nsw.gov.au/view/whole/html/inforce/current/act-2001-058` (WARR Act 2001, CDS in
  Part 5); Plastic Reduction and CE Act 2021 = `act-2021-031`. Regs use `sl-YYYY-NNN` ids.
- Discovery: curated seeds (the relevant set per state is ~5 acts + regs) or A–Z browse crawl.
- Licence: CC BY 4.0 in all three.

### AU second wave
- **ACT**: DOCX at `legislation.act.gov.au/DownloadFile/a/2016-51/current/DOCX/2016-51.DOCX`
  (Waste Management and Resource Recovery Act 2016, the ACT CDS). HTML view is a JS chunk
  loader — use DOCX. Licence unverified (likely CC BY) — confirm.
- **WA**: full HTML exists despite Word/PDF reputation —
  `legislation.wa.gov.au/legislation/statutes.nsf/RedirectURL?OpenAgent&query=mrdoc_48005.htm`
  (WARR Act 2007, 695 KB). Gotcha: Lotus-Notes single-quoted relative hrefs against a `<base>`
  tag; act homepage `main_mrtitle_2758_homepage.html` → scrape current mrdoc id. CC BY 4.0.
- **SA**: RTF at `legislation.sa.gov.au/_legislation-documents/lz/c/a/{slug}/current/{year}.{num}.un.rtf`
  (Environment Protection Act 1993 = `1993.76.un.rtf`, 1.66 MB — CDS Part 8 Div 2, the 1977
  lineage). WAF: 403 without UA, intermittent 403 WITH UA — retry once. CC BY 4.0.
- **VIC**: fetchable DOCX (`content.legislation.vic.gov.au/sites/default/files/...docx`, path
  not predictable — two-hop scrape from `/in-force/acts/{slug}` version pages), but copyright
  page says authorised versions are personal-use-only, NOT CC — **the one Australian
  jurisdiction needing legal review before shipping.** (CE (Waste Reduction and Recycling)
  Act 2021 = doc series `21-55a{ver}`.)
- **NT**: Sitecore API serves legacy binary `.doc` (`/api/sitecore/Act/Word?id=11793`) — needs
  LibreOffice conversion; smallest jurisdiction, defer.

---

## Build phases

**Phase 1 — core value, ~30–40 h** (all Grade A/A-, no new deps except `docx_to_text`):
1. `docx_to_text()` helper (stdlib)
2. CN flk (CN-1) + gov.cn (CN-2) — China goes from zero to national coverage
3. CA federal + BC + Ontario — covers the two flagship provincial EPR regimes
4. AU federal + shared NSW/QLD/TAS adapter — covers CDS in the 3 easiest states
5. Classifier REGION_LABELS for CN/CA/AU

**Phase 2 — fill-in, ~25–35 h**: Manitoba, Québec (counsel flag), ACT, WA, SA
(+ `rtf_to_text`), CN-3 NDRC/MEE seeds.

**Phase 3 — PDF gate, decide once**: add `pdf_to_text()` → Alberta + Saskatchewan
(+ retro-unlocks Malta from the EU fan-out deferred list).

**Blocked/deferred**: NS (non-commercial licence), VIC (licence review), NT (.doc), AustLII +
CanLII (prohibited — never build on aggregators; every official portal is directly accessible).

**Reminder**: the entire foreign corpus (23 jurisdictions, ~535 relevant laws) is still
LOCAL + largely uncommitted — prod deploy of the existing corpus is the gate to users and
should not wait for these three countries.
