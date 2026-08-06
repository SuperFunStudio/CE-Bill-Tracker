# PRO Tariff Schedule Ingestion — Scoping

**Status:** scoped, not built. **Date:** 2026-08-06.

## Why

Ask-the-Atlas can now say *what a producer must do* everywhere in the corpus, and after the
2026-08-06 fee work it can put a directional number on the cost. It still cannot say **what you will
actually pay**, because that number is usually not in the law. A legislature enacts the duty and
delegates the schedule to a PRO or competent authority; the operative tariff is published afterwards,
by a different body, on a different site, on an annual cycle.

Measured on prod (2026-08-06):

| | count |
|---|---|
| enacted EPR bills, all regions | 638 |
| bills stating any numeric fee amount | 313 |
| footwear bills stating a recurring producer fee | 2 of 23 |
| `compliance_pathway` rows | 1,086 |
| …of which `has_fee = true` | **0** |
| `compliance_entity` rows typed `pro` | **12** (FR 3, JP 1, US 8) |
| `join_pro` pathways | 55, **all US** |

So the atlas names a PRO in 4 of 40+ regions and prices none of them. `compliance_pathway.has_fee`
already exists and is populated nowhere — the schema anticipated this and the data never arrived.

The demand surface, enacted EPR bills by region:
`US 168, EU 103, JP 96, FR 85, UK 61, PL 48, SE 34, NL 30, AU 22, DE 13, CA 13, CN 8, ES 8,
CL 6, IE 6, IN 6, DK 6, IT 6, FI 6, AT 5, BR 5, LU 5`.

## What a tariff actually is

Verified against the CAA Oregon 2026 schedule (parsed with `pypdf`, already in the venv — 3 pages,
clean tabular text):

```
Material Category    Covered Material                              Type   Base Fee   SIM      Final Fee
Printing and Writing Newspapers                                    USCL   5.0 ¢/lb   0.0 ¢/lb 5.0 ¢/lb
Glass and Ceramics   Glass Bottles and Jars & Other Containers     PRO   10.0 ¢/lb   0.0 ¢/lb 10.0 ¢/lb
Metal                Aluminum Aerosol Containers                   N/A   64.0 ¢/lb   0.0 ¢/lb 64.0 ¢/lb
Plastic - Rigid      PET (#1) Bottles, Jugs, Jars (Clear/Natural)  USCL  25.0 ¢/lb   0.0 ¢/lb 25.0 ¢/lb
Plastic - Rigid      PET (#1) Bottles, Jugs, Jars (Pigmented)      N/A   67.0 ¢/lb   0.0 ¢/lb 67.0 ¢/lb
```

The shape is consistent across regimes and is **not** the shape of `compliance_details.fee_amounts`:

- a **rate table** keyed by a scheme-specific material taxonomy, far finer than our 22 material
  categories (PET clear vs PET pigmented vs PET thermoform are three different prices);
- a **basis + unit + currency** (¢/lb, €/t, p/tonne, ¥/unit);
- an **eco-modulation layer** — bonus/malus on recyclability, PCR content, labeling, disruptors.
  UK Year 2 uses red/amber/green with red at 1.2× amber; Citeo cites cumulative bonuses of 15–20%
  and penalties up to 100%;
- a **program year**, reset annually, with the prior year retained (an invoice arrives in arrears);
- a **jurisdiction**, which is often narrower than the PRO — CAA publishes a *separate* schedule per
  US state.

## Source tiering

Assessed by probing real sources, not assumed.

**Tier A — published, stable, machine-parseable.** Build first.
- **US (CAA)** — per-state PDFs at predictable slugs (`/s/OR-2026-Fee-Schedule-Public.pdf`,
  California illustrative fees). Note: `circularactionalliance.org` 302-redirects to
  `static1.squarespace.com`, so the fetcher must follow cross-host redirects. Verified parseable.
- **UK (PackUK / DEFRA)** — base fees and the modulation statement published on `gov.uk` as HTML and
  PDF, with an explicit annual cycle (Year 2 confirmed fees due June 2026). Government-published, so
  no access games.
- **Canadian provinces** (Circular Materials, ÉEQ, Recycle BC) — same North American pattern as CAA.

**Tier B — published but access-hostile.** Needs the foreign-adapter playbook already in this repo
(UA headers, PDF mirrors, retry) — the same class of problem India/Türkiye posed.
- **Italy (CONAI)** — `conai.org` returned **403** to a plain fetch. Rates exist and are public.
- **France (Citeo, Refashion, Ecologic, ecosystem)** — tariffs are published as annual *barème* PDFs;
  the URL guessed here 404'd, so the entry point must be discovered per éco-organisme. Multiple PROs
  per material stream, each with its own schedule. Third-party consultancies republish the tables,
  which is a cross-check but not a citable source.
- **Spain (Ecoembes), Ireland (Repak), Nordics (FTI, Grønt Punkt, Rinki)** — assumed Tier B, each
  needs a probe before committing.

**Tier C — structurally unavailable.** Do not promise coverage here.
- **Germany.** No published tariff exists to extract. VerpackG created *competing* dual systems that
  price commercially; rates are contract terms, not schedules. Public sources only support a
  market-range statement (roughly €0.50–2.00/kg, provenance weak). ZSVR runs the LUCID register and
  sets no prices.
- Any regime where the PRO is not yet appointed, or the first schedule is unpublished — a large slice
  of the 2024–2026 enactments the atlas tracks.

Tier C is the honest boundary: for those, keep today's behavior (say the schedule is set
post-enactment, give the directional estimate).

## Data model

A new table, not an extension of `fee_amounts` — these are different objects with different
provenance and lifecycles. A bill's stated fee is *what the law says*; a tariff is *what the
administrator charges this year*.

```
pro_tariff_schedule
  id, entity_id -> compliance_entity(id), jurisdiction_id, region
  program_year, currency, basis            -- per_lb | per_kg | per_tonne | per_unit
  source_url, source_document_sha, published_date, retrieved_at, parser_version
  status                                   -- draft | illustrative | confirmed | superseded
  UNIQUE (entity_id, jurisdiction_id, program_year)

pro_tariff_rate
  id, schedule_id -> pro_tariff_schedule(id)
  scheme_category                          -- verbatim: "PET (#1) - Bottles, Jugs, and Jars (Clear/Natural)"
  material_category                        -- OUR slug, mapped; nullable when no honest mapping exists
  base_rate, modulated_rate, rate_unit
  eco_modulation jsonb                     -- {basis: "rag", band: "red", multiplier: 1.2} etc.
  source_excerpt
```

Three deliberate choices:

1. **`scheme_category` is stored verbatim and is the citable value.** `material_category` is a
   convenience mapping that will be lossy — our taxonomy has no "PET pigmented vs clear" distinction,
   and inventing one to fit would misprice. Where the mapping is ambiguous, leave it null rather than
   guess.
2. **`status` distinguishes illustrative from confirmed.** UK Year 2 fees were illustrative until
   June 2026; CAA publishes "illustrative fees" for California. Quoting an illustrative rate as
   confirmed is exactly the error the recent prompt work exists to prevent.
3. **`program_year` + never delete.** A producer being invoiced in arrears needs last year's rate.

## Ingestion

Follows `scripts/foreign/` conventions — a registry of per-PRO adapters behind one interface, so a
new PRO is a new adapter, not a new pipeline.

```
scripts/pro_tariffs/
  base.py          # TariffAdapter: discover() -> [schedule_url], parse(bytes) -> [rate rows]
  caa.py           # US states; PDF; follows squarespace redirect
  packuk.py        # UK; gov.uk HTML + PDF
  conai.py         # IT; needs UA/session handling
  citeo.py         # FR packaging; annual barème PDF
  registry.py
scripts/ingest_pro_tariffs.py   # --entity/--region/--year, --dry-run default, idempotent on
                                # (entity, jurisdiction, program_year), audit-logged
```

Cadence is annual per scheme, not continuous — a scheduled job that checks for a new program year is
enough. Parsing is deterministic (pypdf + table heuristics per adapter), with the LLM used only to
map `scheme_category` to our slugs, never to read a number off a page. **A rate is never
LLM-extracted**: a hallucinated tariff is worse than no tariff, because it looks authoritative.

## What it unlocks

- `_fee_benchmarks` gains a first tier above everything it has today: the actual schedule for the
  jurisdiction asked about, cited to the administrator, before falling back to bill-stated fees and
  then the directional estimate.
- `compliance_pathway.has_fee` finally means something, and a pathway can carry "join CAA, here is
  the Oregon rate for your material."
- A real cost calculator becomes possible — weight × rate × modulation band — which is the thing the
  Packaging Studio has always implied but never had numbers for.
- Cross-jurisdiction rate comparison at the *same* material granularity, which the bill corpus
  fundamentally cannot support.

## Phasing

- **P0 — spine + one adapter (CAA).** Migration, `TariffAdapter`, CAA adapter across its published
  states, wired into `_fee_benchmarks` as the top tier. Proves the model against the source already
  verified parseable. Delivers real numbers for the biggest single block of enacted EPR bills.
- **P1 — UK (PackUK).** Second regime, different shape (RAG modulation, HTML+PDF), gov-published.
  Validates that the schema survives contact with a non-US scheme.
- **P2 — Tier B probes.** One spike per source (CONAI, Citeo, Ecoembes, Repak) to convert assumption
  into fact, then adapters for whichever clear. Expect the same access friction as India/Türkiye.
- **P3 — Canada + Nordics**, and a scheduled annual refresh job with a staleness alert (a schedule
  more than one program year old should stop being quoted as current).

Germany and unappointed-PRO regimes stay explicitly out of scope, surfaced as "no published schedule"
rather than silently missing.

## Risks

- **Staleness is the failure mode that matters.** A wrong current-year rate is worse than none.
  Mitigate with `program_year` + `status` + a staleness guard at query time.
- **Taxonomy mismatch** between scheme categories and our materials is permanent, not a bug to fix.
  The plan is to cite verbatim and map loosely.
- **Terms of use.** Several PRO sites restrict reuse of published schedules. Worth a check before
  redistributing rate tables wholesale rather than citing and linking.
- **Effort is per-source and does not amortize well.** Each PRO is its own document format. Tier A is
  days; Tier B is a spike each with a real chance of "not without a login".
