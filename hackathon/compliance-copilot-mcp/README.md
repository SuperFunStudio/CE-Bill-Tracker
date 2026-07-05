# Compliance Copilot — MCP server for the SignalScout API

> **Hackathon submission + reference implementation.** Turns the SignalScout EPR /
> circular-economy dataset into LLM-callable tools, so any MCP client (Claude Desktop,
> Claude Code, Cursor, …) can answer **"what are my Extended Producer Responsibility
> obligations?"** for a given product and set of jurisdictions — and subscribe to alerts
> when the law changes.

## The idea

A brand ships a `500ml PET bottle with an HDPE cap` into California, Oregon, and the EU.
Are they compliant? Today that's hours of legal research. With Compliance Copilot it's one
sentence to an LLM:

> *"I sell packaged beverages in CA, OR, and the EU. What are my EPR obligations and deadlines?"*

The model calls `check_compliance`, and gets back the exact producer responsibility
organization (PRO) to join, the registration link, the next deadline, and whether fees apply —
stitched together from five SignalScout endpoints.

## Tools

| Tool | What it does | Endpoints used |
|------|--------------|----------------|
| `check_compliance` | **Flagship.** materials + jurisdictions → actionable obligations (PRO to join, registration URL, next deadline, fee flag) + deadline pressure | `/compliance/pathways`, `/bills/deadlines/summary` |
| `find_laws` | Search/filter the bill dataset by material, instrument, jurisdiction, status | `/bills` |
| `upcoming_deadlines` | The compliance calendar, scoped to materials/states | `/bills/deadlines/upcoming`, `/bills/deadlines/summary` |
| `coverage_matrix` | Where regulation is dense (instrument × material) | `/bills/instrument-material-matrix` |
| `watch_material` | Subscribe to email alerts when matching laws change | `POST /subscriptions` |

All read endpoints are the **public/free tier** — no API key required. Set
`SIGNALSCOUT_API_TOKEN` to a Pro seat's Firebase token to unlock the full deadline calendar in
`upcoming_deadlines`.

## Quick start

```bash
npm install
npm run build

# Verify it talks to the live API end-to-end:
node dist/smoke.js
```

### Add to Claude Desktop / Claude Code

`claude_desktop_config.json` (or your MCP client's config):

```jsonc
{
  "mcpServers": {
    "compliance-copilot": {
      "command": "node",
      "args": ["<abs-path>/hackathon/compliance-copilot-mcp/dist/index.js"],
      "env": {
        // optional overrides — defaults to prod, no auth:
        // "SIGNALSCOUT_API_BASE_URL": "https://signalscout-api-36712717703.us-central1.run.app",
        // "SIGNALSCOUT_API_TOKEN": "<firebase-id-token-for-a-pro-seat>"
      }
    }
  }
}
```

Then ask: *"Check my EPR compliance for packaging and paper in Colorado."*

### Inspect the tools interactively

```bash
npm run inspect   # opens the MCP Inspector against the built server
```

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `SIGNALSCOUT_API_BASE_URL` | prod Cloud Run URL | Point at a local/staging API |
| `SIGNALSCOUT_API_TOKEN` | _(none)_ | Firebase bearer token; a Pro seat unlocks the full deadline calendar |

## Demo script (for judging)

1. *"I make packaged food sold in Colorado and Oregon. What EPR obligations do I have?"* → `check_compliance` (states: CO, OR)
2. *"What battery EPR laws are already enacted?"* → `find_laws`
3. *"When are my next packaging deadlines?"* → `upcoming_deadlines`
4. *"Alert me at me@brand.com when any new packaging law lands."* → `watch_material`

## Current data coverage

The public API today serves a **fully-populated US dataset** (1,500+ bills, per-state compliance
pathways, PROs, deadlines). The schema and these tools are **multi-region-ready** (EU / France /
Japan and `region`/`regions` params), but that data + region filtering activate when the
multi-region API build is promoted to prod. **For the strongest demo, use US state queries** —
that's where the enacted-law → PRO → deadline chain is fully wired.

## Notes for other hackathon builders

- The full API is documented at `<API_BASE>/docs` (FastAPI OpenAPI) — generate a typed client
  from `<API_BASE>/openapi.json` for free.
- Multi-region: US states + EU + France + Japan share one dataset (`region` / `regions` params).
- The material and instrument taxonomies are open vocabularies — call `coverage_matrix` to see
  the live set of values before hard-coding filters.

MIT licensed. Built for the SignalScout hackathon.
