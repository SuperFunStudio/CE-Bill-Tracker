# Ask-the-Atlas latency — why answers get lost, and how to fix it for good

Scoped 2026-08-07 out of a live bug: on the homepage, a question ran its "Thinking…" state and then the
page snapped back to browsing with the question gone — while the same answer showed up in
`/admin/content` and, later, My Library.

## What the evidence says

Prod request logs (`jsonPayload.path="/research/ask"`, service `signalscout-api`):

| when (UTC) | duration | outcome |
|---|---|---|
| 2026-08-07 19:47 | 4.8s / 6.4s / 5.4s | rendered fine |
| 2026-08-06 21:22 | 21.9s | rendered fine |
| 2026-08-06 04:31 | 54.5s | landed |
| 2026-08-06 04:34 | 70.7s | lost |
| 2026-08-06 04:37 | 65.2s | lost |
| 2026-08-06 04:56 | 79.8s | lost |
| 2026-08-08 05:45 | 65.2s | lost |

Every one of them returned **HTTP 200 with a complete, valid body** (a hand-run ask against dev returned
66 KB of well-formed JSON in 52s). CORS is correct on both the preflight and the response. Cloud Run's
request timeout is 300s and the Anthropic client timeout is 180s, so nothing server-side is cutting these
off. The answer is also persisted *before* the response is written (`app/api/research.py`, `_persist_turn`),
which is exactly why the "lost" answers are readable in admin and My Library.

In the 2026-08-08 05:45 case the browser issued its next request (a client-side navigation to `/library`)
**1.2 seconds before the response landed at 65.2s** — i.e. right at the 60-second mark. Failures cluster
above ~60s; everything below it renders. The working hypothesis is a client-side network cap: Safari/iOS
and most corporate proxies abort a fetch at 60s. Confirm with DevTools → Network on a broad question: if
`POST /research/ask` goes red at ~60s while the server logs a 200, that's it.

**This makes latency a correctness problem, not a comfort problem.** Past ~60s the answer is generated,
billed, and stored — and never seen.

## Where the time goes

Not yet instrumented per stage — **step 0 is to measure**, but the shape is clear from the code
(`app/api/research.py`):

- `_rewrite_followup` — one Haiku call, follow-ups only (~1s).
- `_choose_facets` — router + deterministic resolve, partly LLM.
- `_relevant_bills` ×2 + `_passages_for` + `_aggregates` ×2 — Postgres FTS over the corpus.
- `_deep_answer` — **one non-streaming Sonnet call**: up to `_DEEP_READ = 100` full-text bill excerpts in,
  `max_tokens=8000` out. This is the dominant term; both numbers were raised from 50 / 4096 for the
  citation-count win (+28–116%), and the wall-clock cost came with it.

Serial time-to-first-byte is therefore roughly "all retrieval, then a full long-form generation."

## Options

**A. Stream the synthesis (recommended).** Switch `_deep_answer` to `messages.stream` and return
`text/event-stream`; the client reads the body incrementally. Time-to-first-token drops to a few seconds,
and — the point — an open, actively-streaming connection is not what a 60s idle cap kills. Words appearing
also removes the dead-air problem the placeholder copy currently papers over. Costs: the response shape
changes (citations/chart/bills are computed before synthesis and can be sent as a leading event, with the
answer streamed after), `askResearch` in `dashboard-next/src/lib/api.ts` becomes a reader loop, and
`ResearchThread` needs to append into a live turn.

**B. Split into submit + poll.** `POST /research/ask` returns a turn id immediately and does the work in a
background task; the client polls `GET /research/turn/{id}` every ~2s. No long connection at all, so it
survives backgrounded tabs and flaky mobile links — the strongest resilience — and the persisted turn
becomes the single source of truth for both the live view and My Library. Costs: needs a job/`BackgroundTasks`
path on Cloud Run (mind instance-scaling while a request isn't open), a status column, and a polling UI.

**C. Cut the work (stopgap, ship today if needed).** Lower `_DEEP_READ` back toward 50–70, and/or
`max_tokens` toward 4096. Pure config, no plumbing, but it trades away the citation depth that motivated
the raise, and a broad question can still cross 60s. Treat as a bridge, not the fix.

**Recommendation: A now, B if drops persist on mobile.** They compose — a streamed answer that is also
persisted turn-by-turn is the end state. C only buys time.

## Already shipped alongside this (the graceful-failure half)

- `useResearch().active` now includes `error` / `dropped`, so a failed ask no longer unmounts the whole ask
  surface and take its own error message with it. That silent unmount is what made this read as "the page
  resets."
- A network-level failure (a `fetch` rejection with no status) sets `dropped` and shows: *the connection
  dropped before the answer came back — it was still saved, visit your Library* + an "Ask again" retry.
  Fires `atlas_query_dropped` with the latency, so the ~60s cliff is now measurable in GA.
- While an ask is in flight the search bar narrates the work ("Reviewing relevant statutes…", "Comparing
  across the corpus…") instead of holding a frozen "Thinking…".

None of that shortens the wait — it just stops the answer from vanishing while we do.
