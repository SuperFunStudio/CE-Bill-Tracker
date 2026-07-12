# Public-Affairs Research Surface — Design Doc

Draft date: 2026-07-11. Status: **design, unbuilt.** Author-facing planning doc for folding Bill
Explorer + Ask the Bills + Bill Comparison into one research surface, adding follow-up questions,
saved/shareable briefings, and a persistence layer that turns queries into a lasting analysis layer
over the corpus.

Related: [[public-affairs-research-direction]] (memory), `docs/V2_FULLTEXT_SEARCH_PLAN.md`,
`docs/SECURITY_ASSESSMENT.md`. Current backend: `app/api/research.py` (`_relevant_bills` cascade +
stateless `POST /research/ask` + `GET /research/bills`).

---

## 1. Why — the second persona

We are building a **second product line** on the same corpus. Not a feature bolt-on.

| | Compliance officer (existing) | Public-affairs analyst (new) |
|---|---|---|
| Job | Manage *my* obligations | Produce *shareable analysis* |
| Core verb | Track / comply | Ask / brief / share |
| Output | Deadlines, plans, portfolios | Briefings ("tires across all bills"), citable memos |
| Who | In-house EPR / packaging leads | Lobbyists, policy analysts, advocacy orgs, journalists |
| Success | Nothing missed | A defensible, shareable answer |

This reframes several decisions: sharing/briefings become first-class, **snapshotting matters for
citability**, and the sensitive data to protect is primarily the **user's own questions and pasted
text** (which reveal intent/strategy), not the corpus (public law).

---

## 2. The one primitive everything reduces to

Save, share, persist, and follow-up are not four features — they are four uses of one missing object:
a **persisted research session**. Today `POST /research/ask` is fully stateless and ephemeral;
nothing is stored. Build the session object once and all four unlock. This is the trunk; everything
else is a branch, and the phasing (§7) is ordered around building it first.

---

## 2a. Evidence: point-patches are exhausted (verified 2026-07-11 on prod)

After the metadata-match fix shipped, live testing showed AGEC (France's anti-waste law) *still*
missing from answers, for two distinct, verified reasons. These are requirements the redesign must
own, not more patches:

| Live query | What happens | Root cause |
|---|---|---|
| "examples from France to compare to the US?" | AGEC at global **rank 23**, not in the LLM's top-15 → "no French legislation" | **Region/country isn't searchable.** AGEC's title has no "France" token (`'france' in title+summary = False`); only `region=FR` knows it's French, and region isn't in the match surface. |
| "records about the france anti waste law? AGEC?" | `text_broad`, total 1999, AGEC at **rank 346**; LLM sample is all WV bills → "dominated by West Virginia bills" | **OR-broad ranking dilutes title matches** (verbose WV Right-to-Repair bills repeat "law/waste/record") **+ the LLM only sees the top-15**, so the answer contradicts the full set. |

**Three systemic requirements this forces:**
1. **Region/jurisdiction-aware retrieval** — map country/place names → `region` (the Explorer already
   filters on region; in the unified surface the ask inherits the active region filter, §3.1).
2. **Ranking that doesn't drown exact/title matches** under OR-broad noise (boost title/exact hits;
   OR-broad is a blunt last resort).
3. **Close the answer-vs-table gap** — today the LLM narrates only the top-15 while the table holds
   the true set, so it can claim "no records" about a bill sitting at rank 23. In the redesign the
   **table is the primary artifact** and the narrative is explicitly scoped to it; the answer must
   never assert absence of something present in the set.

## 3. UI architecture

### 3.1 The research surface (redesigned homepage)

Two stacked zones, coupled:

```
┌───────────────────────────────────────────────────────────┐
│  ASK BAR   "Ask about circular-economy legislation…"   [→] │  ← natural-language analysis
│            Regions ▾   (confidential ● Private)            │
├───────────────────────────────────────────────────────────┤
│  BILL EXPLORER                                             │
│  filters: state ▾ material ▾ instrument ▾ status ▾ …       │  ← structured browse/filter
│  ┌─────────────────────────────────────────────────────┐  │
│  │ BillTable — all bills, paginated                    │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

**The coupling is the whole point of unifying.** An ask does two things: (a) opens the answer thread
(§3.2), and (b) **scopes the Explorer below to the answer's relevant-bill set** — so the table is the
evidence behind the answer, and the user can then keep filtering it with structured controls.
Conversely, the user can filter first and **ask within the filtered set**. Ask (LLM) and filter
(structured) become two lenses on one bill set.

This directly resolves the "question vs filter" duality raised for follow-ups: some inputs are LLM
questions ("which bills eco-modulate fees?"), some are filter ops ("just the enacted ones",
"drop the EU rows"). The surface supports both because both operate on the same active set.

### 3.2 Answer thread → compendium

- An ask opens an **answer panel/modal**: the cited narrative + chart + the (now-scoped) bill table.
- **Follow-ups** accumulate into a thread (chat history) within one session.
- The saved thread is the **compendium** — browsable under "My Research", re-openable, shareable.
- A session has a title (auto-suggested from the first question, editable).

### 3.3 Confidentiality signaling (called out explicitly — see §6 for the full model)

- A **persistent visibility badge** on the ask bar and every session: `● Private` / `◐ Link` /
  `○ Public`. Always visible so a user is never unsure who can see a thread.
- **Private by default.** Sharing is an explicit action with a confirmation that shows *exactly what
  becomes visible* (including their own questions).
- An inline notice near the input: "Don't paste confidential or client-privileged information."

---

## 4. Data model

New tables (Alembic migration, additive):

**`research_session`**
| col | type | note |
|---|---|---|
| id | uuid PK | |
| owner_user_id | fk NOT NULL | asks require a signed-in account (decided 2026-07-11) |
| title | text | auto from first Q, editable |
| visibility | enum | `private` \| `link` \| `public` (default `private`) |
| share_token | text unique null | minted on first share; used by `/research/shared/{token}` |
| created_at / updated_at | timestamptz | |

**`research_turn`** (one row per question in a session)
| col | type | note |
|---|---|---|
| id | uuid PK | |
| session_id | fk | |
| seq | int | order within session |
| question | text | the raw user question |
| rewritten_query | text | contextual-rewrite output used for retrieval (§5) |
| strategy | text | `text` \| `dimension:<k>` \| `text_broad` (from the cascade) |
| answer | jsonb | the ResearchAnswer payload (narrative, citations, chart, coverage) |
| bill_ids | int[] | **snapshot** of the ranked relevant set at ask time (citability) |
| bill_total | int | total in the set |
| created_at | timestamptz | |

**Snapshot vs live — recommendation: store both, default to snapshot.** Persist `bill_ids` (frozen,
citable — a briefing shows what it showed) *and* `rewritten_query`+`strategy` (so a "Refresh against
today's corpus" button can re-run). Public-affairs briefings need a stable, citable artifact with an
"as of <date>" label; the refresh affordance keeps it from going stale silently.

---

## 5. Backend changes

- **`POST /research/ask`** — accepts optional `session_id` (+ implicitly the prior turns). On no
  session_id, creates one. Appends a `research_turn`. Returns the turn + session_id. Persistence is
  otherwise invisible to the current single-turn UX.
- **Contextual query-rewrite (the one genuinely new bit)** — before `_relevant_bills`, a cheap Haiku
  call condenses `{prior turns + new question}` into a standalone retrieval query, so *"what about
  just California?"* retrieves *"tires in California"*. ~30 lines + one model call. First turn skips
  it. Everything downstream (`_relevant_bills`, `GET /research/bills`) is unchanged because the
  cascade is already stateless + deterministic.
- **Session endpoints** — `GET /research/sessions` (list mine), `GET /research/sessions/{id}` (full
  thread; owner-only), `PATCH /research/sessions/{id}` (rename, set visibility),
  `POST /research/sessions/{id}/share` (mint token), `DELETE /research/sessions/{id}`.
- **Public read** — `GET /research/shared/{token}` (no auth) returns the snapshotted thread only;
  `noindex`. Paging within a shared briefing reads the stored `bill_ids`, not a live re-query.
- `GET /research/bills` stays for live paging of an owner's active ask.

---

## 6. Confidentiality & legal (the risk the founder flagged)

**Threat:** accidental leakage of private information via sharing. The sensitive payload is mostly
**user-authored** — the questions themselves reveal who's researching what (a lobbyist's query =
their client's interest), and any pasted text (note: `Evaluate a Bill` already takes pasted statute
text — same exposure surface). Corpus data is public law and low-risk.

**Model & mitigations:**
- **Private by default.** No session is ever visible to anyone but its owner until an explicit share.
- **Three visibility levels:** `private` (owner only) → `link` (anyone with the unguessable token,
  `noindex`, not listed) → `public` (discoverable; probably gated to a later phase / never for v1).
- **Share confirmation** spells out what becomes visible — *including the questions*, not just the
  answer — and asks the user to confirm. Optionally let them redact/rename before sharing.
- **Always-on visibility badge** (§3.3) so state is never ambiguous.
- **Input notice** discouraging confidential/privileged content.
- **T&C clause**: user is responsible for content they enter; sharing publishes it; we don't index
  private/link sessions. Legal to confirm wording.
- **Attribution — always anonymous (decided 2026-07-11).** A shared briefing never carries the
  creator's identity. Protects the questioner's intent; no byline even opt-in for v1.
- **Deletion**: owner can delete a session (hard delete + invalidate any share token).

---

## 7. Phasing

| Phase | Scope | Depends on | Rough size |
|---|---|---|---|
| **0** | `research_session` + `research_turn` tables; `/ask` persists (invisible plumbing) | — | S |
| **1** | Follow-ups: query-rewrite + thread UI + answer panel | 0 | S–M (~1 day BE) |
| **2** | Save + "My Research" list (the compendium) | 0 | M |
| **3** | Share: visibility model + confidentiality UX + T&C + `/shared/{token}` | 2, §6 decisions | M |
| **4** | Unified homepage: ask bar ⟺ Explorer coupling (ask scopes the table; filter-then-ask) | 1 | L (IA/frontend) |
| **5** | Public/embeddable briefings, PDF/CSV export, "refresh against today's corpus" | 3 | M |

Gating note (decided 2026-07-11): asks are **signed-in only**; Phases 0–2 stay **admin/Pro dogfood**
behind the current admin gate. **Pricing is deliberately deferred** — build and dogfood first, make
the tier/add-on call once the feature set is real (does not block Phases 0–2). Phase 3+ (public
links) is where the free/Pro/pricing question for the public-affairs line eventually gets forced
(see [[tier-restructure]]).

---

## 8. Open questions (decide before the phase that needs them)

1. **Snapshot vs live** — recommend snapshot + refresh (§4). Confirm.
2. **Visibility default & levels** — recommend private default, add `link` in Phase 3, defer `public`.
3. **Shared-link auth** — unlisted token (recommend) vs truly public/indexable.
4. ~~**Attribution**~~ — **RESOLVED (2026-07-11): always anonymous**, no byline.
5. ~~**Anonymous asks**~~ — **RESOLVED (2026-07-11): signed-in only**; `owner_user_id` NOT NULL.
6. **Cost control** — every ask + every follow-up is a Sonnet call; persistence/sharing amplify usage.
   Rate limits? Per-tier quotas?
7. **Retention/deletion** — user-initiated delete (yes); any auto-expiry of link sessions?
8. **Corpus drift labeling** — "as of <date>" on every snapshot; how prominent?
9. ~~**Pricing**~~ — **DEFERRED (2026-07-11)**: stay admin-gated; decide tier/add-on later.
10. **Question-vs-filter routing** — in the unified surface, how do we detect when an input should
    drive structured filters vs an LLM answer? (Phase 4's core UX problem.)

---

## 9. What we would build first

Phase 0 + 1: the `research_session`/`research_turn` tables and follow-up questions. Low-risk,
mostly plumbing on top of the retrieval layer already shipped, and it makes the product *feel* like a
research tool immediately. Everything else (save UI, sharing, unified homepage) rides on that trunk,
and the §8 decisions can be made just-in-time per phase.
