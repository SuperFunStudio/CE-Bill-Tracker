# Design Review — Batch 2 & 3 Backlog

Drift audit against the established `theme.css` "Tier A" foundation (Serious / Minimal-ish / Monotone /
Medium-weight). **Batch 1 shipped 2026-06-26** (rev `00097`): modal follow-star (#4), `.badge-material`
+ `.text-error` tokens (#7), `rounded-2xl` → `rounded-panel` (#8). This file tracks the rest.

Findings numbered to match the original review (#1–#9).

---

## Batch 2 — status (2026-06-26)
- [x] **#3 empty/loading** DONE: new `SkeletonList` primitive + `EmptyState` adopted on home table,
      watch list, Federal (actions + litigation), Compliance (deadlines). Built green.
- [~] **#5 PaywallGate** — DECISION: **do NOT consolidate.** The 3 gates (auth/pro, bespoke,
      deadline/referral) are intentionally-distinct funnel variants under active A/B test; merging
      them adds indirection that makes per-variant funnel tweaks harder for ~10 lines of DRY savings.
      Keeping them independent is the right call for a funnel under test (per Kenny's note).
- [ ] **#2 type sizes** — optional polish (fuzzy; most `text-xs` is legit chrome; promoting risks
      layout bloat — do surgically if/when a specific readability complaint surfaces).
- [ ] **#9 badge family** — optional polish (badges already tokenized in Batch 1; componentizing is
      low marginal value).

## Batch 2 — original detail (reference)

### #3 · Unify empty / loading / error states
A good `EmptyState` component exists (`components/ui/EmptyState.tsx`) but is underused; pages roll their
own text/card empties, and loading is skeleton-pulse on most pages but a text placeholder on the watch
list.
- [ ] Adopt `<EmptyState>` for the "no data" case on: `app/federal/page.tsx`, `app/compliance/page.tsx`,
      `app/states/page.tsx`, `app/insights/*` (gap table, roster), and the company obligations empty.
- [ ] Create a shared `<SkeletonList rows=… height=…>` (extract the repeated
      `h-NN bg-bg-secondary rounded-lg animate-pulse` loops) and use it in Federal, Compliance,
      Company, Insights, States.
- [ ] Replace the watch-list loading **text** ("Loading…") in `WatchListSection` with `SkeletonList`.
- [ ] Keep the `.text-error` token (Batch 1) as the single error style — sweep any remaining ad-hoc
      reds (excluding the semantic party chips).

### #5 · One `PaywallGate` component — **3 funnel variants preserved**
**Constraint (confirmed with Kenny):** this is an internal DRY refactor ONLY. The front end MUST keep
three DISTINCT gate experiences with their own copy/CTAs — the funnel is under active A/B testing. Do
not merge the messaging.
- [ ] Create `components/ui/PaywallGate.tsx` with a `variant` prop: `"auth" | "pro" | "bespoke" |
      "referral"` (each renders its current copy, icon, and CTA verbatim).
- [ ] Replace the three duplicated implementations, keeping their exact content:
      - `WatchListSection` `Gate` (auth + pro variants)
      - `company/page.tsx` `ObligationsBetaInquiry` (bespoke variant — RequestAccessModal)
      - `compliance` `UpcomingDeadlinesLock` (referral/deadline variant)
- [ ] Verify each variant still renders identically (snapshot the three before/after) — the funnel
      experiences must be unchanged; only the markup is shared.

### #2 · Promote readable `text-xs` content to `text-body`
The Tier A foundation says body floor = 16px; `text-xs`/`--fs-meta` is for chrome only (counts,
timestamps). Several places use `text-xs`/`text-sm` for primary reading.
- [ ] `BillDetailPanel` — obligation/product list items, summaries → `text-body`.
- [ ] `company/page.tsx` `ObligationCard` — bill title + obligation detail → `text-body`.
- [ ] `federal/page.tsx` cards — action body text → `text-body`.
- [ ] Leave true chrome (pagination "1–5 of N", `'26` session years, timestamps) at `text-meta`.

### #9 · Badge component family
4+ badge treatments for similar data (StatusBadge, inline spans, deadline-type, material). Consolidate
onto the status palette.
- [ ] `components/ui/Badge.tsx` family: `BadgeStatus` (wraps existing `StatusBadge`), `BadgeType`
      (instrument/action/deadline type), `BadgeMaterial` (uses `.badge-material`), `BadgeParty`
      (semantic red/blue — explicitly the one allowed exception).
- [ ] Replace the inline `<span className="bg-bg-primary border …">` badges in Federal + the
      deadline-type badge in Compliance with the family.

---

## Batch 3 — unify the tables (significant; the original "harmonize the tables" ask)

Today the same row renders 6+ ways: `BillTable` (table+mobile cards, opens modal — the canonical one),
Federal (cards, inline-expand), Company (obligation cards + exposure rows + ranking table), Compliance
(urgency-bordered rows), Insights (grid cards), States (linked list). Goal: one visual grammar.

**Approach chosen:** shared CSS primitives (`.list-row` / `.list-card`) over a forced React component,
because the table-`<tr>` vs card-`<div>` duality makes one component awkward, and utilities harmonize
BOTH bill and non-bill lists. Static cards use the existing `.surface-card`; clickable ones use
`.list-card`.

- [x] **Add `.list-row` / `.list-card` utilities** to `globals.css` (canonical clickable row/card look:
      border, radius, bg-secondary, cursor, hover). Shipped Batch-3-step-1.
- [x] **Refactor `BillTable`** (desktop rows → `.list-row`, mobile cards → `.list-card`) — zero visual
      change, proves the utilities match. Shipped.
- [x] **Federal** adopted: clickable litigation card → `.list-card` (selected = `!border-green-accent`),
      static action card → `.surface-card`. Shipped + screenshot-verified.
- [x] **Company** adopted (shipped, rev 00099): clickable "Bill Exposure" rows → `.list-card`
      (selected = `!border-green-accent`); `ObligationCard` → `.surface-card` (dropped its false
      hover-affordance, lifted bg-primary→secondary). ⚠️ admin-gated — eyeball with an admin login.
- [x] **Compliance `DeadlineRow`:** DECIDED to leave as-is — already bg-secondary/border/rounded/
      cursor with an intentional urgency-colored border that `.list-card`'s hover-border would clobber.
      Not drift; documented skip.
- [x] **Insights grids / States momentum lists:** intentionally distinct views (grids, stacked
      momentum bars), NOT row/table drift — out of scope for unification.
- [ ] *(optional polish)* Sweep remaining static containers on Insights/States → `.surface-card`.
- [ ] *(optional)* Standardize "a bill opens the modal" — already true on BillTable/watchlist; Federal
      litigation + Company exposure use select/expand for non-bill detail (acceptable as-is).

**Batch 3 core: DONE.** Bill/card lists across the home table, Federal, and Company now share the
`.list-row`/`.list-card`/`.surface-card` visual language. Remaining items are optional polish.

**Sequencing:** Batch 2 first (it creates `EmptyState`/`SkeletonList`/`PaywallGate`/Badge primitives
that Batch 3's rows reuse), then Batch 3.

---
*Audit source: the UI Design Review skill pass, 2026-06-26. Tokens + foundation live in
`dashboard-next/src/app/theme.css` + `globals.css`.*
