# ⚑ Whip Count — the EPR champion board

**Rank the legislators who actually move Extended Producer Responsibility law.** Pick a
material + instrument → get a war-room whip sheet of the lawmakers carrying that fight,
each scored into who to **thank**, who to **back**, and who to **watch** — grounded in
enacted-vs-introduced track records via the
[SignalScout API](https://signalscout-api-36712717703.us-central1.run.app/docs).

> Hackathon entry from the **"Marcus Reyes" persona** — *The Whip* (business × design × dev).
> Former state-house legislative director, now runs advocacy strategy. His whole thesis in one line:
>
> *"Every other entry on this board serves the company that has to **comply**, or the market
> that **prices** it. Nobody built for the room upstream of all of them — the advocates
> deciding whether the law should exist at all, and who to call about it. Regulation isn't
> text. It's people. Show me the people."*

Same dataset as the rest of the board. Aimed at a **new buyer**: trade associations, PROs,
and NGO campaigners who build this targeting list by hand in spreadsheets today.

## Why it's a different demo

- **Different audience.** Every other entry (Compliance Cliff, Comply by Friday, Spec-Sheet
  Guard, Exposure Terminal, the MCP server) serves the *regulated* producer or the *investor*
  watching them. This serves the people who **make or kill the law** — the only entry whose
  buyer wants a *targeting list*, not a to-do list.
- **The most detailed feed nobody touched.** `/insights/champions` carries per-legislator
  sponsorship counts, enacted totals, and instrument/material specialties — the richest data
  in the API, and no other entry reads it.
- **A read the raw API doesn't return.** SignalScout gives you *counts*. Whip Count turns them
  into an **advocacy play** — CLOSER / WORKHORSE / RISER — the thing an advocate actually needs.
- **Grounded, not vibes.** Every number is a live public endpoint. The bucket + influence
  formula is printed on the page. Top plastic-packaging EPR closer: **Brian Kavanagh** (NY).
  Top workhorse: **Nicole Lowen** (HI) — 27 CE bills carried, 1 enacted. *Wants it, can't
  finish alone.* That's the highest-leverage meeting on the board.

## The read

| Bucket | Rule | Advocacy play |
|---|---|---|
| **CLOSER** | 2+ CE laws enacted | Thank + protect — your reliable carrier |
| **WORKHORSE** | 6+ bills, &lt;2 landed | Back + coach — high volume, low conversion; needs coalition/testimony |
| **RISER** | emerging / cross-aisle | First meeting — get on the radar early |

`influence = enacted×6 + primary×1 + cosponsor×0.4` — landing law counts for far more than
filing it, because an advocate's scarcest ally is someone who can actually finish.

## Run it

```bash
cd hackathon/whip-count
node server.mjs           # Node 18+ — zero npm dependencies
# open http://localhost:4930
```

Config (optional):
- `SIGNALSCOUT_API` — point at a local/staging API instead of prod.
- `SIGNALSCOUT_API_TOKEN` — a Pro seat's Firebase token (not required; all feeds are free-tier).
- `PORT` — defaults to `4930`.

## How it works

`server.mjs` is a ~150-line zero-dependency **composition engine** (Node built-in `http` +
global `fetch`). It caches the champions roster, then — per filter request — scores every
legislator into an advocacy bucket the raw API never returns, ranks by influence, and derives
the facet lists so the UI never offers a dead option. It also proxies the API server-side, so
the browser never touches CORS. `public/index.html` is the entire front end (no build step): a
whip-sheet of legislator cards with a party color rail, a success meter, and a lazy-loaded
bill-by-bill track record.

| UI action | Proxy route | SignalScout endpoint |
|---|---|---|
| build / filter the board | `/api/board?instrument=&material=&party=&state=&minBills=` | `GET /insights/champions` |
| expand one legislator's receipts | `/api/champion/bills?id=` | `GET /insights/champions/{id}/bills` |

## Where Marcus would take it next

- **Session Forecast overlay.** Cross the champion roster with `/insights/state-cycles` →
  *"Texas has no EPR law, but Rep. X just filed her 3rd CE bill and the session opens in Jan —
  brief her now."* Turns a targeting list into a *who-to-call-and-when* calendar.
- **The Receipts board** (`/bills/outcomes`) — arm every advocate with what enacted EPR laws
  actually delivered (Maine's bottle bill redirected $16M/yr away from beverage companies).
  The pro-regulation mirror image of Exposure Terminal's short book.
