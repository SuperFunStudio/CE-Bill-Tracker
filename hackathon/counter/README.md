# ▭ Counter — what the law asks of the store

**EPR laws are written about producers, but stores carry them out.** The cashier adds the
mattress fee at the register. The bin by the door takes back batteries. The buyer pulls
a SKU because its brand isn't on the state's registered-producer list. Counter takes a
retailer's store list and product categories and gives each store one card: **the fees
to charge, what to take back, what you may not sell, and what signage to post.** Every
line cites its clause.

> Hackathon concept from the **"Marisol Ybarra" persona**, *The Store Walker*
> (ops 50 · design 30 · business 20).

---

## The persona

**Marisol Ybarra**, 44. She uses she/her.

- **Ops, first.** Eleven years in store operations at a regional home-improvement chain:
  140 stores in nine states. She ran the rollout of the battery take-back bins, store by
  store. Two stores in one state were cited because the bin was in the back room and not
  "at a location accessible to the public." Nobody at head office had read that clause.
- **Design, second.** She owns the planogram and signage standards. She designed the
  register prompt that tells a cashier to add a fee. She thinks in shelf feet, sign
  heights and what a 19-year-old cashier can do in four seconds.
- **Business, third.** She signs off on the compliance line in the store P&L. She knows
  what it costs when a district manager guesses wrong.

**Her thesis, in one line:**

> *"Every entry so far was built for someone upstream of the shelf: the brand that pays,
> the seller who imports, the recycler who receives, the advocate who lobbies. The law
> lands in my stores. It's a fee on the receipt, a bin by the door, a sign at eye level,
> and a list of brands I can't stock. Give me that per store, with the clause, and I'll
> push it to 140 district managers on Monday."*

**What she does today.** A shared drive of state memos, mostly from the trade association,
plus a vendor-compliance spreadsheet that the buying team updates when they remember. The
paint, mattress and battery programmes each send their own retailer packet in their own
format.

---

## The concept

Producer laws give retailers four kinds of duty. Atlas already holds the statute text for
almost all of them. Nobody has pulled them out from the store's side.

| Duty | What it looks like at the store |
|---|---|
| **Charge** | A visible per-unit fee at the register (mattresses, paint, some electronics), remitted to the programme |
| **Collect** | Accept products back, often only if the store sells that category, sometimes only above a floor area |
| **Check** | Don't sell products from a producer that isn't registered or in a programme |
| **Tell** | Post signage or give customers information about where to return the product |

Counter does three things:

1. **The store card.** One page per store: the four duties for that store's state (and
   city, where Atlas has ordinance rows), filtered to the categories the store sells.
   Each line shows the clause excerpt and a link to the law in Atlas.
2. **The do-not-sell check.** The buyer uploads a vendor list. Counter checks it against
   the public registered-producer lists that state programmes publish, and flags brands
   with no listing in a state where the chain sells that category.
3. **The coverage map.** Where statutes set a convenience standard, such as a drop-off
   site within a set distance for a share of residents, Counter overlays the chain's
   stores on the programme's published collection sites and the population grid. A store
   that would close a gap is a store the programme may want to recruit, and may pay.

### The demo, in about 30 seconds

1. Load **Ridgeline Hardware** (fictional): 140 stores in nine states, selling paint,
   batteries, small electronics and a mattress line in 30 stores.
2. Click a store in **Washington**. The card shows battery collection, with the clause and
   the programme to call. It also flags that the mattress line isn't sold here, so the
   mattress duty is greyed out with the reason.
3. Click a store in **California**. A register-fee row appears for mattresses and paint.
   Each fee shows its source: the programme's published charge, with the date it was
   last checked.
4. Switch to **do-not-sell**. Two battery brands are flagged in two states: "no listing
   found on the state's producer list, checked 2026-10-20."
5. Switch to **coverage**. Three rural stores light up as sitting in collection gaps.
6. Export: a district-manager PDF per store, and a CSV of register prompts for the POS team.

---

## Data

### From Atlas (prod API, all live)

| Endpoint | What Counter takes from it |
|---|---|
| `GET /bills/search` | Full-text search over statute text. Finds the retailer clauses ("retailer" near "collection site", "not registered", "point of sale") and returns highlighted excerpts |
| `GET /bills/laws-in-force` | Only in-force law creates a store duty. Pending bills appear as "coming" |
| `GET /bills/{id}` | Product coverage and instrument type, used to match a law to the categories the store sells |
| `GET /bills/{id}/text` | The full text the clause excerpt comes from, for a reviewer to check |
| `GET /compliance/pathways` | The programme (PaintCare, Call2Recycle, the mattress council and so on) that sends the retailer packet |
| `GET /compliance/deadlines/upcoming` | Programme start dates. A store duty usually begins when the programme does |

Checked against prod on 2026-10-20 (US only; the search returns at most 200 hits):

| Query | Enacted laws | States |
|---|---|---|
| `retailer battery` | 43 | 19 |
| `retailer paint` | 19 | 13 |
| `retailer mattress` | 9 | 4 |
| `retailer electronic` | 55+ (capped) | 22+ |
| `retailer "collection site"` | 44 | 20 |
| `"convenience standard"` | 9 | 6 |

### Public data sets

| Data set | Use |
|---|---|
| **State registered-producer and brand lists** (for example CalRecycle's covered electronic device lists and state battery and paint programme lists) | The do-not-sell check. Lookup per state, with the check date shown |
| **Programme site locators**: Call2Recycle, PaintCare, Mattress Recycling Council | Existing collection sites, for the coverage map |
| **Programme retailer fee schedules** (PaintCare per-container fees, mattress recycling charges, the California electronic waste recycling fee published by CDTFA) | The register-fee row. Shown with source and last-checked date |
| **US Census ACS block-group population** | People within the convenience radius of each site and store |
| **Census County Business Patterns** (NAICS 444, 449, 455) | Counts of hardware, furniture and general-merchandise stores per county. Sizes the market: how many stores each duty touches |
| **OpenStreetMap** shop tags | Fallback store locations when a chain won't share its list |

---

## How it is built

- **A clause tagger.** A small script runs a fixed set of retailer queries against
  `/bills/search`, keeps in-force hits, and tags each excerpt as charge, collect, check or
  tell. An LLM proposes the tag; a person accepts it. The result is a reviewable file of
  about 150 rows, keyed to bill ID, so every store-card line traces to a clause.
- **A thin join service** in Node: stores and categories in, cards out. It caches the
  programme lists and locators. It holds no legal logic beyond the tagged file.
- **A one-page front end** with a store map, the card panel, the do-not-sell table and the
  coverage overlay. It uses the colour-vision-safe palette already in dashboard-next.
- **Day one:** store cards for batteries, paint and mattresses in the US, from the tagged
  file. **Day two:** do-not-sell for two states, the coverage map, and exports.

---

## Honesty rules

- **A store card with no line for a category says "no duty found in tracked law," never
  "no duty."** Full-text search can miss a clause worded differently.
- **Every line shows its clause.** No paraphrase without the excerpt next to it.
- **Fees are quoted, never estimated.** A fee row shows the programme's published figure,
  its source and the date it was checked, or it doesn't appear.
- **"Not on the list" means not found, not non-compliant.** Brand names on state lists
  vary. Counter shows the closest matches and asks a person to confirm.
- **Coverage gaps are measured against the statute's own standard.** Where a law sets no
  convenience standard, Counter shows sites and stores but draws no gap.
- **US first, and it says so.** The search index is English-language. EU retailer duties
  (WEEE take-back by floor area, for example) are a stretch goal, not a silent omission.

---

## Known gaps, found while scoping

- **Retailer duties aren't structured.** `compliance_details` holds producer obligations,
  fees and targets, but no retailer field. The tagged file is the stopgap. A
  `retailer_obligations` extraction is the obvious follow-up if this wins.
- **Search caps at 200 hits.** Broad queries such as `retailer electronic` hit the cap.
  The tagger runs narrower queries per state to get round it.
- **Search finds words, not duties.** "Retailer" also appears in definitions and
  exemptions. That's why a person reviews every tag.
- **City ordinances are thin.** Atlas has some city rows (bag fees, for example), but not
  enough to promise city-level cards everywhere.
- **Programme lists change monthly.** The do-not-sell check is only as fresh as its last
  lookup, and every row says when that was.

---

## Why it belongs in the product

- **A new buyer.** Retail compliance and store operations at multi-state chains. No
  earlier entry served the retailer, and one seat covers every store.
- **It fills a gap the last entry found.** *Landed* flagged that marketplace operator
  duties are missing and deserve their own row type. Counter builds that row type for
  physical stores, and the same model can cover marketplaces next.
- **It uses the full-text index nobody showed off.** Layer B search exists but has had no
  surface built around a job. Counter gives it one.
- **It brings producers in through their customers.** A brand flagged on a retailer's
  do-not-sell report has a reason to look up its own obligations on Atlas the same day.
