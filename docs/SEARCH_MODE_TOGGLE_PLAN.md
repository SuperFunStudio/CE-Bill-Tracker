# Search-mode toggle: Keyword ⇄ Deep Search

## Goal

Give users explicit agency over search mode via a toggle in the search-bar area, default **OFF**:
- **OFF (default)** — classic keyword bill search → the `BillTable` (today's behavior, unchanged).
- **ON ("Deep Search" / analysis)** — unlocks asking questions (Ask-the-Atlas), and the results
  table STAYS visible instead of vanishing.

## Current state (grounded)

- One unified page: `dashboard-next/src/app/page.tsx` (`/`). `/ask` just redirects here.
- One "adaptive" search box (`page.tsx:342-352`) that on every keystroke sets BOTH `query` (ask) and
  `billFilters.search` (keyword filter). Intent (keyword vs question) is inferred implicitly — there
  is no explicit mode today.
- **The table-disappearing bug** is one ternary at `page.tsx:390`:
  `{research.active ? <ResearchThread/> : <> map + <BillTable .../> (line 470) </>}`. `research.active`
  (`ResearchThread.tsx:160` = `turns.length>0 || busy || restoring || wall!==null`) flips true the
  moment a question is asked, so the keyword `BillTable` unmounts. The research view renders its OWN
  server-ranked "Relevant bills" table per turn (`ResearchThread.tsx:555-568`) — a different table.
- Gating: `hasCapability(CAP.ASK)` (Student/Research/Pro; admins bypass). Anon gets ONE free ask
  (`atlas_free_ask_used`), then `ResearchWall` (`ResearchThread.tsx:95-96, 453`). `useCapabilityGate`
  exists if we ever gate the toggle itself.
- Persisted-preference template to mirror: `src/components/settings/BetaContext.tsx` — hydration-safe
  localStorage boolean context.

## Design

**Mode state.** Add a `deepSearch` boolean (default false), persisted to localStorage exactly like
`BetaContext` (server render false, read stored value in a mount effect → no hydration mismatch).
Replaces the implicit adaptive behavior with an explicit switch.

**OFF (keyword mode).** Input placeholder "Search bills…"; Enter/typing only filters (`billFilters.search`
→ `BillTable`). Asking is disabled — pressing Enter never triggers `research.ask`. This is the literal
"fall back to original keyword search." Map + Export-CSV + `BillTable` render as today.

**ON (deep search mode).** Placeholder "Ask a question about the corpus…"; submit → `research.ask(q)`.
The answer renders AND a bills table stays visible (the bug fix — see decision 1). Existing gate/wall
flow is unchanged: anon 1 free ask → wall; under-tier → upgrade wall. The toggle is free to flip (it
is the upsell surface — flipping ON and seeing the capability IS the teaser, consistent with the
preview-lock funnel).

**The bug fix.** Restructure the `page.tsx:390` ternary so it keys off `deepSearch`, not
`research.active`, and so a bills table is always present in deep-search mode (per decision 1). In
keyword mode `research.active` can't become true (asking is disabled), so the table can never vanish.

## Decisions (LOCKED 2026-08-04)

1. **Deep Search mode shows the answer + its ranked "Relevant bills" table** (the per-turn
   server-ranked table, made persistent/prominent). Keyword mode shows the classic browse table.
2. **Toggle = a labeled on/off switch reading "AI Analysis"**, living on the SAME ROW as the Ask
   button:
   - Mobile: switch sits to the LEFT of the Ask button on that row.
   - Desktop: same row; the **Ask button only appears/enables once "AI Analysis" is ON** (OFF = pure
     keyword filter, no Ask affordance at all).
3. **Persist across visits** via localStorage (mirror `BetaContext`).
4. **Layout tidy (part of this change):** move the hint line ("Type keywords to filter the bills
   instantly · ask a full question for a grounded, cited answer over the same corpus") to ABOVE the
   search bar. Freeing that space lets the filters row (Regions / States / More filters) move up to
   sit in line — at least on desktop.

### Resulting bar layout
```
[ hint: Type keywords to filter … · ask a full question for a grounded, cited answer ]
⌕  [ search / ask input …………………………… ]   AI Analysis ⚬on/off   [ Ask ]   ← one row
Regions ▾   States ▾   More filters ▾                                    ← aligned up
```
- OFF: input = keyword filter → `BillTable`; no Ask button; `research.active` can never fire → table
  never disappears.
- ON: input placeholder → "Ask a question…"; Ask button appears; submit → answer + ranked bills table.
  Existing gate/wall (anon 1 free ask → wall; under-tier → upgrade) unchanged.

## Scope / risk

Frontend-only; no API or DB change. Touches `page.tsx` (the ternary + the search form + a new
context/state) and a small toggle component. The adaptive auto-detect behavior is removed in favor of
the explicit toggle — the one behavior change to call out. Analytics: add a `search_mode_toggled`
event (mirror the existing `track()` taxonomy).
