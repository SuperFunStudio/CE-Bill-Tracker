# Pre-post traffic baseline — 2026-08-12

Captured immediately before a planned promotional post, so the spike can be measured against a
record rather than a memory. Everything here is reproducible:

```
venv/Scripts/python scripts/ga4_report.py --report raw \
  --dimensions sessionDefaultChannelGroup,sessionSource \
  --metrics sessions,totalUsers,engagedSessions,userEngagementDuration --days 28
venv/Scripts/python scripts/ga4_journeys.py --report funnel --days 7
```

**Read the acquisition table with a caveat**: the `Unassigned` rows below
(`region_instrument_matrix`, `pricing`, `pricing_developers`, `home_walkthrough`) are *not* real
sources. They are UI labels that were being sent as GA4's reserved `source` event parameter, which
overwrites session attribution. Fixed 2026-08-12 (commit dc6c598), but the historical rows can't be
reprocessed — roughly 130 of those sessions are really Direct or LinkedIn. Post-fix data won't have
this class of row at all, which is itself a way to confirm the fix landed.

## Audience (7 days)

| cohort | users | sessions | engaged sessions | engagement (s) |
|---|---|---|---|---|
| new | 77 | 77 | 25 | 1,339 |
| returning | 16 | 76 | 55 | 6,793 |
| (not set) | 13 | 17 | 0 | 0 |

16 returning users generate as many sessions as 77 new ones, at 5x the engagement. That ratio is the
thing to watch after the post: a spike that moves only the "new" row is reach, not audience.

## Acquisition, 28 days

| channel | source | sessions | users | engaged | engagement (s) |
|---|---|---|---|---|---|
| Direct | (direct) | 533 | 321 | 250 | 36,382 |
| Organic Social | linkedin.com | 89 | 68 | 34 | 3,149 |
| Referral | atlascircular.substack.com | 25 | 4 | 19 | 3,479 |
| Organic Search | google | 22 | 16 | 13 | 2,079 |
| Organic Social | reddit.com | 12 | 12 | 3 | 40 |
| Referral | teams.public.onecdn.static.microsoft | 8 | 4 | 2 | 50 |
| AI Assistant | claude.ai | 3 | 1 | 1 | 219 |

Engaged-session rate is the column that matters, not volume:

- **Substack 76%** (19/25) — best-converting channel by a wide margin
- **LinkedIn 38%** (34/89) — 3.5x the volume at half the quality
- **Reddit 25%** (3/12), 40 seconds of engagement across twelve people — effectively noise

## Intent events, 7 days

| event | count | users |
|---|---|---|
| page_view | 199 | 25 |
| deadlines_lock_shown | 8 | 7 |
| bill_open | 7 | 3 |
| atlas_query_submitted | 6 | 2 |
| atlas_query_dropped | 4 | 1 |
| subscribe | 1 | 1 |

## Product state

| | |
|---|---|
| email subscribers (active) | 17 (of 23 rows) |
| accounts | 11 |
| paying, non-comp | 1 |
| access requests, pending | 9 |
| anon_scope rows | 0 (shipped 2026-08-12; a post is its first real traffic) |
| watchlist items | 14 |
| research sessions | 153 (150 of them the founder's) |

## Known measurement caveats at capture time

1. **Bots inflate the top line.** ~100 of 404 28-day "new users" show cloud-region or blank geo, one
   session, no return, zero engagement. `scripts/ga4_journeys.py --report bots` quantifies it;
   GA4's own reports do not, so every GA4 number above is bot-inclusive.
2. **`page_view` under-counted before 2026-08-12.** A race between RouteAnalytics and the gtag script
   dropped the first page_view of most sessions (419 session_start users vs 104 page_view users).
   Fixed in dc6c598, so `page_view` counts before and after this date are not comparable.
3. **Link-preview traffic counts as human.** 45 `Safari (in-app)` users over 28 days are largely
   Slack/Teams/LinkedIn unfurls. The classifier deliberately does not flag them, and a post will
   generate more.

## What to compare after

Run the same commands plus `scripts/ga4_journeys.py --report funnel` both with and without
`--include-bots`. The questions worth answering:

- Did **returning** users grow, or only new? (reach vs audience)
- Did the engaged-session rate hold at the channel's baseline, or dilute?
- Did anything reach `subscribe` / `scope_sync_cta` / `atlas_query_submitted`, or did the spike land
  and leave?
- How many `anon_scope` rows appeared — the first read on what anonymous visitors actually want.
