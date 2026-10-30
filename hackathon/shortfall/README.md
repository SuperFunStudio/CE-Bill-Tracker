# ▤ Shortfall — the feedstock ledger

**The tonnes the law requires that nobody is collecting yet.** Shortfall reads the
recycling and collection targets written into enacted statutes, lines them up against
what each country actually recycles, and turns the gap into one number a recycler can
plan around: **tonnes per year, per material, per market, due by a named year.**

> Hackathon concept from the **"Rosa Achterberg" persona** — *The Bale Counter*
> (ops 50 · engineering 30 · business 20).

---

## The persona

**Rosa Achterberg**, 41. She uses she/her.

- **Ops, first.** Eight years as shift lead and then plant manager at a materials recovery
  facility (MRF) outside Rotterdam. She has stood on the sort line at 2 a.m. when the optical
  sorter jammed on black PP trays. She knows what a bale of mixed plastics sells for, and she
  knows it changes every month.
- **Engineering, second.** She taught herself Python to replace the plant's capacity
  spreadsheet. She now runs inbound logistics for a regional recycler with four plants in the
  Netherlands and Poland. She reads JSON-stat for fun.
- **Business, third.** She sits in the room when the board decides whether to build a fifth
  line. Every one of those decisions is a bet on feedstock that does not exist yet.

**Her thesis, in one line:**

> *"Every entry last time was built for the company that **pays** the EPR fee. Nobody built
> for the company that **receives** the material. A collection target in a statute is a
> purchase order nobody has filled yet. Tell me how many tonnes, of what, where, by when,
> and I'll tell you where to build the next line."*

**What she does today.** She reads the Dutch and Polish packaging decrees herself, pulls
Eurostat tables into Excel, and guesses. The guess decides an €18M capital project.

---

## The concept

Every EPR law with a target is a promise: *X% of material Y recycled by year Z.* Atlas has
already extracted those promises from statute text, with a verbatim source excerpt for each.
Public statistics say how close each country is to keeping them. Nobody has joined the two.

Shortfall computes three things per market and material:

1. **The supply gap.** Target rate minus actual rate, times tonnes generated. This is the
   material producers must pay to collect, and that someone must process.
2. **The demand pull.** Recycled-content minimums times tonnes placed on the market. This is
   the recycled resin that brands are legally obliged to buy.
3. **The squeeze.** Where a large supply gap meets a near deadline and a large demand pull.
   That is where processing capacity is underbuilt and bale prices should rise.

### The demo, in about 30 seconds

1. Open a map of Europe. Each country is shaded by its **plastic packaging shortfall** in
   tonnes for its next binding target year.
2. Click **Poland**. A ledger opens:
   - Statutory target, with the verbatim clause and a link to the law in Atlas.
   - Latest Eurostat recycling rate, with the data year shown.
   - Gap in tonnes per year, and years remaining to close it.
   - Recycled-content minimums that apply, and the resin tonnes they imply.
3. Switch material to **paper**, then **glass**. The map re-shades.
4. Toggle **"show the squeeze"**. The markets where supply gap and demand pull are both
   large light up, ranked.
5. Export the ledger as a CSV that drops straight into a capacity model.

---

## Data

### From Atlas (prod API, all live)

| Endpoint | What Shortfall takes from it |
|---|---|
| `GET /bills/{id}` → `compliance_details.collection_targets` | Material, percent, by-year, basis, and verbatim source excerpt for each statutory target |
| `GET /bills/{id}` → `compliance_details.recycled_content` | Recycled-content minimums by material and year |
| `GET /bills/collection-target-basis` | Which markets measure targets by weight, so the join is apples to apples |
| `GET /compliance/eco-modulation` | Fee criteria that reward recyclability, used to flag which streams producers will push hardest |
| `GET /bills/outcomes` | Documented real-world results, including target misses, shown as context on the ledger |
| `GET /bills/laws-in-force` | Which laws are actually in force, so pending bills never count as obligations |

`collection-target-basis` already shows weight is the dominant target basis in the US,
Poland, the EU, Sweden, the Netherlands, Germany, Spain, France, Ireland and the UK.
That is why the join works on tonnes.

### Public data sets

| Data set | Use |
|---|---|
| **Eurostat `env_waspac`**: packaging waste by material and treatment, per member state | Tonnes generated and tonnes recycled. The denominator and the actual rate. Free JSON-stat API. |
| **Eurostat `env_waselee`**: waste electrical and electronic equipment | Same join for WEEE collection targets. Stretch goal. |
| **US EPA Facts and Figures about Materials, Waste and Recycling** | National US baseline by material. Labelled as national only. |
| **Container Recycling Institute redemption rates** | Actual rates for US deposit-return states, which do have state-level data |
| **EPA Recycling Infrastructure and Market Opportunities Map** | MRF and reprocessor locations, to show where existing capacity sits relative to the gap |

---

## How it is built

- **A small join service** in Node or Python. It pulls enacted, in-force bills with
  `collection_targets.status = present`, normalises material names to Eurostat's waste
  codes, and caches Eurostat responses.
- **A one-page front end** with a choropleth, a ledger panel and a CSV export. It uses the
  shared chart primitive and the colour-vision-safe palette already in dashboard-next.
- **Day-one scope:** EU member states, three materials (plastic, paper, glass), supply gap
  only. **Day-two scope:** demand pull, the squeeze view, and the US deposit-return states.

A material crosswalk is the only hand-built piece. It maps Atlas's free-text target
materials to Eurostat codes. It is small, about a dozen rows, and lives in a reviewable file.

---

## Honesty rules

These come straight from what lost points last time.

- **Every number shows its source and year.** The target shows its statute clause. The actual
  rate shows its Eurostat table and reference year. No blended figures without both.
- **No forecast curves.** Shortfall reports a gap against a statute. It does not predict
  whether the gap closes. Last time, the forward-curve entry lost points for uncalibrated
  weights.
- **The 2020 method break is flagged.** The EU changed how packaging recycling is measured
  from the 2020 reference year. Reported rates dropped for reasons unrelated to behaviour.
  The UI marks the break and never draws a trend line across it.
- **Unit mismatches are excluded, not converted.** A target measured in units or value
  recovered is listed but not summed into tonnes.
- **The US is labelled thin.** Outside deposit-return states, US recycling data is national.
  Shortfall says so rather than inventing state rates.

---

## Known gaps

- **Extraction quality.** Targets are LLM-extracted. Each ledger row shows the verbatim
  excerpt so a reader can check it, and a misread target is one click from being reported.
- **Bulk access.** No endpoint returns targets for many bills at once. The hack fans out
  over bill detail calls and caches. A `GET /bills/targets` endpoint is the obvious
  follow-up if this wins.
- **Thin outcomes feed.** The public outcomes endpoint returns only vetted rows, currently
  six. Shortfall uses them as context, never as an input to the gap.
- **Eurostat lags about two years.** The ledger states the reference year on every rate.

---

## Why it belongs in the product

- **A new buyer.** Recyclers, reprocessors, PROs and municipal operations teams. Every
  earlier entry served producers, advocates or investors. The investor entry was ruled out
  on tier fit. Operators are a Pro-tier buyer with a capital decision on the line.
- **It uses data nobody else touched.** Collection targets and recycled-content minimums
  have been extracted across the corpus but never shown anywhere in the product.
- **It flips the corpus.** Same laws, read from the receiving end of the material flow.
