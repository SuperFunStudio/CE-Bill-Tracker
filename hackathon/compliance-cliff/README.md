# 🪨 Compliance Cliff

**The shareable EPR risk card.** Type a company → get a screenshot-worthy card of its
Extended Producer Responsibility exposure: the laws, the states, the nearest deadline,
the statutory penalty-per-day, and the annual-fee range — all grounded in enacted
statutes via the [SignalScout API](https://signalscout-api-36712717703.us-central1.run.app/docs).

> Hackathon entry from the **"Maya" persona** (design-technologist: design × business × dev).
> The MCP server on the board answers *"am I compliant?"*. This makes a stranger **ask** the
> question — then hands them a card they'll post to LinkedIn. Every share is a lead.

![Amazon example](https://signalscout-api-36712717703.us-central1.run.app) <!-- run it to see the real thing -->

## Why it's a good demo
- **One screen, no login, ~15 seconds.** Search → card. That's the whole product.
- **The artifact is the ad.** The card is designed to be downloaded and shared.
- **Grounded, not vibes.** Numbers come from `GET /companies/{id}/obligations` — statutory
  penalties and published fee schedules with citations, not an LLM guess.

## Run it
```bash
cd hackathon/compliance-cliff
node server.js            # Node 18+ — zero npm dependencies
# open http://localhost:8787
```
Then click a shortcut chip (Amazon, Apple, PepsiCo…) or search 400+ tracked producers.

Config (optional):
- `SIGNALSCOUT_API_BASE_URL` — point at a local API instead of prod.
- `PORT` — defaults to `8787`.

## How it works
`server.js` is a ~120-line zero-dependency proxy (Node built-in `http` + global `fetch`)
that fronts two **public** SignalScout endpoints and kills CORS:

| UI action | Proxy route | SignalScout endpoint |
|---|---|---|
| type-ahead search | `/api/search?q=` | `GET /companies?search=` |
| build the card | `/api/obligations?id=` | `GET /companies/{id}/obligations` |

`public/index.html` is the entire front end (no build step). It computes a **Cliff Score
(0–100)** — a blend of breadth (laws × states), deadline urgency, statutory penalty size,
and annual-fee magnitude — maps it to a verdict (*Solid ground → Sheer drop*), and renders
the card. **Download card (PNG)** exports at 2× via `html-to-image` (loaded from a CDN);
**Copy share link** yields a deep link (`#c=<company-uuid>`) that reopens the exact card.

## Honesty notes
- Penalties shown are the **statutory maximum** per-day figure; fees are **volume-apportioned
  estimates** from published schedules (the API flags `any_fee_grounded`).
- "Affected" is the high-confidence half of exposure: the company has a material in the
  bill's categories **and** an operational presence in that state. No proxy volumes are
  used to decide *whether* a company is affected.

## Where Maya would take it next
- Real server-side **OG image** endpoint (`/card/:id.png`) so links unfurl in Slack/LinkedIn
  with the card baked in — turning every paste into an impression.
- A **"claim your cliff"** CTA on the card → the SignalScout no-card trial (the conversion loop).
- **Industry leaderboards** ("steepest cliffs in consumer packaged goods") as recurring content.
