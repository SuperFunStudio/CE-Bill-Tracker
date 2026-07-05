# ◇ Swap Studio — the material cost curve

**Price the package you haven't drawn yet.** Build a package from components, pick your
US markets, then **swap a material** and watch the Extended Producer Responsibility bill
move — fee-per-tonne, obligations, PROs, deadlines — all recomputed live against the
[SignalScout API](https://signalscout-api-36712717703.us-central1.run.app/docs).

> Hackathon entry from the **"Theo Marchetti" persona** — *The Material Choice*
> (design 45 · business 35 · dev 20). Industrial/packaging designer who once shipped a
> "nicer" aluminum cap that quietly picked up three states' worth of EPR obligations.
> His thesis in one line:
>
> *"Every other entry on this board checks compliance **after** the package exists —
> audits, cards, CI gates, short books. But I'm the person who **chooses the material**.
> Compliance isn't a test you pass at the end; it's an input to a sketch. Move the
> intervention upstream to the moment of material choice, and the fee schedule becomes a
> design constraint like weight or cost. Show me the package I haven't drawn yet."*

Everyone else on the board optimizes around a fixed spec. **Swap Studio changes the spec.**

## Why it's a different demo

- **A new moment in the funnel.** Comply-by-Friday says *do this by Friday*; Spec-Sheet
  Guard *blocks the bad merge*; the MCP server answers *am I compliant?*. All of them act on
  a package that already exists. This one lives **before** the package exists — at the
  drawing board, where the material is still a decision.
- **The swap is the product.** Click any bar on a component's cost curve and the whole
  spec re-prices instantly: PP cap → PET cap drops a 5M-unit line's fee from **~$180k/yr to
  ~$149k/yr**, and the obligation list redraws. Design becomes a fee-optimization loop.
- **Grounded, not vibes — and honest about which layer is which:**
  - *What applies* is **live**: `GET /compliance/pathways?state=XX` (public / free tier) —
    the real enacted-law obligations, PROs to join, and deadlines per state, matched to the
    materials in your spec, split into **action-required** vs **monitor-only**.
  - *What a swap costs* is **published**: the California SB 54 (2027) producer fee schedule
    (Circular Action Alliance, Ch.9 Table 5) — per-material eco-modulation rates in ¢/lb →
    $/tonne. This is the same grounded anchor the SignalScout API itself uses
    (`app/scoring/ca_sb54_fees.py`): published-with-citation reference data, not an LLM guess.

## Run it

```bash
cd hackathon/swap-studio
node server.mjs           # Node 18+ — zero npm dependencies
# open http://localhost:4820
```

Config (optional):
- `SIGNALSCOUT_API_BASE_URL` — point at a local/staging API instead of prod.
- `PORT` — defaults to `4820`.

## How it works

`server.mjs` is a ~260-line zero-dependency **quote engine** (Node built-in `http` + global
`fetch`). It fans out one `/compliance/pathways` call per selected state, indexes every
enacted law by the canonical material category it covers, and for each component in your
spec computes:

| Output | Source |
|---|---|
| fee $/tonne + ¢/package | CA SB 54 Table 5 rate for that material format |
| **eco-modulation spread** (best↔worst format) | the published low/high format in that material family — the redesign headroom, quantified |
| **cost curve** (every material, ranked, with Δ vs current) | the fee table, sorted cheapest → dearest |
| action-required obligations + PROs + deadlines | live `/compliance/pathways`, filtered to that material's category |

It proxies the API server-side, so the browser never hits the CORS allowlist.
`public/index.html` is the entire front end (no build step): a component bench on the left,
and on the right the package's fee headline, a live obligation panel, and a per-component
**cost curve** you click to swap.

```
/compliance/pathways?state=CA  ─┐
/compliance/pathways?state=OR  ─┼─► index by material category ─┐
/compliance/pathways?state=CO  ─┘                               │
                                                                ├─► buildQuote() ─► cost curve + obligations ─► UI
CA SB 54 (2027) fee schedule (¢/lb → $/tonne, best/worst format)┘
```

## Honest scoping

- **US markets only.** Fees are priced in California terms because CA is the only US program
  with per-material rates published in enough detail to price a redesign. That basis is wrong
  for EU/PPWR law, and the API's `region=EU` filter also mixes US bills into its response — so
  the EU is deliberately out of scope rather than shown misleadingly.
- **`has_fee` is not used.** That flag in the pathways feed is currently always false; the real
  fee number comes from the SB 54 schedule. Obligations are counted by whether they require an
  **action** (`join_pro` / `register_with_state` / `file_individual_plan` / …) vs. monitor-only.
- **Draft schedule.** The 2027 CA rates are the published draft; final rates land October 2026.
  Same caveat the production estimator carries.
- **Format-level, not PCR-level.** The palette uses the real published named formats (clear PET,
  PP/PS foam, corrugated, laminate carton, …). Post-consumer-recycled content and source
  reduction earn *further* bonuses on top; we note that rather than inventing a number.

## Natural next step

Promote the per-material fee table to a public `GET /compliance/fee-schedule` endpoint (it's
pure published reference data — no per-company sensitivity, no LLM cost, no auth concern). Then
Swap Studio's cost layer becomes 100% live-API-grounded, and every other board entry that shows
dollars can read the same endpoint instead of hardcoding the anchor.
