# Methodology graphic: what the Atlas covers, by R-strategy and cycle

**Status:** plan, nothing built. Written 2026-10-19.
**Where it lives:** `/methodology`, as the opening figure of "What we screen for". The Explore count line
("2,593 circular economy laws") links straight to it, so the diagram is the answer to "what counts as one?"

## What the graphic should say

One figure, readable in five seconds: *here is the circular economy, and here is how much of it the
law we track touches.*

- **Shape:** the Ellen MacArthur "butterfly". The technical cycle is one wing, the biological cycle the
  other, and extraction → use → leakage runs down the middle. People in this field already know it,
  so it explains itself.
- **R-strategies on the loops.** Along the technical wing, the R-ladder runs from the tightest loop out:
  R0 Refuse · R1 Rethink · R2 Reduce (design / use) → R3 Reuse · R4 Repair · R5 Refurbish ·
  R6 Remanufacture · R7 Repurpose → R8 Recycle · R9 Recover (energy). The biological wing has its own
  steps: cascade use → composting / anaerobic digestion → regeneration (soil, biodiversity).
- **Each node shows a count.** "Repair · 395 laws". Shading uses the same enacted-laws scale as the maps
  (`lib/mapScale`), so the site keeps one visual language for "more law here".
- **Each node is a link** into Explore, filtered to the laws behind that count.
- **Gaps are shown, not hidden.** A node with little or no law gets the hatched "not tracked / thin"
  treatment from the maps. That makes the coverage claim honest and tells readers what we don't do yet.

## What data exists today

| Dimension | Status | Prod numbers (2026-10-19, 2,593 CE-relevant rows) |
|---|---|---|
| Cycle (technical / biological) | **Available now.** Computed from `material_categories` by `app/classification/cycles.py`. No stored field and no LLM cost. | technical 1,708 · biological 246 · both 245 · unclassified 394 |
| R-strategy | **Not stored anywhere.** Can only be guessed from `instrument_types` for now. | see the mapping below |

### Phase 0 mapping from instrument to R-strategy

This is good enough for a first version of the figure, as long as it is labelled as derived from
instrument type.

| Instrument | Laws | Maps to | Confidence |
|---|---|---|---|
| right_to_repair | 395 | R4 Repair (some R5) | high |
| deposit_return | 254 | R3 Reuse (refillables) + R8 Recycle (one-way) | medium: can't tell refill from recycle without text |
| recycled_content | 149 | R8 Recycle (demand side) | high |
| disposal_ban | 51 | R8 Recycle / R9 Recover (keeps material out of landfill) | medium |
| organics_diversion | 29 | biological: composting / AD | high |
| chemical_restriction | 137 | R1 Rethink / design (safer inputs) | medium |
| labeling | 421 | R1 Rethink (informs choice) + R8 (recyclability labels) | low |
| incentives | 434 | depends on what is funded | **can't map** |
| **epr** | **1,285** | spans R2 through R8 (eco-modulation → design, take-back → recycle) | **can't map honestly** |
| other / budget / preemption | ~570 | — | **can't map** |

**The problem:** about 2,300 of the 2,593 rows are EPR, incentives or "other". Those are exactly the
instruments that span several R-steps, so an instrument mapping leaves the biggest part of the corpus
unplaced. A Phase 0 figure would show Repair and Recycle as well covered and everything else as thin,
which says more about our labels than about the law.

## Plan

### Phase 1: a cycle-only figure (ships with frontend work alone)
- Draw the butterfly with **wing-level** counts from `cycles.py`, plus a material breakdown per wing.
  The material axis is well tagged, so these numbers are solid.
- R-strategy labels appear on the loops as **descriptive** text with no counts yet, and a footnote
  says per-strategy counts are coming.
- Needs a small aggregate endpoint (`GET /bills/coverage/cycles`: wing → count, wing × material →
  count) or a client-side roll-up of the already-public bill list. The roll-up is fine at today's size.

### Phase 2: classify R-strategies properly
- Add `r_strategies TEXT[]` to `bills`: multi-label, primary first, mirroring `instrument_types`.
- Extract it in the existing Haiku classification pass, with a short evidence quote per strategy, the
  same pattern as `compliance_details`, so every count can be traced to statute text.
- **Validation before backfill:** hand-label a golden set of about 150 laws, stratified by instrument
  (heavy on EPR and incentives), and report per-strategy precision and recall. Ship only strategies
  that reach a precision bar we agree on in advance. Show the rest as "coming".
- Backfill the corpus in one pass. Estimate the token cost before running it.
- Expose the field as an Explore facet ("Strategy") and a `?strategy=` URL param. Today Explore filters
  aren't URL-synced (only `?regions=` is), so the diagram's node links need that param first.

### Phase 3: the full figure
- Per-node counts for every R-step on both wings, the shared enacted-laws shading, hatched gaps, hover
  for the count, click through to the filtered Explore table.
- Build as inline SVG, theme-aware (light and dark tokens), with no chart library. The node layout is
  fixed, so this is a drawing, not a chart. Use the dataviz skill's palette checks for the shading.
- Mobile: the two wings stack vertically, technical first, with the same nodes and the same links.

## Decisions needed

1. **Framework.** The 10R ladder (Potting et al., used by the Dutch government and the EU) or the
   butterfly's own loop names (maintain / reuse / refurbish / recycle)? Recommendation: 10R on the
   technical wing and butterfly names on the biological wing, because 10R has no good biological steps.
2. **What "laws" means in the count.** Explore now says "2,593 circular economy laws", but that number
   includes introduced bills and bills in committee. About 1,061 are enacted laws in force. Either the
   count line becomes "laws and bills", or the diagram counts enacted law only, which matches the
   maps. Recommendation: the diagram counts **enacted** law. It is a coverage claim, and only enacted
   law is comparable across countries.
3. **Do cycle and strategy become Explore filters?** That's needed for the diagram's click-through, and
   it's a cheap win in its own right once Phase 2 lands.
