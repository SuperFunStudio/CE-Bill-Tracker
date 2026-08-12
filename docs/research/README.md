# Research briefs

Primary-source research passes, preserved verbatim as point-in-time snapshots. These are **not
maintained** — each is dated and describes the world as it was on that date.

## Why these exist as documents

A research pass produces far more cited material than any single build consumes. The 2026-08-11 passes
below yielded several hundred article-level citations; roughly 15% was encoded into code and specs at the
time. Persisting the full briefs means the remainder is available to the next build without re-running
research against a search budget that these passes exhausted.

## Conventions

- **Every claim carries a URL.** Where a verbatim quote was captured it is quoted; where it wasn't, the
  text says so rather than paraphrasing into quotation marks.
- **"Unverified" means unverified** — a lead, not a fact. It is used in preference to dropping the item
  or filling the gap with a plausible-sounding figure.
- **In-force status is always stated.** Enacted ≠ commenced ≠ enforced. Several findings turn entirely on
  this distinction (Italy's plastic tax deferred an eighth time; Ireland's latte levy never commenced; the
  Netherlands not enforcing its takeaway charge and planning to abolish it).
- **Penalties and rates are cited to article level, never transplanted from an adjacent subtitle** of the
  same act — a trap that trade coverage falls into routinely (see the Colorado/Maryland PFAS penalty note).

## 2026-08-11 — packaging compliance for a multi-market QSR chain

Run to scope `docs/EXPOSURE_CALCULATOR_SPEC.md`. All four passes hit the session's 200-call web-search
cap; each brief's closing section lists what that left open.

| Brief | Covers | Encoded into |
|---|---|---|
| [UK](2026-08-11-uk-qsr-compliance.md) | pEPR franchise sweep-up (Sch. 10), household vs non-household, RAM modulation + red escalator, Plastic Packaging Tax, DRS, SUP bans, carrier bags | `producer_attribution.py` (UK pEPR + PPT); `feeSchedule.ts` (RAM escalator, green-estimate correction) |
| [EU member states](2026-08-11-eu-member-state-qsr-compliance.md) | PPWR timeline, SUPD Art. 8 four-way split, FR / DE / ES / IT / IE / NL registration, tariffs, eco-modulation, labelling, authorised representatives | `producer_attribution.py` (6 country entries) |
| [US states](2026-08-11-us-state-qsr-compliance.md) | The 7 EPR states — producer definitions, thresholds, calendars; OR/CO/CA fee tables; SB 343; foam bans; bottle bills; PCR mandates | `producer_attribution.py` (7 states); `feeSchedule.ts` (OR + CO PY2026 schedules) |
| [Practitioner workflow & vendors](2026-08-11-practitioner-workflow-and-vendors.md) | The annual cycle, the three-clock problem, where packaging data actually comes from, audit regimes by market, competitive landscape, KISS test | `EXPOSURE_CALCULATOR_SPEC.md` §0, §6, §9 — this is the brief that changed the product thesis |
| [US carryout bag laws](2026-08-11-us-carryout-bag-laws.md) | 13 states — restaurant applicability, fee levels, **fee-remittance direction**, paper/reusable specs, local preemption | **Not yet encoded** — `carryout_bag` regime is declared but empty |
| [US PFAS in food packaging](2026-08-11-us-pfas-food-packaging.md) | 15 states — scope (plant-fiber vs all materials), thresholds, **certificate duties incl. NY's duty on the food seller**, penalties, FDA position | **Not yet encoded** — `pfas` is not in the `Regime` vocabulary at all |

### The findings that changed the design

1. **Attribution inverts by jurisdiction.** Oregon's food-serviceware producer is the *first seller*
   (ORS 459A.866(3)), not the brand owner — so a chain may owe nothing there while owing franchisor-level
   fees in five other states for the identical cup.
2. **Tonnage is not the billing unit** in most markets — France bills per sales unit and per *order*, the
   Netherlands per 1,000 units, California a PPMF fee **per plastic component**, Germany a municipal tax
   per item.
3. **Non-EPR charges often exceed the EPR fee** — Spain's €0.45/kg plastic tax, Germany's EWKFondsG at
   €1.236/kg on beverage cups, German municipal packaging tax exceeding €1.50 on one meal.
4. **The bottleneck is grams, not arithmetic.** Fee calculation is commoditised and partly free from the
   PROs; component-level weights from suppliers are what nobody has solved.
5. **Applicability determination is unserved** — 14 law firms have practices on it, zero software vendors
   address it.

### Known coverage gaps

The attribution table built from these briefs covers **14 jurisdictions against Atlas's ~37 regions**, and
only 2 of 5 declared regimes. Missing entirely: Japan, Canadian provinces, Australian states, China,
India, Korea, Brazil, Chile, and the Nordics/CEE — several of which carry more enacted EPR measures in the
corpus than countries that were covered.
