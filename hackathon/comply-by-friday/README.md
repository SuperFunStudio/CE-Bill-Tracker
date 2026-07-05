# Comply by Friday

**Hackathon build — persona: Priya Okafor, "The Translator" (business × design × dev).**

> *"Don't show me the bill. Tell me what to do about it — in date order, by when."*

SignalScout's API is rich on **data** (what laws exist, their deadlines, which PRO runs
each program) but thin on **decisions**. This turns three raw feeds into the one-pager a
compliance lead would actually forward to their boss: a dated, urgency-sorted checklist of
*do-this-next* actions — join this PRO, register with this agency, file this plan, by this date.

## What it does

Pick the states you operate in (+ optional material filter) → get an action plan:

- **Actions required** vs **monitor-only**, so you see obligations at a glance.
- **Sorted by deadline**, bucketed into *within 30 days / within 90 days / on the horizon / no fixed date*.
- Each item carries the **PRO or agency name + registration link**, a **fee flag**, the source bill, and materials.
- **Print / save-as-PDF** for the compliance binder.

## How it's built

Zero dependencies — just Node ≥18.

- `server.mjs` — the **composition engine** (the real product). Fans out to
  `/compliance/pathways?state=…` per state, pulls the shared `/bills/deadlines/upcoming`
  feed, merges + enriches + urgency-sorts, and serves the result as `/api/plan`.
  It also proxies the API server-side, sidestepping the CORS allowlist.
- `public/index.html` — a dependency-free renderer (Priya's design lens: a to-do list, not a dashboard).

Data flow:

```
/compliance/pathways?state=CA   ─┐
/compliance/pathways?state=OR   ─┼─► buildPlan() ─► dated, sorted action plan ─► UI
/bills/deadlines/upcoming        ─┘   (merge + enrich + bucket by urgency)
```

## Run it

```bash
cd hackathon/comply-by-friday
npm start
# → http://localhost:4310
```

Point at a different API with `SIGNALSCOUT_API=…` / change port with `PORT=…`.
Defaults to the live prod API.

## Honest limitations (hackathon scope)

- Rich deadline *descriptions* come from the free-tier `/bills/deadlines/upcoming` teaser
  (5 soonest). A Pro/API key would return every dated milestone — the engine already keys
  on `bill_id`, so it lights up automatically with more rows.
- `monitor` laws carry a placeholder deadline; we deliberately show them as "no fixed date
  yet" rather than inventing urgency.
- Fee amounts aren't summed — we flag *whether* a law has a fee; dollar figures live behind
  the company-impact endpoints (a natural next step: blend `/companies/{id}/obligations`
  to turn "has fee" into "$X/yr").

## Where it goes next

- **Company mode**: swap the state picker for a company → use `/companies/{id}/obligations`
  for exposure ∩ footprint + financial stakes.
- **`.ics` export / webhook**: same plan, delivered to the user's real calendar or Slack
  (Priya's board idea #2).
