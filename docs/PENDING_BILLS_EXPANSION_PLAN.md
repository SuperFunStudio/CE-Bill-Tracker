# Pending bills: expansion plan

Audit of 30 Oct 2026. Which regions can get pending-bill tracking, from which source, and in what order.

## Where we are

- Every adapter in `FOREIGN_CLIENTS` except two reads only enacted law. The exceptions:
  - `BR_CAMARA`, with lifecycle tracking.
  - `EU_TRIS`, which tracks draft technical rules from EU member states plus NO, CH, TR and UK.
- `eurlex.py` pulls only enacted acts (CELEX sector 3). Commission proposals are not tracked.
- A source joins the pending pipeline by setting `tracks_status = True` and supplying a status map onto the canonical vocabulary. `sync_foreign` then handles the rest: refreshing every non-final row, recording `status_change` events, and re-classifying only rows whose text changed. This is the cost per adapter in the estimates below.

## Source probe (live, 30 Oct 2026)

Each source was searched with a native-language packaging or waste keyword where it supports one.

### Tier 1: proper API with a status field, in a high-value market

| # | Region | Source | Status signal | Notes | Est. |
|---|---|---|---|---|---|
| 1 | BR | **Built 30 Oct (`BR_SENADO`).** Senado `legis.senado.leg.br/dadosabertos/processo` | `dataSituacaoAtual`, author, ementa | The old `/materia/pesquisa` endpoint is deprecated (shut-off date 1 Feb 2026, still answering); build on `/processo`. PL 2524/2022 returns correctly. | ½ day |
| 2 | PL | Sejm `api.sejm.gov.pl/sejm/term10/processes` | `stages[]` with dates, `passed`, `rclNum`/`rclLink` | Same host as the `PL` ELI adapter. `rclLink` bridges to the government draft at RCL. The `title=` filter works. | ½ day |
| 3 | UK | Bills API `bills-api.parliament.uk/api/v1/Bills` | `currentStage`, `isAct`, `isDefeated`, `billWithdrawn` | Cleanest API probed. UK is our third-largest foreign corpus. | ½ day |
| 4 | EU | CELLAR SPARQL, CELEX `5YYYYPC…` | Procedure stage needs OEIL (HTML) | Reuses the EUROVOC discovery in `eurlex.py`. 481 COM proposals in 2025 before filtering. Send `Accept: application/sparql-results+json` (the `format=` param returns 406). | 1 day |
| 5 | FR | Sénat `data.senat.fr/data/dosleg/dossiers-legislatifs.csv` | "État du dossier", promulgation date and law number | One bulk CSV (3.6 MB, Latin-1) covers bills from both chambers. Draft decrees already come through TRIS. | ½ day |
| 6 | DE | Bundestag DIP `search.dip.bundestag.de/api/v1/vorgang` | `beratungsstand` | Needs an API key. The public key in circulation has expired (401). Request a free personal key from the Bundestag rather than scraping the help page, which is rendered by JavaScript. | ½ day after the key arrives |

### Tier 2: good APIs, smaller corpus

| Region | Source | Status signal | Notes |
|---|---|---|---|
| SE | Riksdagen `data.riksdagen.se/dokumentlista?doktyp=prop` | document status | Same API as the `SE` adapter. Flaky: one 200 and one dropped connection on 30 Oct. |
| NL | Tweede Kamer OData `gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/Zaak` | `Status`, `Afgedaan` | Filter on `Soort eq 'Wetgeving'`. |
| DK | Folketinget ODA `oda.ft.dk/api/Sag` | `statusid` | OData v3 (`substringof`). |
| CH | Curia Vista `ws.parlament.ch/odata.svc/Business` | `BusinessStatusText` | Includes parliamentary questions, so filter by business type. Fedlex consultations cover the draft stage. |
| IT | Senato SPARQL `dati.senato.it/sparql` | `statoDdl`, `dataStatoDdl` | Camera has a parallel SPARQL endpoint. Decree-laws must be converted within 60 days, so they move fast. |
| IE | Oireachtas `api.oireachtas.ie/v1/legislation` | `bill_status`, events | |
| CA | LEGISinfo `parl.ca/legisinfo/en/bills/json` | stage fields | Federal only. Provinces are separate. |
| CL | Senado `tramitacion.senado.cl/wspublico/tramitacion.php` | `estado`, `etapa` | XML, looked up by boletín. |
| NO | Stortinget `data.stortinget.no/eksport/saker` | `status` | Session-wide dump of about 1.8 MB. |
| ZA | PMG `api.pmg.org.za/bill/` | `status` | Third-party API (Parliamentary Monitoring Group). |
| AT | Parlament `parlament.gv.at/Filter/api/filter/data/101` | `PHASEN_BIS` | Returns 58 MB unfiltered. Find the filter params before using it. |

### Tier 3: draft or consultation stage only, or HTML scraping

| Region | Source | Notes |
|---|---|---|
| JP | e-Gov public comment RSS `public-comment.e-gov.go.jp/rss/pcm_list.xml` | Covers all ministries, so filter by keyword. On 30 Oct it listed a live consultation on an amendment to the Waste Management Act's enforcement order. |
| KR | `opinion.lawmaking.go.kr` (입법예고) | HTML. The National Assembly API needs a key. |
| MX | SIL `sil.gobernacion.gob.mx`; Gaceta `gaceta.diputados.gob.mx` | HTML. The Gaceta's TLS chain fails verification, so it needs a CA bundle workaround. CONAMER (draft regulations) not yet probed. |
| IN | PRS Bill Track `prsindia.org/billtrack` | HTML. EPR rules arrive as MoEFCC draft notifications in the eGazette, not as bills, so the eGazette is the real draft source. |
| CO | Cámara `camara.gov.co/proyectos-de-ley` | HTML, about 1 MB. |
| ES | Congreso open data `congreso.es/es/opendata/iniciativas` | The dataset download URL is not yet identified. Spanish draft rules come through TRIS. |

### Blocked

| Region | Source | Problem |
|---|---|---|
| AU | APH bills search | The site's firewall returns 403 to scripted requests. |
| TW | Legislative Yuan open data | The server needs legacy TLS renegotiation, which our HTTP client refuses. |
| PE | Congreso spley-portal | The guessed endpoint returns 404; the real one still needs finding. |

## Do these before adding more regions

1. **Check classifier precision on short text.** Pending bills often arrive as a title plus a one-line ementa. Before scaling, run the classifier on about 50 Senado, Sejm and UK bills and compare it with a manual label. Where a source offers full text (Senado *inteiro teor*, Sejm print PDFs, UK bill PDFs), fetch it.
2. **Link a pending bill to the law it becomes.** Once the Senado, Sejm and UK feeds are live, the enacted-law adapter will create a second row for the same law. Link the two, or suppress one, before the duplicates add up. `app/ingestion/bill_matcher.py` may be a starting point.
3. **One status map per source,** each with a test, following the pattern of `BR_CAMARA_SITUACAO`.

## Build order

~~Senado~~ (built) → Sejm processes → UK Bills → EU proposals → FR Sénat → DE DIP (once the key arrives).

Run the classifier check next, on the first Senado batch, before Sejm. That way puts the precision measurement before the larger feeds. Tier 2 sources go in as demand appears, by customer market.

## Corpus gaps found during the probe

- **IT:** d-l 143/2026, which makes compostable certification (UNI EN 13432) mandatory for single-use plastic HoReCa dine-in and condiment packaging and for small fresh-produce packs. Takeaway packaging for ready-to-eat food is exempt. Converted by L. 173/2026 (5 Oct 2026). Added to `IT_SEED_LAWS` on 30 Oct.
- **JP:** a draft amendment to the Waste Management Act's enforcement order is in public comment now.
- **PL:** UC100 is still not in the Sejm. The two packaging processes in term 10 (760 and 2112) are the 2024 and 2025 amendments to the deposit-return system, both passed. The deposit-return repeal draft (TRIS 2026/0550/PL) has no Sejm process yet.
