# ◗ EPR Forward Curve

**The "what regulates next" forecast.** Every other entry on the board answers the *present
tense* — what EPR law exists today and what to do about it. This one is the **leading
indicator**: a US map + ranked list of which state is most likely to pass a new Extended
Producer Responsibility law **next**, scored live from the [SignalScout API](https://signalscout-api-36712717703.us-central1.run.app/docs).

> Hackathon entry from the **"Nadia Ferro" persona** — *The Analyst* (business × dev × design).
> An ex-ESG equity analyst's reflex: regulation is a leading indicator, so where's the forward
> curve? The MCP server answers *"am I compliant?"*; Comply-by-Friday says *"do this by Friday."*
> This one says *"budget for Texas before the bill is even introduced."*

## Why it's a good demo
- **One screen, no login, ~10 seconds.** A US heatmap of regulatory pressure + a ranked
  "next to regulate" leaderboard. Click any state for the score breakdown.
- **It's the one tense nobody else built.** Four teams built *now*; this builds *next*.
- **Grounded, not vibes.** Every input is a live public endpoint — pending-bill counts,
  per-state lawmaking propensity, national momentum. The scoring formula is printed on the page.

## Run it
```bash
cd hackathon/epr-forward-curve
node server.mjs           # Node 18+ — zero npm dependencies
# open http://localhost:4720
```
Config (optional):
- `SIGNALSCOUT_API` — point at a local/staging API instead of prod.
- `SIGNALSCOUT_API_TOKEN` — a Pro seat's Firebase token (not required; all feeds are free-tier).
- `PORT` — defaults to `4720`.

## How it works
`server.mjs` is a ~130-line zero-dependency **forecast engine** (Node built-in `http` + global
`fetch`) that fans out to three **public** SignalScout endpoints, computes a per-state Forward
Score server-side, and serves it as `GET /api/forecast`. It also proxies the API server-side,
so the browser never hits CORS. `public/index.html` is the entire front end (no build step): a
national tailwind gauge, an inline **tile-grid US map** colored by score, and a ranked
leaderboard.

| Signal | Endpoint | Role in the score |
|---|---|---|
| Pending pipeline pressure | `GET /bills/map-summary` | in-flight bills per state (`pending_count`) |
| State lawmaking propensity | `GET /insights/state-gap` | how hard a state over-indexes on circular-economy law vs its peer baseline |
| National tailwind | `GET /bills/stance-momentum` | advances vs. rollbacks over the last 5 years |

### The Forward Score
```
score = climate × ( 0.5·pending-pressure  +  0.3·conversion-room  +  0.2·state-propensity )
```
- **pending-pressure** — a state's in-flight bills relative to the busiest state.
- **conversion-room** — pending relative to what's already enacted (lots queued, little passed = ripe).
- **state-propensity** — the `state-gap` signal: leaders convert pending → enacted faster than laggards.
- **climate** — a national 0.6–1.0 multiplier from momentum; it *dampens* the score in a rollback
  environment but never dominates it (stance is the noisiest classifier axis, so it's kept on a leash).

Live prod snapshot at build time: national tailwind **96%** (1,067 advances vs 47 rollbacks,
2022–2026); top of the curve **NY 85 · MA 84 · HI 70** — MA notable for 145 pending bills against
only 2 enacted (huge conversion room).

## Honesty notes
- This is a **transparent heuristic, not a trained model.** It ranks *relative* likelihood, not a
  calendar date — "most likely next," not "enacts on 2027-03-01."
- `laws-in-force` (the adoption S-curve) would sharpen the propensity term, but it isn't live on
  prod yet, so the score deliberately doesn't depend on it.
- All inputs are the **public/free tier** — no API key required.

## Where Nadia would take it next
- **Material lens.** `stance-momentum` and `map-summary` both filter by material — add a
  packaging/batteries/textiles toggle so the map re-forecasts per product line.
- **Confidence band from history.** Backfill with `laws-in-force` to calibrate the score against
  actual pending→enacted conversion rates, turning the heuristic into a probability.
- **Alert on the curve.** Wire `POST /subscriptions` so a strategy team gets pinged when a state
  crosses into the "Imminent" band — the forward curve as a standing signal, not a one-time look.
