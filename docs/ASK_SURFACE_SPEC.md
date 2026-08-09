# Ask the Atlas gets a real home — routing spec

Scoped 2026-08-08. Supersedes the "fold `/ask` into the unified Explore surface" call from the homepage
work: we tried direct integration, learned from it, and are going back with the toggle kept and the
answer given an address.

## What we're keeping from the last round

- **The AI Analysis toggle stays on the homepage.** Reader agency over which mode the bar is in was the
  right call; nothing here changes it.
- **Keyword filtering stays on the homepage**, exactly as now — typing filters the table live.
- The Ask button still no-ops with the toggle off.

## What changes

The homepage stops *hosting* the answer and starts *routing* to it. Pressing Ask (toggle on, ≥3 chars)
hands off to `/ask`, which becomes the true home for questions: the thread, follow-ups, the walls, the
relevant-bills table, and a "← Back to the Atlas" return to browse. One place where AI usage happens, and
it has a URL.

### Why this is a bug fix, not a re-skin

The thread currently lives only in React state on `/`. Anything that unmounts that tree — a nav click, a
reload, iOS discarding a backgrounded tab, the ~60s network cap documented in
[ASK_LATENCY_PLAN.md](ASK_LATENCY_PLAN.md) — destroys the answer. That's what forced the `dropped` state
and then the recovery poll. **An addressable thread is recoverable by construction**: refresh, Back,
share, and reopen all become the same code path, and the recovery poll degrades from a load-bearing
mechanism to a safety net.

## URL states

| URL | Meaning |
|---|---|
| `/ask` | The empty ask surface — bar, examples, no thread. Indexable landing page. |
| `/ask?q=<question>` | Phase 1 handoff: the page owns the request for this question. |
| `/ask?session=<id>` | **Canonical.** An owned thread; follow-ups append to it. |
| `/?session=<id>` | Legacy (My Library, older links) → redirect to `/ask?session=<id>`. |

The `/ask` → `/` redirect in [app/ask/page.tsx](../dashboard-next/src/app/ask/page.tsx) inverts: `/` keeps a
tiny redirect for `?session=` so nothing already in the wild 404s or dead-ends.

## Phasing

**Phase 1 — frontend only. Ships the UX, no API change.**

1. `/ask` becomes the real page: hosts `useResearch()` + `ResearchThread` + `ResearchWall` (both already
   extracted and portable — this is a move, not a rewrite), plus the ask bar in permanent ask-mode (no
   toggle here; that's the clarity win) and "← Back to the Atlas".
2. Home's `submitQuery` becomes `router.push('/ask?q=' + encodeURIComponent(q))`. Everything gated on
   `research.active` in [page.tsx](../dashboard-next/src/app/page.tsx) — the collapsing grid, the hidden
   globe, the swapped table — **deletes**. The homepage gets materially simpler.
3. `/ask` reads `?q=` on mount and fires the ask once (guard against StrictMode double-fire and against
   re-asking on a Back into the page).
4. Link updates: [AskHistorySection.tsx:71](../dashboard-next/src/components/research/AskHistorySection.tsx#L71)
   `/?session=` → `/ask?session=`; add `'/ask': 'Ask the Atlas'` to `ROUTE_TITLES` in
   [lib/analytics.ts](../dashboard-next/src/lib/analytics.ts); `newThread()` strips `?session=` from `/ask`
   rather than `/`.
5. Known interim gap: a **refresh mid-flight re-asks** (the id doesn't exist yet), costing one duplicate
   Sonnet call. Phase 2 removes it. Don't paper over it with a localStorage cache — that's a third source
   of truth for the same thread.

**Phase 2 — backend. This is where the drop dies.**

`POST /research/ask` returns `{session_id, turn_id}` **immediately** and completes the work in the
background; the client swaps the URL to `/ask?session=<id>` at once and polls `GET /research/turn/{id}`
(or streams into it) until the answer is written. No long-lived connection means no 60s cap to hit, and a
refresh, a dropped link, or a killed tab all just re-read the URL. Needs: a status column on
`research_turns` (`pending|done|failed`), a background-task path that survives Cloud Run's
scale-to-zero (a min-instance or a job), and the poll endpoint. Retrieval already runs before synthesis,
so the bills table and citations can be written at the same time as the id if we want them to paint early.

## The transition

The search bar is the shared element: on submit it flies from its place on the homepage to the top of
`/ask`, the question already in it, while the globe and table fade out beneath. View Transitions API where
supported, a CSS fade/slide fallback where not. ≤350ms, and honor `prefers-reduced-motion` with a plain
cut — the point is "I'll take you over here," which reads as intent at 300ms and as latency at 800ms.

## Explicit non-goals

- Not touching the toggle, keyword filtering, or the browse surface.
- Not moving shared threads (`/r/<token>`) or staged articles (`/p/`) — they stay read-only and separate.
- Not making thread state a client-side cache. The server's persisted turn is the single source of truth;
  the URL is the pointer to it.

## Risks

- **Reverses a recent decision.** The unified surface was deliberate; if the transition feels like a page
  load, this trades a good instinct for a worse one. Mitigation: the shared-element move above, and the
  fact that Phase 2 makes the destination genuinely more capable (refresh-safe, shareable) rather than
  merely elsewhere.
- **An extra hop before the answer.** Push happens instantly (static export, client nav) and the request
  fires on the destination, so time-to-answer is unchanged — but this must be measured, not assumed.
- **Phase 1 duplicate asks** on refresh, as above. Real Anthropic spend, bounded by how often people
  refresh a 60s wait — which, per the drop logs, is more often than we'd like. Phase 2 shouldn't lag far
  behind Phase 1.
