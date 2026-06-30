"""Find documented real-world outcomes of enacted laws — the bill_outcome candidate finder.

Sparked by TX HB3487: a niche oyster-shell sales-tax deduction that turned out to have produced 45
acres of restored reef. Most enacted laws never produce a *measured, citable* effect; a few do, and
those are the soul of the Insights "Real-World Impact" spotlight. This script hunts for them at scale
so they don't have to be stumbled on by hand.

For each enacted, in-scope law in a bounded slice, it asks Claude (with the web_search + web_fetch
server tools, plus a NewsAPI recent-movement signal) to find ONE documented outcome — a number with a
live source — then runs a second adversarial pass that re-fetches the cited page and confirms the
figure is actually there. Survivors are written to bill_outcome as reviewed=FALSE, where they show up
ONLY in the /admin review console (never the public page) until a human approves them. This mirrors the
existing reviewed=true discipline: a wrong impact stat is worse than no stat, so a human is always the
last gate (see scripts/seed_bill_outcomes.py for the hand-curated originals this learns its bar from).

FRED is deliberately downgraded to optional context (--fred): it's macro time-series and can't pin a
number to one law, so anything leaning on it is framed as "associated", never the headline metric.

Usage:
  venv/Scripts/python scripts/propose_bill_outcomes.py --dry-run            # list the slice, no API
  venv/Scripts/python scripts/propose_bill_outcomes.py --limit 6 --preview  # research, print, no write
  venv/Scripts/python scripts/propose_bill_outcomes.py --state TX --limit 8 # research + insert reviewed=false
  venv/Scripts/python scripts/propose_bill_outcomes.py --rank --limit 10    # Haiku pre-rank the slice first
  venv/Scripts/python scripts/propose_bill_outcomes.py --prod-dsn "..." --limit 12
"""
import argparse
import json
import re
import sys
import time

import anthropic
import httpx
from sqlalchemy import create_engine, text

from app.config import settings
from app.links.health import classify
from app.research.evidence import fred_search, search_news

MODEL = "claude-opus-4-8"          # house default; --model claude-sonnet-4-6 for a cheaper sweep
RANK_MODEL = "claude-haiku-4-5-20251001"  # the cheap pre-ranker

# A live link in any of these buckets is acceptable as a citation; "dead" is dropped. "blocked" is a
# correct-but-WAF'd page (e.g. a .gov behind a bot wall) — keep it (matches the link auditor's stance).
ACCEPTABLE_BUCKETS = {"alive", "redirected", "blocked"}

VALID_DIRECTIONS = {"positive", "negative", "mixed"}
VALID_ATTRIBUTION = {"direct", "program", "associated"}

# Two gold examples from the hand-vetted set, so Claude learns the bar: a MEASURED figure, a primary
# source, and an honest attribution knob (the oyster law's acreage predates the deduction, so it's
# "program", not "direct"). Kept short on purpose.
FEWSHOT = """Two examples of the bar (these are already in our curated set — do NOT return them):

EXAMPLE A — TX HB3487, oyster-shell recycling sales-tax deduction:
  direction=positive, metric_value=45, metric_unit="acres", metric_label="of oyster reef restored",
  attribution="program"  (the reef acreage comes from the Sink Your Shucks program the deduction now
  subsidizes — the law scales existing activity rather than producing the number itself),
  source="Harte Research Institute".

EXAMPLE B — CA SB270, single-use bag ban:
  direction=NEGATIVE, metric_display="157k -> 231k tons (+47%)", attribution="direct"  (a 'reusable'
  film-bag loophole raised plastic-bag tonnage by weight — the clearest cautionary case in the set).
  A documented BAD or MIXED outcome is just as valuable as a good one; report what's true."""

RESULT_SCHEMA_HINT = """Return ONLY a JSON object (no prose, no code fence), exactly this shape:
{
  "found": true | false,
  "direction": "positive" | "negative" | "mixed" | null,
  "metric_label": "<short noun phrase completing the figure, e.g. 'of oyster reef restored'>",
  "metric_value": <number or null>,
  "metric_unit": "<unit string, e.g. 'acres', '%', 'million gallons', or null>",
  "metric_display": "<override string for figures that don't compose as value+unit, e.g. '157k -> 231k tons (+47%)', else null>",
  "summary": "<2-4 sentences: what the law did and what it has been documented to PRODUCE, with the number>",
  "attribution": "direct" | "program" | "associated",
  "as_of_date": "<YYYY-MM-DD the figure is as of, or null>",
  "source_name": "<the publisher/agency, e.g. 'CalRecycle'>",
  "source_url": "<the single best primary URL where the figure appears>",
  "law_title": "<plain-language name of the law>",
  "instrument_type": "<one of: epr, deposit_return, recycled_content, right_to_repair, incentives, labeling, preemption, other>",
  "material_categories": ["<lowercase material tags, e.g. 'packaging','electronics','organics'>"],
  "slug_hint": "<1-3 kebab words naming the outcome, e.g. 'oyster-reef'>",
  "confidence": <0.0-1.0>,
  "remediation_note": "<ONLY if direction is negative/mixed AND a later law fixed it: one sentence naming the fixing law and year, else null>",
  "remediation_bill_number": "<the fixing law's bill number if known, e.g. 'SB1053', else null>"
}

Rules:
- found=true ONLY if you can cite a SPECIFIC, MEASURED outcome (a quantity, rate, or dollar figure) at
  a real URL you actually consulted. A vague "improved recycling" with no number is found=false.
- The source_url must be the page where the number literally appears — prefer a .gov / agency / program
  report or a reputable outlet citing one. NOT a generic homepage.
- attribution is the honesty knob: "direct" = the statute itself produced the number; "program" = the
  law funds/incentivizes a program that produced it (number may predate or exceed the law);
  "associated" = correlated, looser (anything resting on macro/FRED context is at most "associated").
- A negative or mixed outcome is a valid, valuable find. Do not bias toward positive.
- REMEDIATION: if the outcome is negative or a shortfall, check whether a later amendment or follow-on
  law has since fixed it, and if so name that law and year IN THE SUMMARY (e.g. "...California closed
  the loophole with a 2024 follow-on law"). This negative-then-remedied arc is high-value.
- If after searching there is no measured, citable outcome for THIS law yet, return found=false."""


def collect_one_bill(engine, state, bill_number):
    """Fetch a single bill by (state, bill_number) IGNORING the 'no existing outcome' exclusion —
    for verification/backtests (e.g. re-deriving the oyster finding to sanity-check the engine).
    Pairs with --preview so it never overwrites the vetted row it's checking against."""
    sql = text("""
        select b.id, b.state, b.bill_number, b.title, b.description,
               b.instrument_type, b.material_categories, b.last_action_date
        from bills b
        where upper(b.state) = upper(:state) and b.bill_number = :bn
        limit 1
    """)
    with engine.connect() as c:
        return list(c.execute(sql, {"state": state, "bn": bill_number}))


def collect_targets(engine, state, material, instrument, since_year, limit, max_per_bill=1):
    """Enacted, in-scope laws with FEWER than max_per_bill outcomes recorded, newest-acted first,
    bounded. max_per_bill=1 (default) keeps the original "no outcome yet" behaviour; raise it to let
    a single law accumulate several distinct documented impacts (the research pass is told what's
    already on file so it hunts a DIFFERENT one each time)."""
    sql = text("""
        select b.id, b.state, b.bill_number, b.title, b.description,
               b.instrument_type, b.material_categories, b.last_action_date,
               coalesce(oc.cnt, 0) as outcome_count
        from bills b
        left join (select bill_id, count(*) cnt from bill_outcome group by bill_id) oc
               on oc.bill_id = b.id
        where b.ce_relevant
          and b.status = 'enacted'
          and b.state <> 'US'
          and coalesce(oc.cnt, 0) < :max_per_bill
          and (:state is null or b.state = :state)
          and (:instrument is null or b.instrument_type = :instrument)
          and (:material is null or b.material_categories ? :material)
          and (:since_year is null or extract(year from b.last_action_date) >= :since_year)
        order by b.last_action_date desc nulls last, b.state, b.bill_number
        limit :limit
    """)
    with engine.connect() as c:
        return list(c.execute(sql, {
            "state": state, "material": material, "instrument": instrument,
            "since_year": since_year, "limit": limit, "max_per_bill": max_per_bill,
        }))


def existing_outcomes(engine, bill_id):
    """The outcomes already recorded for a bill — fed to the research prompt so a multi-outcome run
    finds a DISTINCT additional impact rather than re-proposing one we have."""
    if not bill_id:
        return []
    sql = text("""
        select direction, metric_label, metric_value, metric_unit, metric_display, summary
        from bill_outcome where bill_id = :bid order by id
    """)
    with engine.connect() as c:
        rows = c.execute(sql, {"bid": bill_id}).all()
    out = []
    for r in rows:
        fig = r.metric_display or (
            f"{r.metric_value} {r.metric_unit or ''}".strip() if r.metric_value is not None else "")
        out.append(f"[{r.direction}] {fig} {r.metric_label or ''}".strip())
    return out


# ---- optional Haiku pre-ranker: which laws are even worth a (pricier) web-search pass? ----

RANK_SCHEMA = """Return ONLY a JSON object: {"score": <0.0-1.0>, "why": "<6 words>"}.
score = how likely THIS enacted law has produced a SPECIFIC, MEASURABLE, citable real-world outcome
(tons recycled, acres restored, a redemption rate, dollars raised, jobs). Reward concrete, unusual,
program-creating mechanisms (like an oyster-shell recycling incentive). Penalize purely procedural,
study-only, definitional, or preemption laws that produce no measurable thing."""


def rank_one(client, t):
    prompt = (f"{RANK_SCHEMA}\n\nState: {t.state}\nBill: {t.bill_number}\nTitle: {t.title}\n"
              f"Summary: {(t.description or '')[:600]}")
    try:
        resp = client.messages.create(
            model=RANK_MODEL, max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        obj = _extract_json("".join(b.text for b in resp.content if b.type == "text"))
        return float(obj.get("score") or 0.0), (obj.get("why") or "")[:60]
    except (anthropic.APIError, ValueError, TypeError):
        return 0.5, "(rank failed)"


# ---- the research pass ----

def build_prompt(t, news_lines, fred_lines, already=None):
    mats = ", ".join(t.material_categories or []) or "unspecified"
    blocks = [
        "You are researching the DOCUMENTED real-world outcome of an enacted U.S. circular-economy / "
        "extended-producer-responsibility law — what it has been measured to PRODUCE in the world, not "
        "what it requires. Weigh GOOD and BAD outcomes equally: a law that backfired, hit an unintended "
        "consequence, underperformed its target, or had to be amended is among the most valuable finds.\n",
        FEWSHOT, "",
        f"LAW UNDER RESEARCH:\nState: {t.state}\nBill: {t.bill_number}\nTitle: {t.title}\n"
        f"Summary: {(t.description or '')[:800]}\nInstrument: {t.instrument_type or '?'}\n"
        f"Material(s): {mats}\n",
    ]
    if already:
        blocks.append(
            "ALREADY ON FILE for this law (find a DISTINCT, ADDITIONAL outcome — a different metric or "
            "a different effect; do NOT re-report these, and return found=false if there is no "
            "materially different documented outcome):\n" + "\n".join(f"  - {a}" for a in already) + "\n")
    if news_lines:
        blocks.append("RECENT NEWS SIGNAL (NewsAPI, possibly noisy — verify before citing; these are "
                      "leads, not proof):\n" + "\n".join(news_lines) + "\n")
    if fred_lines:
        blocks.append("MACRO CONTEXT (FRED — context only, can't be attributed to one law; if you use "
                      "it, attribution must be 'associated'):\n" + "\n".join(fred_lines) + "\n")
    blocks.append("Search the web for the program/agency reports, statute evaluations, or reputable "
                  "coverage that quantify this law's effect. Find the single best documented figure.\n")
    blocks.append(RESULT_SCHEMA_HINT)
    return "\n".join(blocks)


def research_one(client, prompt, model, web_tools, max_tokens=3500):
    messages = [{"role": "user", "content": prompt}]
    resp = None
    for _ in range(6):  # bound the server-tool resume loop
        resp = client.messages.create(
            model=model, max_tokens=max_tokens,
            thinking={"type": "adaptive"}, tools=web_tools, messages=messages,
        )
        if resp.stop_reason == "pause_turn":
            messages = [messages[0], {"role": "assistant", "content": resp.content}]
            continue
        break
    return _extract_json("".join(b.text for b in resp.content if b.type == "text"))


VERIFY_HINT = """Return ONLY JSON: {"supported": true|false, "note": "<8 words>"}.
supported=true ONLY if the figure below literally appears at (or is directly stated by) the cited page
when you fetch it. If the page doesn't load, doesn't contain the figure, or contradicts it, supported=false."""


def verify_one(client, cand, web_tools):
    """Adversarial second pass: re-fetch the cited URL and confirm the number is actually there."""
    fig = cand.get("metric_display") or (
        f"{cand.get('metric_value')} {cand.get('metric_unit') or ''}".strip())
    prompt = (f"{VERIFY_HINT}\n\nClaimed figure: {fig}\nFor law: {cand.get('law_title')}\n"
              f"Cited source: {cand.get('source_url')}\n\nFetch that URL and check.")
    try:
        obj = research_one(client, prompt, MODEL, web_tools, max_tokens=1500)
        return bool(obj.get("supported")), (obj.get("note") or "")[:80]
    except (anthropic.APIError, ValueError, TypeError) as e:
        return False, f"verify error ({type(e).__name__})"


# ---- helpers ----

def _extract_json(s):
    s = (s or "").strip()
    if "```" in s:
        s = s.split("```")[1]
        s = s[4:].strip() if s.lower().startswith("json") else s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        a, b = s.find("{"), s.rfind("}")
        if a != -1 and b != -1:
            try:
                return json.loads(s[a:b + 1])
            except json.JSONDecodeError:
                pass
    return {}


def _slug(t, cand):
    hint = (cand.get("slug_hint") or "").strip().lower()
    hint = re.sub(r"[^a-z0-9]+", "-", hint).strip("-")
    bn = re.sub(r"[^a-z0-9]+", "", (t.bill_number or "").lower())
    base = f"{(t.state or '').lower()}-{bn}" + (f"-{hint}" if hint else "")
    return base[:100] or f"bill-{t.id}"


def _news_query(t):
    """A focused recent-news query: the law's distinctive words + outcome verbs."""
    title = (t.title or "")[:120]
    return f'{t.state} "{t.bill_number}" OR ({title} recycling OR restored OR diverted OR collected)'


def _fig_str(cand):
    return cand.get("metric_display") or (
        f"{cand.get('metric_value')} {cand.get('metric_unit') or ''}".strip()
        if cand.get("metric_value") is not None else "(no figure)")


def resolve_bill_id(engine, state, bill_number):
    """Best-effort lookup of a bills.id by (state, bill_number) — used to make the fixing law clickable."""
    bn = (bill_number or "").strip()
    if not (state and bn):
        return None
    with engine.connect() as c:
        return c.execute(
            text("select id from bills where state=:s and bill_number=:b limit 1"),
            {"s": state, "b": bn},
        ).scalar()


def upsert_outcome(engine, t, cand, slug):
    """Insert as reviewed=FALSE. On slug conflict, refresh ONLY if the existing row is still unreviewed
    (never clobber a human-approved figure)."""
    rem_note = cand.get("remediation_note") or None
    rem_bn = cand.get("remediation_bill_number") or None
    # Only negative/mixed outcomes carry a remediation; ignore any stray note on a positive one.
    if cand.get("direction") == "positive":
        rem_note, rem_bn = None, None
    rem_bill_id = resolve_bill_id(engine, t.state, rem_bn) if rem_bn else None
    payload = {
        "slug": slug, "bill_id": t.id, "state": t.state, "bill_number": t.bill_number,
        "law_title": cand.get("law_title") or t.title,
        "instrument_type": cand.get("instrument_type") or t.instrument_type,
        "material_categories": json.dumps(cand.get("material_categories") or t.material_categories),
        "direction": cand.get("direction"),
        "metric_label": cand.get("metric_label"),
        "metric_value": cand.get("metric_value"),
        "metric_unit": cand.get("metric_unit"),
        "metric_display": cand.get("metric_display"),
        "summary": cand.get("summary") or "",
        "attribution": cand.get("attribution"),
        "as_of_date": cand.get("as_of_date") or None,
        "source_name": cand.get("source_name"),
        "source_url": cand.get("source_url"),
        "confidence": cand.get("confidence"),
        "remediation_note": rem_note,
        "remediation_bill_number": rem_bn,
        "remediated_by_bill_id": rem_bill_id,
    }
    with engine.begin() as c:
        c.execute(text("""
            insert into bill_outcome
              (slug, bill_id, state, bill_number, law_title, instrument_type, material_categories,
               direction, metric_label, metric_value, metric_unit, metric_display, summary,
               attribution, as_of_date, source_name, source_url, confidence, reviewed,
               remediation_note, remediation_bill_number, remediated_by_bill_id, remediation_checked_at)
            values
              (:slug, :bill_id, :state, :bill_number, :law_title, :instrument_type,
               cast(:material_categories as jsonb), :direction, :metric_label, :metric_value,
               :metric_unit, :metric_display, :summary, :attribution, :as_of_date, :source_name,
               :source_url, :confidence, false,
               :remediation_note, :remediation_bill_number, :remediated_by_bill_id, now())
            on conflict (slug) do update set
              bill_id=excluded.bill_id, law_title=excluded.law_title,
              instrument_type=excluded.instrument_type, material_categories=excluded.material_categories,
              direction=excluded.direction, metric_label=excluded.metric_label,
              metric_value=excluded.metric_value, metric_unit=excluded.metric_unit,
              metric_display=excluded.metric_display, summary=excluded.summary,
              attribution=excluded.attribution, as_of_date=excluded.as_of_date,
              source_name=excluded.source_name, source_url=excluded.source_url,
              confidence=excluded.confidence, remediation_note=excluded.remediation_note,
              remediation_bill_number=excluded.remediation_bill_number,
              remediated_by_bill_id=excluded.remediated_by_bill_id,
              remediation_checked_at=now()
            where bill_outcome.reviewed = false
        """), payload)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    ap = argparse.ArgumentParser()
    ap.add_argument("--prod-dsn", default=None)
    ap.add_argument("--state", default=None, help="two-letter filter")
    ap.add_argument("--material", default=None, help="material_categories filter, e.g. organics")
    ap.add_argument("--instrument", default=None, help="instrument_type filter, e.g. incentives")
    ap.add_argument("--since-year", type=int, default=None, help="only laws acted on in/after this year")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--min-confidence", type=float, default=0.5)
    ap.add_argument("--max-per-bill", type=int, default=1,
                    help="how many outcomes a single law may accumulate. 1 = original behaviour (skip "
                         "any law with an outcome). Raise it for multi-outcome coverage — the research "
                         "pass is told what's on file and hunts a DISTINCT additional impact.")
    ap.add_argument("--rank", action="store_true", help="Haiku pre-rank the slice; research best first")
    ap.add_argument("--rank-keep", type=float, default=0.45, help="drop pre-rank scores below this")
    ap.add_argument("--rank-pool", type=int, default=250,
                    help="with --rank, how many laws to score before picking the top --limit. Large by "
                         "default: documented outcomes favour OLD established laws, so a small "
                         "newest-first pool misses them.")
    ap.add_argument("--no-verify", action="store_true", help="skip the adversarial re-fetch pass")
    ap.add_argument("--fred", action="store_true", help="attach FRED macro context to prompts")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true", help="list the slice, make no API calls")
    ap.add_argument("--preview", action="store_true", help="research + print, but DO NOT write to DB")
    ap.add_argument("--bill", default=None,
                    help="backtest ONE bill (STATE:BILLNUMBER, e.g. TX:HB3487) even if it already has "
                         "an outcome — for verification. Forces --preview; the reviewed=true row is safe.")
    args = ap.parse_args()

    engine = create_engine(args.prod_dsn or settings.database_url)
    if args.bill:
        # Backtest mode: one specific bill, never written (the vetted row stays untouched).
        args.preview = True
        st, _, bn = args.bill.partition(":")
        if not bn:
            sys.exit("--bill needs STATE:BILLNUMBER, e.g. --bill TX:HB3487")
        targets = collect_one_bill(engine, st.strip(), bn.strip())
        if not targets:
            sys.exit(f"No bill found for {args.bill}.")
    else:
        targets = collect_targets(engine, args.state, args.material, args.instrument,
                                  args.since_year, args.rank_pool if args.rank else args.limit,
                                  max_per_bill=args.max_per_bill)
    where = " (PROD)" if args.prod_dsn else ""
    cap = "" if args.max_per_bill <= 1 else f" (< {args.max_per_bill} outcomes each)"
    print(f"Enacted in-scope laws needing research{cap}: {len(targets)}{where}\n")
    if not args.rank:
        for t in targets:
            print(f"  {t.state} {t.bill_number or '?':22s} {(t.title or '')[:70]}")
    if args.dry_run:
        print("\n--dry-run: no API calls made.")
        return
    if not targets:
        return
    if not settings.anthropic_api_key:
        sys.exit("\nERROR: anthropic_api_key not set. Use --dry-run to scope work without the API.")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=600.0, max_retries=4)
    web_tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]

    # Optional cheap pre-rank, then keep the top --limit above the floor.
    if args.rank:
        print(f"\nPre-ranking {len(targets)} laws (Haiku)...")
        scored = []
        for t in targets:
            s, why = rank_one(client, t)
            scored.append((s, why, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        for s, why, t in scored[:args.limit + 4]:
            print(f"  {s:.2f}  {t.state} {t.bill_number or '?':18s} {why}")
        targets = [t for s, _w, t in scored if s >= args.rank_keep][:args.limit]
        print(f"\nResearching top {len(targets)} (score >= {args.rank_keep}).")

    accepted, rejected = [], []
    with httpx.Client(timeout=20.0) as http:
        for i, t in enumerate(targets, 1):
            print(f"\n[{i}/{len(targets)}] researching {t.state} {t.bill_number} — {(t.title or '')[:60]}")
            news = search_news(_news_query(t), http=http, page_size=6)
            news_lines = [h.as_line() for h in news]
            if news_lines:
                print(f"    news: {len(news_lines)} recent hit(s)")
            fred_lines = []
            if args.fred:
                mats = " ".join(t.material_categories or []) or "recycling"
                fred_lines = [s.as_line() for s in fred_search(f"{mats} recycling", http=http, limit=3)]

            already = existing_outcomes(engine, t.id)
            if already:
                print(f"    {len(already)} outcome(s) on file — hunting a distinct one")
            try:
                cand = research_one(
                    client, build_prompt(t, news_lines, fred_lines, already), args.model, web_tools)
            except anthropic.BadRequestError as e:
                sys.exit(f"\nAPI rejected the request (web tools may not be enabled on this key): {e.message}")
            except (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.APIStatusError) as e:
                print(f"    -> API error, skipping: {type(e).__name__}")
                rejected.append((t, {}, f"api error ({type(e).__name__})"))
                time.sleep(args.delay)
                continue

            why = _validate(cand, args.min_confidence)
            if why:
                print(f"    -> rejected: {why}")
                rejected.append((t, cand, why))
                time.sleep(args.delay)
                continue

            bucket, code, _final, note = classify(cand["source_url"], http)
            if bucket not in ACCEPTABLE_BUCKETS:
                print(f"    -> source link {bucket} [{code}], dropping: {cand['source_url']}")
                rejected.append((t, cand, f"{bucket} link ({note})"))
                time.sleep(args.delay)
                continue

            if not args.no_verify:
                ok, vnote = verify_one(client, cand, web_tools)
                if not ok:
                    print(f"    -> figure NOT confirmed at source: {vnote}")
                    rejected.append((t, cand, f"unverified ({vnote})"))
                    time.sleep(args.delay)
                    continue
                print(f"    verify: confirmed ({vnote})")

            slug = _slug(t, cand)
            print(f"    [OK] [{cand['direction']:>8s}] {_fig_str(cand):>26s}  conf={cand.get('confidence')}  {slug}")
            print(f"         {cand['source_url']}")
            if not args.preview:
                upsert_outcome(engine, t, cand, slug)
            accepted.append((t, cand, slug))
            time.sleep(args.delay)

    # ---- summary ----
    print("\n" + "=" * 72)
    verb = "found (NOT written --preview)" if args.preview else "written as reviewed=FALSE"
    print(f"{len(accepted)} candidate(s) {verb}; {len(rejected)} rejected of {len(targets)} researched.")
    if accepted and not args.preview:
        print("Review them in the /admin console (Outcomes) — approve, edit, or reject. Nothing is "
              "public until you approve it.")
    print("=" * 72)
    for t, cand, slug in accepted:
        print(f"  [{cand['direction']:>8s}] {t.state} {t.bill_number:18s} {_fig_str(cand):>24s}  ({slug})")
    if rejected:
        print("\n# not proposed:")
        for t, cand, why in rejected:
            print(f"#   {t.state} {t.bill_number}: {why}")


def _validate(cand, min_conf):
    """Return a rejection reason string, or '' if the candidate is structurally acceptable."""
    if not cand:
        return "unparseable response"
    if not cand.get("found"):
        return "no measured outcome found"
    if not cand.get("source_url"):
        return "no source_url"
    if cand.get("direction") not in VALID_DIRECTIONS:
        return f"bad direction ({cand.get('direction')})"
    if cand.get("attribution") not in VALID_ATTRIBUTION:
        return f"bad attribution ({cand.get('attribution')})"
    if cand.get("metric_value") is None and not cand.get("metric_display"):
        return "no figure (need metric_value or metric_display)"
    if not (cand.get("summary") or "").strip():
        return "empty summary"
    if (cand.get("confidence") or 0) < min_conf:
        return f"below confidence floor ({cand.get('confidence')})"
    return ""


if __name__ == "__main__":
    main()
