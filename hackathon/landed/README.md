# ⇲ Landed — who owns the box at the border

**EPR is a landed cost nobody quotes.** Landed takes one seller and the markets it ships
into, and answers the question that comes before any fee: **in each market, is this
seller the obligated producer, or is someone else?** Every answer carries a citation, a
confidence badge, the register to join, and whether an authorised representative is
required.

> Hackathon concept from the **"Dara Lindqvist" persona**, *The Hand-Off*
> (business 45 · ops 35 · design 20).

---

## The persona

**Dara Lindqvist**, 37. They use they/them.

- **Business, first.** Five years running EU expansion for a US direct-to-consumer
  home-goods brand. They opened Germany, France and Spain on Amazon, then watched listings
  get blocked because the brand had no LUCID registration number. Nobody on the team knew
  the brand was the producer. Everyone assumed the marketplace or the freight forwarder was.
- **Ops, second.** Now head of seller onboarding at a cross-border fulfilment company in
  Venlo, on the Dutch-German border. About 300 non-EU sellers keep stock there. Each one
  asks the same question at onboarding, and Dara answers it from a spreadsheet of tabs.
- **Design, third.** They redesigned the onboarding flow twice. They think in hand-offs:
  the box changes owner at the factory, the port, the warehouse and the doorstep, and the
  law attaches to exactly one of those owners.

**Their thesis, in one line:**

> *"Every entry last time assumed you already knew you were the producer. My sellers
> don't. The fee calculator is commoditised and the PROs give it away. Nobody tells a
> seller in Ohio that the moment their box lands in Duisburg, they are the producer,
> they need a German representative, and VAT registration doesn't count. That sentence is
> worth more than any fee estimate."*

**What they do today.** A spreadsheet with one tab per market, last checked by a
consultant in 2024. Germany's rules changed on 12 August 2026 and the tab still describes
the old ones.

---

## The concept

The obligated party changes with three things: **where the box lands**, **how it got
there**, and **whose name is on it**. A brand owner in one market, an importer in another,
a first seller in Oregon, a domestic supplier in Italy. Atlas already holds a cited table
of these rules. Landed is the first surface that reads it from the seller's side, across
every market at once.

It does three things:

1. **The hand-off map.** One row per destination market. Who is the producer, why, how
   sure Atlas is, and which register and penalty apply.
2. **The entity check.** Does the seller already have a legal entity in the market? A German
   GmbH removes the authorised-representative requirement there. A VAT number does not.
   Landed resolves this from the public legal-entity register, not from the seller's memory.
3. **The portfolio grid.** For a fulfilment company, marketplace agency or freight
   forwarder: sellers down the side, markets across the top, every cell coloured by
   *you are the producer*, *someone upstream is*, or *unknown, verify*. That grid is
   Dara's onboarding queue.

### The demo, in about 30 seconds

1. Type a seller: **Kettle & Pine** (fictional), HQ Ohio, ships through Amazon to DE, FR,
   ES, IT, NL, IE and the UK, and from its own site to CA, OR and CO.
2. Landed looks the company up in the legal-entity register. It finds a US parent and a UK
   subsidiary, and no EU entity.
3. The hand-off map renders:
   - **Germany:** *you are the producer.* Brand-owner rule, guidance confidence. LUCID
     registration, free, up to €100,000 for not registering. Authorised representative
     required since 12 August 2026, with the flag that the Commission has proposed
     suspending that requirement.
   - **Italy:** *your supplier likely discharges it,* unless you import directly.
   - **Oregon:** *the first seller into the state owns it,* which may not be the brand.
   - **A market with no row:** *unknown, verify this yourself.* Never "not obligated."
4. Flip the sourcing toggle from *buys from a distributor* to *imports its own stock*.
   The rows that change light up.
5. Switch to the **portfolio grid** with 300 sellers loaded from a CSV. Sort by "producer
   in a market with no registration on file."
6. Export a one-page onboarding brief per seller.

---

## Data

### From Atlas (prod API, all live)

| Endpoint | What Landed takes from it |
|---|---|
| `GET /compliance/producer-attribution` | Rule, liable party, citation, verbatim quote, confidence, thresholds, register, penalty, authorised-representative rule and open questions, per jurisdiction. Open and unauthenticated. |
| `GET /compliance/pathways` | Which PRO runs each programme, so "you are the producer" ends in "join this one" |
| `GET /compliance/deadlines/upcoming` | Registration and reporting dates per market |
| `GET /compliance/laws-in-force` | Only in-force law creates an obligation. Pending bills appear as "coming" |
| `GET /compliance/fee-schedule` | Shown only for confirmed, binding schedules such as Oregon and Colorado. Never estimated elsewhere |

Verified against prod on 2026-10-20: the attribution endpoint returns 14 jurisdictions.
Germany, France and Spain flag an authorised representative as required.

### Public data sets

| Data set | Use |
|---|---|
| **GLEIF Legal Entity Identifier register**, free API with parent and child links | Finds whether a seller has a subsidiary in each market. This drives the authorised-representative answer. |
| **ZSVR LUCID public register**, Germany | Per-brand lookup: is this brand already registered? Lookup only, no bulk scraping. |
| **EU VIES VAT number check** | Confirms a VAT registration so the UI can say plainly that VAT alone is not enough in Germany |
| **Eurostat Comext**, EU imports by product code and partner country | Sizes each market's inflow of non-EU goods, so the portfolio grid can rank markets by exposure |
| **Eurostat digital economy survey**, cross-border online purchases | Shows the share of shoppers buying from outside the EU, by member state. Context for which markets see the most cross-border parcels. |
| **US Census state import data** | The US-side equivalent for sizing state exposure |

---

## How it is built

- **A thin join service** in Node. It fans out to the attribution endpoint, caches the
  GLEIF and Comext responses, and holds no legal logic of its own. The law stays in Atlas.
- **A one-page front end** with the hand-off map, the sourcing toggle and the portfolio
  grid. It uses the colour-vision-safe palette already in dashboard-next.
- **Day one:** single-seller hand-off map, GLEIF entity check, EU and UK rows.
  **Day two:** portfolio grid from CSV, US rows, onboarding brief export.

It reuses the existing "Who is the producer?" panel on /compliance as its row component.
That panel answers for one company in one market. Landed answers for many sellers in many
markets.

---

## Honesty rules

- **An absent row is "unknown", never "not obligated."** The API docstring already demands
  this. Landed renders silence as a grey cell labelled *verify this yourself*.
- **Confidence is visible on every row.** Statutory, regulatory and guidance get different
  badges. Germany is guidance-level today and the badge says so.
- **Volatile rules carry their flag.** The authorised-representative rule may be suspended.
  The row shows the proposal and its status, not a settled answer.
- **No fee estimates outside confirmed schedules.** The product research concluded the
  wedge is attribution, not fee calculation. Landed stays on the wedge.
- **Entity data is shown with its source.** A GLEIF lookup that finds nothing says "no
  record found," not "no entity exists." Small firms often have no identifier.

---

## Known gaps, found while scoping

These are real defects in the current data, verified against prod on 2026-10-20. Landed
needs the first two fixed before the US and sourcing demos are honest.

- **US rows assume a franchise.** With the franchise flag off, every US state except
  Oregon still returns the franchisor as the liable party. The table was researched for
  quick-service restaurants. A non-franchised seller needs the brand-owner, licensee,
  importer cascade the statutes define, and that is not yet encoded.
- **The sourcing toggle only changes Italy.** The API says sourcing flips the answer in
  Germany, Italy and Spain. Only Italy has a sourcing branch in the resolver. Germany and
  Spain return the same answer whatever sourcing is passed.
- **Coverage is 14 jurisdictions.** Atlas tracks about 37 regions. Everything else renders
  as unknown, which is correct but leaves gaps in the grid.
- **Packaging only.** The carryout-bag, PFAS and deposit-return research exists in
  docs/research but is not encoded as attribution rules.
- **Marketplace operator duties are missing.** Germany and France make marketplaces check
  producer registration. That is why Dara's listings were blocked. It deserves its own
  row type.

---

## Why it belongs in the product

- **A new buyer with a multiplier.** Fulfilment companies, marketplace agencies and freight
  forwarders. One seat covers hundreds of sellers, and each seller is a future Pro account.
- **It ships the wedge.** Product research named producer attribution as the unserved
  question that no software vendor answers. The table exists but has one small panel.
  Landed makes it the whole screen.
- **It forces the right data fixes.** The franchise assumption and the missing sourcing
  branches would hurt any non-restaurant user. Landed makes them visible and gives them
  a reason to be fixed.
