# Gap-B: Cross-jurisdiction enabler curation (out-of-corpus)

## Why

Gap-A (scripts/recall_enablers.py) proved the enablers you actually want — green public
procurement, recycled-content mandates, right-to-repair — are NOT sitting misclassified in the
corpus; they were **never ingested** (foreign law bypasses the ingest keyword gate, and non-bill
instruments — procurement regimes, framework acts, programs — aren't what the adapters pull). This
is the same hole the US-federal seed just filled ([federal-enablers-corpus]), now applied to other
jurisdictions. Curation, not recall, is the lever for cross-jurisdiction enabler coverage.

## What the data proved (prod, 2026-08-03)

Enabler coverage by region (ce_relevant):

| region | total | recycled_content | right_to_repair | incentives | epr |
|--------|------:|-----------------:|----------------:|-----------:|----:|
| EU     | 208   | 4                | 1               | 13         | 62  |
| FR     | 122   | 1                | 18              | 12         | 65  |
| JP     | 113   | 10               | 17              | 9          | 57  |
| UK     | 89    | **0**            | **0**           | 15         | 49  |
| AU     | 41    | **0**            | **0**           | 1          | 19  |
| SE/NL/CA/DE | 15-34 | **0**        | **0**           | 0-1        | ~   |

- **UK has zero** recycled-content and zero right-to-repair; EU is thin (4 / 1). AU/SE/NL/CA/DE ~0
  on both. "procurement" appears in EU 2 / UK 0 titles.
- Landmark instruments **missing**: EU **Public Procurement Directive 2014/24** (the GPP legal
  basis) and the **2024 Right-to-Repair Directive** (32024L1799). Present already: ESPR (32024R1781),
  PPWR (32025R0040), Waste Framework CE package (32018L0852) — dedupe against these.

## Sourcing (both keyless, both verified)

- **EU** — reuse `app/ingestion/eurlex.py` `EurLexClient.fetch_act(celex)` (EUR-Lex/CELLAR, already
  in the prod pipeline: celex_id dedup + bill_texts + region="EU"). Adding an EU enabler = adding a
  CELEX id to a curated list and running fetch_act → classify → insert. Near-zero new code.
- **UK** — `https://www.legislation.gov.uk/<type>/<year>/<num>/data.xml` is keyless and returns full
  text + metadata (verified on Procurement Act 2023, ukpga/2023/54). Add a `legislation_gov_uk`
  fetch mode to `app/ingestion/federal_text.py` (parse XML like the eCFR branch) + a foreign_id-keyed
  import (region="UK"), classified via `HaikuClassifier`.

## Curation targets — Wave 1 (EU + UK)

EU (via CELEX, EurLexClient):
- 32014L0024 Public Procurement Directive 2014/24 — GPP legal basis → recycled_content/incentives
- 32024L1799 Right to Repair Directive (EU) 2024/1799 → right_to_repair
- 32019L1161 Clean Vehicles Directive (green vehicle procurement) → recycled_content/incentives
- 52020DC0098 Circular Economy Action Plan (COM/2020/98) — landmark roadmap (non-binding) → other
- (candidates: 32014L0025 Utilities Procurement; GPP criteria communications)

UK (via legislation.gov.uk):
- ukpga/2023/54 Procurement Act 2023 (National Procurement Policy Statement hook) → recycled_content/incentives
- ukpga/2021/30 Environment Act 2021 (EPR / DRS / resource-efficiency powers) → epr
- uksi/2021/745 Ecodesign for Energy-Related Products & Energy Information Regs 2021 (repair/spares) → right_to_repair
- DRS + packaging EPR regulations as they come into force → deposit_return / epr
- (candidate, from gov.uk not legislation.gov.uk: PPN 06/21 Carbon Reduction Plans in procurement)

Wave 2 (later): CA / AU / JP / DE / NL / SE procurement + repair — each ~10-15 curated items.

## Design (reuse the federal-seed pipeline)

- Seed: `data/seed/_foreign_enablers_raw.json` with `{key, region, celex|leg_uk_id, title,
  kind, enacted_date, source_url, fulltext_url|celex, fulltext_kind, theme, materials, summary,
  lifecycle?}` — same shape as the federal seed, plus a region + source-id field.
- Build/validate: extend `build_federal_seed.py` (theme→instrument map is region-neutral) or a sibling
  `build_foreign_seed.py`; live-validate URLs.
- Import: EU rows go through EurLexClient (celex_id dedup); UK rows through a foreign_id importer with
  the new UK fetch mode. Same guardrails: dry-run default, `--dsn` prod tunnel, skip live dupes,
  `classification_changes`/audit where relevant, region-tagged.
- Lifecycle/rollback tracking carries over (status="repealed" + compliance_details.lifecycle) for
  any superseded directive.

## Decisions (LOCKED 2026-08-03)

- **Wave 1 = EU + UK together** — build the UK legislation.gov.uk fetch mode this wave.
- **Families = procurement + right-to-repair + framework acts + funding/incentives** (broad set, not
  just the two zero-gaps).
- Wave 2 (CA/AU/JP/DE/NL/SE) deferred.

Build order: (1) research + assemble `data/seed/_foreign_enablers_raw.json` for EU+UK across the four
families (dedupe vs CELEX already present: ESPR/PPWR/Waste-Framework); (2) add `legislation_gov_uk`
fetch mode; (3) local dry-run → commit; (4) prod deploy (EurLex reuse + UK importer via proxy) + build.

## Out of scope

Municipal/city procurement (a later drill-down); non-English full-text translation (the foreign
ts_rank≈0 issue — see [research-diversity-funnel-and-foreign-rank]) — English-native UK + EU-English
CELLAR text sidesteps it for Wave 1.
