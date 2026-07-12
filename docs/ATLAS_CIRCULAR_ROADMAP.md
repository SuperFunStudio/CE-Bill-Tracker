# Atlas Circular — Platform Roadmap & Next Major Phase

Draft date: 2026-07-11. Status: **planning.** The umbrella roadmap for the rebrand from
"Battle of the Bills / SignalScout" to **Atlas Circular**, and the major update that turns the
product from a bill tracker + Q&A into a **scalable, jurisdiction-aware analysis atlas** over
circular-economy interventions worldwide.

Companion detail: `docs/PUBLIC_AFFAIRS_RESEARCH_DESIGN.md` (the research-surface pillar).
Related memory: [[public-affairs-research-direction]], [[state-profile-pages]], [[eu-integration]],
[[foreign-law-scraper]], [[federated-expansion-au-ca-cn]].

---

## 1. The reframe

**Old model:** a searchable list of bills + an ask box bolted on.
**Atlas Circular:** a navigable **atlas** — circular-economy interventions organized by *place* and
analyzable *at scale*. The corpus is the content; **jurisdiction is the primary axis**; analysis
(ask / filter / compare / brief) is the surface on top.

Why the name matters for architecture: an *atlas* implies (a) a real **jurisdictional hierarchy** you
drill into — World → Region → Country → State/Province → **Municipality** — and (b) that every
jurisdiction node has a coherent, comparable profile of interventions. That hierarchy is the
backbone this phase must lay down, even where we only populate the upper levels now.

**The problem to solve (from live testing, 2026-07-11 — see PUBLIC_AFFAIRS_RESEARCH_DESIGN §2a):**
the current retrieval can't reliably analyze the corpus we already have. "Examples from France"
misses France's own AGEC law because *region isn't a searchable dimension*; broad questions bury
exact matches and the LLM narrates a top-15 slice that contradicts the full table. These are
scalability failures, not patch targets. Atlas needs an analysis engine that is **facet- and
jurisdiction-aware**, not a single brittle text query.

---

## 2. Architecture pillars

| Pillar | What | State today |
|---|---|---|
| **A. Jurisdiction model** | First-class hierarchy (region→country→state→municipality) that every bill/intervention attaches to | Only flat `region` + `state` columns exist |
| **B. Scalable analysis engine** | Facet + text (+ later semantic) retrieval, jurisdiction-aware, NL→facet routing, table-as-truth | Single-tsquery cascade in `_relevant_bills`; fails §2a |
| **C. Unified research surface** | Ask + Explorer + Compare in one place; answer thread; persistence/briefings | Three separate pages; Ask is stateless/admin-gated |
| **D. Municipal drill-down** | Extend the hierarchy to cities + local interventions | Future; builds on Pillar A + [[state-profile-pages]] |
| **E. Rebrand** | Atlas Circular name, IA, homepage-as-atlas | Not started |

---

## 3. Pillar A — Jurisdiction model (the backbone)

Introduce a first-class `jurisdiction` entity as a tree, and attach bills to it. Design for
municipality now even though we populate only region/country/state this phase — a later
migration to add city rows must be additive, not a reshape.

**`jurisdiction`** (nested set or adjacency list + materialized path)
| col | type | note |
|---|---|---|
| id | pk | |
| parent_id | fk null | tree edge |
| level | enum | `world` \| `region` \| `country` \| `state` \| `municipality` |
| code | text | stable slug (`FR`, `US-CA`, `US-CA-SF`) |
| name | text | display ("France", "California", "San Francisco") |
| aliases | text[] | search synonyms ("French", "Golden State") — **fixes the "France" query** |
| path | ltree/text | `world.eu.fr` for fast subtree queries |

- Backfill from existing `region`/`state` (the 27 regions already live — see [[eu-integration]],
  [[federated-expansion-au-ca-cn]]). Bills get a `jurisdiction_id` (keep `region`/`state` as
  denormalized mirrors during transition).
- `aliases` is the direct fix for retrieval: "France"/"French" → jurisdiction FR → its bills.
- Every jurisdiction node gets a **profile** (extends the existing `/states/[abbr]` pages,
  [[state-profile-pages]]) — this is the atlas's navigable unit.

---

## 4. Pillar B — Scalable analysis engine

Replace the single-tsquery cascade with a **hybrid, facet-aware retrieval** pipeline. This is the
heart of "analyze the multitude of bills."

```
question ──► NL→FACET router (Haiku) ──► { facets:{jurisdiction:FR, material:tires,
                                              instrument:…, dimension:…, status:…, year:…},
                                            free_text:"…" }
                         │
                         ▼
   candidate set = SQL facet filters  ∩  text relevance (FTS now; vector rerank later)
                         │
                         ▼
   rank: relevance + boosts (exact title, jurisdiction match, enacted) ; the FULL set is the table
                         │
                         ▼
   narrate: LLM sees a representative sample + the totals-by-facet; MUST NOT assert absence
```

**How this fixes the three §2a requirements:**
1. **Region/jurisdiction-aware** — the NL→facet router turns "France" into a `jurisdiction=FR`
   filter (via `aliases`), so FR bills are *in the candidate set by construction*, not dependent on
   the word appearing in body text. Generalizes to every facet (material, instrument, status, year).
2. **Ranking that respects exact matches** — boosts for title/exact/jurisdiction hits; facet
   filtering removes the OR-broad noise that drowned AGEC at rank 346.
3. **Answer never contradicts the table** — the table is the authoritative faceted set; the LLM is
   handed counts-by-facet and a representative (not just top-15-by-rank) sample, and is instructed to
   describe absence only relative to the set ("none in the top matches" — never "no records exist").

**Sequencing within the engine:** facet + FTS first (deterministic, leans on the compliance data we
already extract, good for citable briefings). **Semantic/vector (pgvector) rerank is a later
enhancement**, not a blocker — add it once the facet layer is solid.

---

## 5. Pillar C — Unified research surface

Per `PUBLIC_AFFAIRS_RESEARCH_DESIGN.md`. Atlas homepage = ask bar on top, Explorer (now
jurisdiction-faceted) below, coupled: an ask scopes the table to its faceted set; filtering
scopes the next ask. Answers accumulate into a persisted **research session** (the one primitive
that unlocks save/share/follow-up). Decisions already locked (2026-07-11): signed-in only, admin/Pro
first; shared briefings anonymous; pricing deferred; snapshot + refresh.

---

## 6. Pillar E — Rebrand to Atlas Circular

- Name/logo, nav, metadata, emails — swap "Battle of the Bills / SignalScout" → Atlas Circular.
- **Domain (decided 2026-07-11):** move to **atlascircular.com** (already owned);
  **battleofbills.com 301-redirects** to it at the A4 cutover — preserves existing links/SEO until the
  product is worth the new name.
- Homepage becomes the **atlas entry point** (ask + faceted Explorer + a jurisdiction map/drill-in),
  not a marketing splash.
- Coordinate with the deferred Tier C UX backlog in [[prod-ux-review-2026-07]] (rename, homepage
  declutter) — this rebrand supersedes those items.

---

## 7. Pillar D — Municipal drill-down (future)

Extend the jurisdiction tree to `municipality`: cities/counties with active local interventions
(bag bans, local EPR, deposit schemes, procurement rules). Builds directly on Pillar A's schema
(city rows are additive) and the profile pages. New ingestion sources per municipality — a research +
adapter effort like the federated expansion ([[federated-expansion-au-ca-cn]]). Explicitly **not**
this phase; the schema just has to not preclude it.

---

## 8. Phasing

| Phase | Scope | Ships | Size |
|---|---|---|---|
| **A0** | Jurisdiction model + backfill from region/state; `research_session`/`turn` tables | invisible backbone | M |
| **A1** | Scalable engine v1: NL→facet router + facet∩FTS retrieval + boosts + answer-scoped-to-table | fixes §2a; better answers | M–L |
| **A2** | Unified Atlas homepage: ask bar ⟺ faceted Explorer coupling; answer thread + follow-ups | the new surface | L |
| **A3** | Briefings: save / "My Research" / anonymous share links (+T&C) | the analysis layer pays off | M |
| **A4** | Rebrand cutover: Atlas Circular name/IA/homepage-as-atlas | public rename | M |
| **A5+** | Semantic/vector rerank; **municipal drill-down**; embeddable briefings | future | L |

**Scope of THIS major update (decided 2026-07-11): A0 + A1 only** — jurisdiction backbone + scalable
engine. A2–A4 (unified surface, briefings, rebrand cutover) are the *next* update, sequenced after
the engine proves out. Rebrand timing (A4) can run parallel to A2/A3 on the frontend, but the
*product* has to be worth the new name first.

---

## 9. Open decisions

1. **Jurisdiction tree representation** — adjacency+path (recommend, simple + `ltree` subtree
   queries) vs nested set (faster reads, painful writes). Recommend adjacency + materialized path.
2. **Transition strategy** — dual-write `region`/`state` + `jurisdiction_id` during migration, or
   hard cutover? Recommend dual-write, drop the old columns after A2.
3. **NL→facet routing cost** — every ask adds a Haiku call. Acceptable? (cheap; recommend yes.)
4. ~~**How much semantic now**~~ — **RESOLVED (2026-07-11): facet + FTS this phase; defer vector.**
5. ~~**Rebrand scope**~~ — **RESOLVED (2026-07-11): atlascircular.com (owned); battleofbills.com
   301-redirects at A4.**
6. **Municipal sourcing** — which jurisdictions first when we get to D (likely large US cities /
   EU capitals with known local EPR)? Parking-lot for now.

---

## 10. Recommended first move

**Phase A0 + A1** — the jurisdiction model + the scalable engine. A0 lays the backbone (and quietly
adds the persistence primitive); A1 makes the corpus actually analyzable and closes the §2a failures.
Everything visible (unified homepage, briefings, rebrand) rides on those two. It also means the very
next thing a user notices is that the tool *stops lying about what's in the corpus* — the credibility
floor for a public-affairs research product.
