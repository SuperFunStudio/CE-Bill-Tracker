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
   **⚠ Revised 2026-07-14 (§10):** with the ask as the homepage, the *free/anon* default flips to
   `public`; private becomes the Pro gate.
3. **Shared-link auth** — unlisted token (recommend) vs truly public/indexable.
4. ~~**Attribution**~~ — **RESOLVED (2026-07-11): always anonymous**, no byline.
5. ~~**Anonymous asks**~~ — **RESOLVED (2026-07-11): signed-in only**; `owner_user_id` NOT NULL.
   **⚠ Reopened 2026-07-14 (§10):** the homepage ask must serve anonymous + free users; `owner_uid`
   goes nullable. This supersedes the 07-11 resolution.
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

---

## 10. Public homepage & the publish tier (added 2026-07-14) — revises §6 / §8

**Since 2026-07-11 the tables shipped** (migration `037_research_sessions.py`; `ResearchSession` +
`ResearchTurn` in `app/models.py`), and `POST /research/ask` now persists every answer via
`_persist_turn` — Phase 0 is done, admin-gated. This section reframes the confidentiality model for a
new decision: **Ask the Bills becomes the main homepage UI, exposed to anonymous + free users**, not
just signed-in dogfooders. That inverts the 07-11 "private-by-default, signed-in-only, public-deferred"
posture for the free tier — and the inversion is the *point*: public-by-default is what builds the
SEO / social-proof corpus for free, while confidentiality becomes a felt Pro benefit.

### 10.1 The tiered visibility model

| Actor | Default visibility | Can keep private? | Rationale |
|---|---|---|---|
| **Anonymous** (no account) | `public` (moderated → indexable) | no | Every ask feeds the public corpus; the on-ramp. `owner_uid` nullable. |
| **Free** (signed in) | `public` | no (upsell) | Same corpus contribution; "keep this private" is the upgrade prompt. |
| **Pro** | `private` (their choice: private / link / public) | **yes** | Confidentiality is the paid benefit; still may opt-in to publish. |

Free/anon **cannot** make a thread private — that's the paywall. Pro **can** publish (opt-in), so the
public corpus isn't only free-tier questions. `visibility` already models `private|link|public`; this
is a per-tier *default + permission*, not a new column.

### 10.2 The keystone: publish the *generalized* question, not the raw one

"Publish the answer without the question" (founder ask) is right in spirit but can't be literal — a
page with no heading is disorienting and, worse, **un-findable** (nothing to rank or browse by). The
practical form:

> Publish the answer under a **de-identified, generalized title synthesized from the question's
> facets**, and make it findable by those facets as tags. The **raw** question (company names, pasted
> text, strategy) never goes public.

Raw *"does my company Acme's HDPE bottle line comply with Maine's new EPR law?"* → public title *"Do
HDPE bottles comply with Maine's EPR law?"*, tagged `jurisdiction:Maine · material:plastics ·
dimension:recycled_content`. This single move satisfies all three founder asks at once — free-tier
confidentiality (raw text withheld), publish-without-the-question (generalized stand-in), and
searchability (facet tags, §10.3). The generalized title is cheap synthesis over data we **already
compute**: `resolve_facets` runs on every ask, and the A1 shadow router already produces structured
intent — reuse either to draft the title.

New field: `public_title` (the generalized stand-in) + `slug` (SEO URL). The raw `question` stays in
`research_turns`, owner-only, never rendered on a public page.

### 10.3 Topic tagging = surfacing facets we already compute

We do **not** need a new NLP tagging system. Every ask already resolves jurisdiction / material /
instrument / product / dimension facets — that *is* the taxonomy, and it's what makes a
question-less public answer findable (you browse it by its tags, not its text).

**Gap to fix first:** `_persist_turn` currently writes only `place_labels` + `reference_labels` into
the `facets` JSONB and **drops materials / instruments / products / dimensions** — the very fields a
tag index needs. Step one is widening what gets persisted (JSONB, **no migration**). Then a GIN index
on the facet JSONB (or a small `research_tag` join table) powers a browsable, filterable public index.

### 10.4 Shareable pages — two flavors, both already modeled

- **Public** (`visibility=public`): in the browsable/indexed corpus. The SEO + social-proof surface.
- **Link** (`share_token`, `noindex`, unlisted): anyone-with-the-link. Works even for a *private* Pro
  answer — the Pro user keeps it out of the public corpus but still hands a colleague a URL.

`share_token` is defined but **never minted yet**. Work is: mint-on-share, public read routes, and
OpenGraph/unfurl meta tags for social sharing — not schema.

### 10.5 Moderation — the new hard requirement

Public-by-default from **anonymous** users means raw free-text could reach an indexable page. Do not
let unmediated anon input hit Google. Publishing the *generalized-title-only* form (§10.2) defuses
most PII/abuse, but a quality/abuse gate is still required before a page is indexable. Add a
`status` state machine — `draft → held → published` — and gate the generalized title itself: an LLM
rewrite could misrepresent scope, so **generate then hold for review (or a confidence threshold)**
until the rewrite is proven. This also protects against the answer-quality liability of a public
compliance claim.

### 10.6 Schema deltas (against the shipped 037 tables)

Smaller than the ambition implies — all additive, one migration + one no-migration change:

| Change | Where | Migration? |
|---|---|---|
| `owner_uid` → **nullable** (anonymous asks) | `research_sessions` | yes |
| `public_title`, `slug`, `category`, `published_at`, `status` (`draft\|held\|published`) | `research_sessions` | yes |
| `publish_consent` (Pro opt-in publish) | `research_sessions` | yes |
| Widen `_persist_turn` to store material / instrument / product / dimension facets | `app/api/research.py` (JSONB) | **no** |
| Partial index `WHERE visibility='public'` + GIN on facet JSONB | indexes | yes |
| Mint `share_token` on share; public read routes + OG tags | `app/api/research.py` | no (routes) |

Everything else the publish flow needs already exists: the self-contained markdown `answer` payload,
the `bill_ids` snapshot for "as of <date>" citability, and the `visibility` state.

### 10.7 Why this is a stepping stone (the founder's strategic frame)

The free public corpus is top-of-funnel: it demonstrates depth, ranks in search, and normalizes
asking compliance questions here. **Privacy is the first paid step**, and it opens the door to the
tailored engagements above it — *company exposure* analysis, portfolio-scoped briefings, monitored
watchlists — where the value is explicitly *your* confidential situation, not the public law. The
publish tier and the confidentiality tier are the same feature seen from opposite ends of the funnel.

### 10.8 Revised phasing addendum

Slots into §7 after the existing Phase 3 (share):

| Phase | Scope | Depends on |
|---|---|---|
| **3.5** | `_persist_turn` facet widening + generalized `public_title`/`slug` generation (held, not yet public) | 0 |
| **3.6** | Moderation `status` + admin review queue; publish the first curated batch (your own admin asks) | 3.5 |
| **3.7** | Public homepage: anon/free asks default `public`, facet-tag browse/search, per-tier default+paywall | 3.6, §10.1 |
| **3.8** | Pro confidentiality toggle + opt-in publish + `share_token` minting + OG unfurl | 3.7 |

Gating still deferred per §7, but §10.1 forces the free/Pro line for this product *at* Phase 3.7 —
that's where pricing (see [[tier-restructure]]) finally gets decided.

### 10.9 New open questions

11. **Anon rate-limiting / cost** — public homepage + anonymous Sonnet asks is an open cost/abuse
    surface (amplifies §8.6). Per-IP quota? Cheaper model for anon? Cache-and-serve popular asks?
12. **Generalized-title fidelity** — how do we validate the rewrite doesn't misstate scope before it's
    indexable? (Ties to §10.5 hold state.)
13. **De-dup** — many users will ask near-identical questions; publish one canonical page per
    facet-cluster and increment a counter, or many near-duplicates? (Canonical is better for SEO.)
14. **Consent UX for free tier** — the "your answer will be public" disclosure at the input box; wording
    + ToS (extends §6).
