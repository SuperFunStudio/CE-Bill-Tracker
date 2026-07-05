# ◨ Under Appeal — the EPR challenge board

**Is your compliance spend standing on solid ground?** Pick a producer → get a litigation
posture review of its Extended Producer Responsibility obligations: which are **settled**,
which are **under active constitutional challenge**, which are **enjoined** (enforcement paused
by a court), and which have no suit of their own but stand on a legal theory **already winning
next door** — all joined live to enacted statutes via the
[SignalScout API](https://signalscout-api-36712717703.us-central1.run.app/docs).

> Hackathon entry from the **"Dana Okonkwo" persona** — *The Docket* (business 45 · dev 30 · design 25).
> Ex-EPR-**defense** litigator; she was in the room when industry sued to block Oregon's and
> California's packaging laws. Her whole thesis in one line:
>
> *"Every other entry on this board treats an enacted law as a rock you build on. I spent
> years trying to blow those rocks up — and sometimes we won. The most expensive compliance
> mistake isn't missing a deadline. It's spending $2M to comply with a statute that gets
> **enjoined** three months before it takes effect. The board tracks laws being **born**.
> Nobody tracks them being **tested**. Show me which of my obligations is one court ruling
> away from vanishing."*

Same dataset as the rest of the board. Run through a **different lens**: not *"what do I owe?"*
but *"is what I owe still going to be law when the deadline hits?"*

## Why it's a different demo

- **A new tense.** Comply-by-Friday says *do this by Friday*; Exposure Terminal *prices the
  liability*; Swap Studio *moves the intervention upstream to material choice*. All of them
  assume the law is settled. This is the only entry that asks whether it **is** — the
  contrarian read that tells you when **not** to spend.
- **It just came true.** In **Feb 2026** a federal court granted a preliminary injunction
  pausing **Oregon's** EPR law on Dormant Commerce Clause grounds (*NAW v. Feldon*) — the first
  time a US court halted an EPR statute. In **June 2026**, 17 state AGs + NAW sued to block
  **California's SB-54** (*Nebraska v. Heller*). Dana's demo ships with the actual dockets.
- **A read the raw API can't return.** SignalScout gives you obligations and, separately,
  cases. It doesn't tell you that an **untested** Maryland obligation stands on the *same*
  legal theory that just **won** in Oregon. Under Appeal computes that: the **EXPOSED · by
  precedent** verdict. That's the analyst read an in-house GC actually forwards up the chain.

## What it does

Pick a producer (chips open on the packaging majors; search covers 400+):

- **Verdict banner** — obligations contested / enjoined, states now in court, portfolio fee
  exposure, and the soonest deadline attached to a *challenged* law.
- **Per-obligation cards**, sorted hottest-first, each with a **preemption-risk gauge** and its
  litigation dossier: case name, court, judge, plaintiff type, challenge theory, a docket-event
  timeline, and cited sources.
- **Direction, not just risk.** A suit by *environmental* groups to make SB-54's rules
  **stricter** (*NRDC v. CalRecycle*) isn't a threat to your obligation — it's a signal your
  **fees may rise**. Under Appeal flags that separately instead of scoring it as danger.
- **Print / save as a risk memo** for the compliance binder.

## How it's built

Zero dependencies — just Node ≥18 (for global `fetch`).

- `server.mjs` — the **composition engine** (the real product). For a company it pulls
  `/companies/{id}/obligations`, then fans `/bills/{id}/litigation-cases` across every
  obligation, scores each Settled → Under-Challenge → Enjoined, and layers the precedent read.
  Proxies the API server-side, sidestepping the CORS allowlist.
- `litigation-seed.mjs` — **grounded, cited** litigation data (see below).
- `public/index.html` — a dependency-free renderer (Dana's design lens: a legal risk memo, not
  a dashboard).

## Grounded, not vibes — and honest about the one gap

The SignalScout litigation feed is **fully built** — `litigation_cases` model, the
CourtListener webhook, LLM `preemption_risk` scoring — but prod hasn't **ingested** cases yet
(`/bills/{id}/litigation-cases` returns `[]` today). Rather than invent dockets, this entry
carries **real, publicly-reported** EPR challenges in `litigation-seed.mjs`, each with cited
law-firm/trade-press sources, shaped to the exact `LitigationCaseSummary` schema the API
returns. The server **prefers live rows** and overlays the seed only when the live feed is
empty for a bill — every seed row is labelled `seed` in the UI.

The moment someone runs the repo's own `scripts/seed_courtlistener.py` against prod, the live
rows win and the overlay goes dark on its own — **zero UI change**. The seed isn't a mock; it's
the backfill, pre-loaded.

Cases included (all real, 2025–2026):
| Case | Law | Status |
|------|-----|--------|
| *NAW v. Feldon* (D. Or.) | OR SB-582 (RMA) | **Preliminary injunction granted** |
| *Nebraska et al. v. Heller* (E.D. Cal.) | CA SB-54 | Active — 17 AGs + NAW |
| *NRDC / CAW / Oceana v. CalRecycle* | CA SB-54 regs | Active — wants stricter rules |
| *ILMA v. CDPHE* (Denver Dist.) | CO recycling program | Active — PRO-structure fight |

## Run it

```bash
cd hackathon/under-appeal
node server.mjs           # Node 18+ — zero npm dependencies
# open http://localhost:4740
```

Config (optional):
- `SIGNALSCOUT_API` — point at a local/staging API instead of prod.
- `PORT` — defaults to `4740`.

## The satellites (same feed, different buyer)

- **Docket Pulse** — alerts on *litigation events*, not law changes: "MTD denied in the SB-54
  challenge" the day CourtListener fires the webhook. Insurers and the Exposure Terminal's
  investors both want this feed.
- **Preemption Map** — the Forward Curve's US map recolored by *legal fragility* instead of
  legislative momentum: green = enacted & unchallenged, amber = under challenge, red = precedent
  exists to strike it.
