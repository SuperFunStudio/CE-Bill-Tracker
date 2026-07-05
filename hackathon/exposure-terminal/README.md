# ▚ Exposure Terminal — the EPR short book

**Rank producers by unpriced Extended Producer Responsibility liability.** Pick an enacted
law → get a trading-desk-style short book of the companies most exposed to it, each priced by
its *portfolio-wide* statutory penalty and annual-fee ceiling — grounded in enacted statutes
via the [SignalScout API](https://signalscout-api-36712717703.us-central1.run.app/docs).

> Hackathon entry from the **"Jordan Wu" persona** — *"The Short Book"* (business × dev × design).
> Ex-sell-side ESG analyst. Her whole thesis in one line:
>
> *"Everyone on this board is building for the company that has to **comply**. Nobody's building
> for the people who get to **price the fact that it hasn't** — investors, insurers, procurement,
> M&A diligence. An unmet EPR obligation isn't a chore. It's an unbooked liability on someone's
> balance sheet, and I can see it before the market does."*

Same dataset as the rest of the board. Run **backwards**: not *"what do I owe?"* but
*"who owes, how much, and how late?"*

## Why it's a different demo

- **Different audience.** Every other entry (Compliance Cliff, Comply by Friday, Spec-Sheet
  Guard, the MCP server) serves the *regulated* producer. This serves the people *watching*
  them — the only entry with a buyer who pays for the **answer**, not the to-do list.
- **The number an analyst would put in a model.** The SB-54 book leads with Procter & Gamble
  at a **~$101M/yr fee ceiling** across 20 laws, PepsiCo right behind at ~$96M across 22 —
  ~$282M/yr of stacked exposure across the top names, six of them **grounded in published fee
  schedules**, all with a hard 2027-01-01 deadline.
- **Grounded, not vibes.** Numbers come straight from `GET /companies/{id}/obligations` —
  statutory penalties and published fee ranges with a `grounded` flag, not an LLM guess.

## Run it

```bash
cd hackathon/exposure-terminal
node server.mjs            # Node 18+ — zero npm dependencies
# open http://localhost:4320
```

Click a marquee-law chip (CA SB-54, MN, MD, WA) or search all 165 enacted EPR laws.

Config (optional):
- `SIGNALSCOUT_API` — point at a local API instead of prod.
- `PORT` — defaults to `4320`.

## How it works

`server.mjs` is a ~180-line zero-dependency **composition engine** (Node built-in `http` +
global `fetch`). SignalScout ships two facts that were never joined:

1. **Who is exposed to a law**, ranked — `GET /companies/exposure-ranking?bill_id=`
2. **What one company owes** — penalty/day, annual-fee range, nearest deadline —
   `GET /companies/{id}/obligations`

Neither is a leaderboard of *dollar liability*. The engine fans #2 across #1 and sorts the
result into a book.

| UI action | Proxy route | SignalScout endpoints |
|---|---|---|
| load the picker | `/api/bills` | `GET /bills?status=enacted&instrument_type=epr` |
| build the book | `/api/book?bill_id=` | `GET /companies/exposure-ranking` → fan out `GET /companies/{id}/obligations` + `GET /bills/{id}` for the header |

Data flow:

```
/companies/exposure-ranking?bill_id=865  ─►  top N producers, ranked
        │  (fan out, ~300ms each)
        ▼
/companies/{id}/obligations  ─►  penalty/day · annual-fee range · #laws · nearest deadline
        │
        ▼
   merge + sort by fee ceiling  ─►  THE SHORT BOOK  ─►  terminal UI
```

Priced names sort first by fee ceiling; names with no fee data fall back to SignalScout's
composite exposure score, so a zero-obligation name like Tesla-on-SB-54 correctly sinks to the
bottom instead of faking a rank.

## Honesty (the part a real analyst insists on)

The headline is an **exposure ceiling, not a booked loss**:

- **Annual fee exposure** is a producer's portfolio-wide fee *range* across every enacted law
  it touches — grounded where a published schedule exists (the `grounded` tag), a benchmark
  estimate otherwise.
- **Max penalty / day** is the single largest statutory civil penalty in that portfolio — the
  ceiling if in continuous default. It is shown in its own column and **never added into** the
  fee number.

That's how a short thesis is framed, and the UI says so on every book. Jordan wouldn't ship it
any other way.

## Where it goes next

- **Landfall** (Jordan's follow-up): flip from enacted to *predicted* — score which
  jurisdictions move next from `/insights/state-gap` × `/bills/stance-momentum` ×
  `/insights/state-cycles` × `/insights/champions`. Forward exposure, not just current.
- **Diligence memo**: one target company → its full obligation stack + `/bills/{id}/litigation-cases`
  as the EPR section of an M&A / underwriting memo (the LLM-generated `exposure-brief` is
  admin-gated — the premium unlock).
