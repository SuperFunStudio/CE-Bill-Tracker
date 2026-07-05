# Spec-Sheet Guard — EPR compliance as a CI check

> **Hackathon submission.** Compliance, shifted left. Describe your packaging in a
> `packaging.yaml`, and this fails your build the moment a product/market combination
> picks up an **unmet Extended Producer Responsibility obligation** — the PRO you haven't
> joined, the state you haven't registered with, the deadline you're about to miss.

The MCP server on the board *answers questions* ("am I compliant?"). Spec-Sheet Guard
*blocks mistakes* — it lives in the pull request, next to the code and the packaging spec,
and turns "someone should check the regs" into a red X that stops the merge.

## The idea

A packaging designer changes `packaging.yaml` — adds an aluminum cap, or a new market:

```yaml
product: "500ml Sparkling Water — PET bottle, aluminum cap, paperboard multipack"
markets: [CA, OR, CO, ME]
materials: [plastic_packaging, paper_packaging, metals]
acknowledged:
  - Circular Action Alliance   # the PRO you've already joined
```

On the PR, the check runs and posts:

```
✗ ERROR  CA  SB-54 — Solid waste: reporting, packaging, and plastic food service ware.
    action: join_pro — Join Circular Action Alliance and report your packaging.
    register with: Circular Action Alliance
    deadline: 2027-01-01 — in 183d
    → https://circularactionalliance.org/

✗ ERROR  CO  HB22-1355 — Producer Responsibility Program for Statewide Recycling
    action: join_pro — Join Circular Action Alliance and report your packaging.
    deadline: 2026-06-30 — OVERDUE by 2d
    → https://circularactionalliance.org/

Summary: 13 error, 0 warning, 22 note
FAIL — 13 unmet obligation(s). Register, or add to `acknowledged` once handled.
```

You either **register for real** or **acknowledge** the obligation once handled — and the
build goes green. New law lands next quarter? The check goes red again on its own.

## How it works

For every `market` in the spec it calls `GET /compliance/pathways` on the public
[SignalScout API](https://signalscout-api-36712717703.us-central1.run.app/docs), keeps the
enacted laws whose materials overlap your product, and classifies each:

| Result | Meaning | Blocks build? |
|--------|---------|---------------|
| **error** | Actionable obligation (`join_pro` / `register_with_state` / `file_individual_plan`) that isn't acknowledged | ✅ yes (exit 1) |
| **warning** | Obligation whose materials aren't pinned yet, or a deadline beyond `--fail-window` | no |
| **note** | `monitor` / informational, or already acknowledged | no |

No API key needed — it uses the public/free tier. Multi-region: US state codes plus the
`EU`, `FR`, and `JP` families all work as `markets`.

## Quick start

```bash
npm install
npm run build

npm run check           # runs against packaging.example.yaml (will FAIL — that's the point)
npm test                # unit tests for the evaluation rules (no network)
```

### The spec file (`packaging.yaml`)

| Field | Required | Purpose |
|-------|----------|---------|
| `product` | no | Label for the report |
| `markets` | **yes** | Jurisdictions sold into: US state codes, or `EU` / `FR` / `JP` |
| `materials` | **yes** | SignalScout material categories (see the live vocab at `GET /bills/instrument-material-matrix`). Loose match: `packaging` matches `plastic_packaging`/`paper_packaging` |
| `acknowledged` | no | Obligations already handled. Matches an entity name/slug, a bill number, or a market-scoped `CA:SB-54`. Matching ignores case, spacing, and punctuation (`Circular Action Alliance` == `circular-action-alliance`) |

### CLI

```
spec-sheet-guard [--spec packaging.yaml] [--warn-only] [--json] [--github] [--fail-window <days>]
```

| Flag | Effect |
|------|--------|
| `--spec <path>` | Spec file (default: `packaging.yaml` / `.yml` / `.json`) |
| `--warn-only` | Report everything but always exit 0 (soft rollout) |
| `--fail-window <days>` | Only fail on obligations due within N days; the rest become warnings |
| `--json` | Machine-readable report (for custom CI annotations) |
| `--github` | Emit `::error::`/`::warning::` workflow commands (auto-on under `GITHUB_ACTIONS`) |

Exit codes: `0` pass · `1` unmet obligation · `2` bad spec / API error.

### In CI

See [`.github/workflows/epr-guard.yml`](.github/workflows/epr-guard.yml). One step:

```yaml
- run: npx spec-sheet-guard --spec packaging.yaml --github
```

Findings show up as inline annotations on the PR, and a red obligation blocks the merge.

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `SIGNALSCOUT_API_BASE_URL` | prod Cloud Run URL | Point at a local/staging API |
| `SIGNALSCOUT_API_TOKEN` | _(none)_ | Firebase bearer token, only if you gate a deployment |

## Design notes

- **The `acknowledged` list is the state machine.** A green build means "every obligation
  is either handled or explicitly triaged" — and it re-opens automatically when the law
  changes, because the pathways come live from SignalScout, not a snapshot.
- The evaluation core ([`src/guard.ts`](src/guard.ts)) is pure and network-free, so the
  rules are unit-tested ([`src/guard.test.ts`](src/guard.test.ts)) without hitting the API.
- Sibling project [`../compliance-copilot-mcp`](../compliance-copilot-mcp) exposes the same
  data conversationally; this one enforces it. Same API, two surfaces.

MIT licensed. Built for the SignalScout hackathon.
