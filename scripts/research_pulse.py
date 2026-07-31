"""Timeliness PRE-PASS for the short-form article pipeline — a "social listening" step that runs BEFORE
we draft anything, so a Friday Fact / crop / pair is written about what's actually moving this week.

The ranking core lives in app/research/pulse.py and is SHARED with the admin POST /research/pulse endpoint
(the staging-page button), so the CLI briefing and the button rank identically. The discipline: the pulse
signal picks the TOPIC and TIMING; it never supplies FACTS. Two grounded, keyless signals — recent movement
in our own DB (corpus deltas) and recent Google News headlines — re-rank candidate research turns; the fact
itself still comes only from the chosen turn's cited corpus bills, via the unchanged crop/fact/pair distillers.

Run against PROD via the Cloud SQL proxy (127.0.0.1:5436), same recipe as scripts/shortform_articles.py:

    PW=$(gcloud secrets versions access latest --secret=SIGNALSCOUT_DB_PASSWORD --project=ce-bill-tracker)
    AK=$(gcloud secrets versions access latest --secret=ANTHROPIC_API_KEY --project=ce-bill-tracker)
    DATABASE_URL="postgresql://signalscout:$PW@127.0.0.1:5436/signalscout" ANTHROPIC_API_KEY="$AK" \
        venv/Scripts/python.exe scripts/research_pulse.py --top 10                       # briefing only
        venv/Scripts/python.exe scripts/research_pulse.py --all-beats --distill fact --dry-run   # per-beat preview

Briefing-only by default (writes nothing). --distill {fact,crop,pair} stages the picks as content_drafts
(status='staged') via the SAME machinery shortform_articles.py uses, so they land in the admin drafts queue.
--dry-run prints each generated piece without writing. --all-beats gives one deduped pick per news beat.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))  # so we can reuse shortform_articles' single-turn distiller

from app.database import AsyncSessionLocal  # noqa: E402
from app.research import pulse  # noqa: E402
# _make_draft(mode, turn, pair_size) is the exact single-turn distill the shortform script uses — reuse it
# so --distill shares one voice + citation path with everything else. Importing the module is side-effect free.
from shortform_articles import _make_draft  # noqa: E402

PROGRESS = Path(__file__).parent.parent / "data" / "exports" / "research_pulse.jsonl"


def _log(rec: dict):
    line = json.dumps(rec, ensure_ascii=False)
    print(line, flush=True)
    with PROGRESS.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _print_pick(n_or_beat, p: dict):
    head = f"{n_or_beat}. " if isinstance(n_or_beat, int) else f"### BEAT: {n_or_beat}  → "
    print(f"\n{head}[{p['score']}]  {p['question']}")
    print(f"     session={p['session_id']} seq={p['seq']} cited={p['cited']} "
          f"(corpus={p['corpus']} news={p['news']})")
    if p.get("moved_bills"):
        print(f"     moved: {', '.join(p['moved_bills'])}")
    if p.get("hot_themes"):
        print(f"     theme: {', '.join(p['hot_themes'])}")
    if p.get("news_terms"):
        print(f"     news:  {', '.join(p['news_terms'])}")


async def _distill_picks(picks: list[dict], turns_by_key: dict, mode: str, pair_size: int,
                         dry_run: bool) -> list[str]:
    """Distill the chosen picks via the shared single-turn path. Persists a staged content_draft per pick,
    OR (dry_run) just prints the generated piece — the 'run it a few times to see what it generates' path."""
    from app.models import ContentDraft
    ids = []
    for p in picks:
        turn = turns_by_key.get((p["session_id"], p["seq"]))
        if turn is None:
            continue
        rec = await _make_draft(mode, turn, pair_size)
        if not (rec and rec.get("ok")):
            _log({"event": "distill_skip", "session_id": p["session_id"], "seq": p["seq"],
                  "reason": (rec or {}).get("error", "not_eligible")})
            continue
        if dry_run:
            print(f"\n----- {mode.upper()} PREVIEW (session={p['session_id']} seq={p['seq']}) -----")
            print("TITLE:", rec["title"])
            if rec["fields"].get("dek"):
                print("DEK:  ", rec["fields"]["dek"])
            print("\n" + rec["fields"].get("body_markdown", ""))
            _log({"event": "preview", "mode": mode, "session_id": p["session_id"], "seq": p["seq"],
                  "title": rec["title"]})
            continue
        async with AsyncSessionLocal() as db:
            draft = ContentDraft(**rec["fields"])
            db.add(draft)
            await db.commit()
            await db.refresh(draft)
        ids.append(str(draft.id))
        _log({"event": "staged", "draft_id": str(draft.id), "mode": mode,
              "session_id": p["session_id"], "seq": p["seq"], "title": rec["title"]})
    return ids


async def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=10, help="How many ranked turns to show / stage.")
    ap.add_argument("--pool", type=int, default=200, help="Newest turns to consider before re-ranking.")
    ap.add_argument("--days", type=int, default=30, help="Corpus-delta window (bill movement look-back).")
    ap.add_argument("--news-days", type=int, default=21,
                    help="Drop headlines older than this many days (default 3 weeks; try 28 for a wider net).")
    ap.add_argument("--news-query", action="append", default=None,
                    help="News query (repeatable). Omitted -> the default EPR/circular set. With "
                         "--all-beats, each query is a separate beat.")
    ap.add_argument("--all-beats", action="store_true",
                    help="One deduped pick PER beat (each --news-query, or the default set). Pair with "
                         "--distill fact to get one fact per beat.")
    ap.add_argument("--no-news", action="store_true", help="Corpus signal only (skip the news fetch).")
    ap.add_argument("--w-corpus", type=float, default=1.0, help="Corpus-signal weight.")
    ap.add_argument("--w-news", type=float, default=1.0, help="News-signal weight.")
    ap.add_argument("--owner-uid", default=pulse.CORPUS_SURVEY_UID,
                    help="Only turns owned by this uid (blank for all).")
    ap.add_argument("--min-citations", type=int, default=1, help="Skip turns citing fewer than N bills.")
    ap.add_argument("--distill", choices=["crop", "fact", "pair"], default=None,
                    help="Distill the picks via this shape (default: briefing only).")
    ap.add_argument("--dry-run", action="store_true",
                    help="With --distill: PRINT each generated piece but write no drafts (preview a batch).")
    ap.add_argument("--pair-size", type=int, choices=[2, 4], default=2, help="pair mode: bills to contrast.")
    args = ap.parse_args()

    # Research questions / bill titles carry non-ASCII (foreign law); force UTF-8 so console print never dies.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — non-reconfigurable stream (piped/redirected); best-effort only
        pass

    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text("", encoding="utf-8")

    # Shared corpus + turn signals (once).
    async with AsyncSessionLocal() as db:
        movers, hot_terms = await pulse.recent_movers(db, args.days)
        turns = await pulse.candidate_turns(db, args.owner_uid or None, args.pool, args.min_citations)
    idf = pulse.build_idf(turns)
    turns_by_key = {(str(t.session_id), t.seq): t for t in turns}
    beats = args.news_query or pulse.DEFAULT_NEWS_QUERIES

    if args.all_beats:
        _log({"event": "start", "mode": "all-beats", "pool": len(turns), "movers": len(movers),
              "beats": beats, "distill": args.distill, "dry_run": args.dry_run})
        beats_news = [(b, *pulse.fetch_news_terms([b], args.news_days)) for b in beats]
        beats_news = [(b, terms, len(heads)) for b, terms, heads in beats_news]
        picks = pulse.pick_beats(beats_news, turns, movers, hot_terms, idf, args.w_corpus, args.w_news)
        print(f"\n=== PULSE — all beats ({len(beats)}), one deduped pick each ===")
        live = []
        for p in picks:
            if p.get("skipped"):
                print(f"\n### BEAT: {p['beat']}  → skipped ({p['reason']}; {p['headlines']} headlines)")
                _log({"event": "beat_skip", **p})
                continue
            _print_pick(p["beat"], p)
            _log({"event": "beat_pick", **p})
            live.append(p)
        if args.distill and live:
            ids = await _distill_picks(live, turns_by_key, args.distill, args.pair_size, args.dry_run)
            if not args.dry_run:
                print(f"\nStaged {len(ids)} draft(s): {', '.join(ids) or '(none)'}")
            _log({"event": "done", "mode": "all-beats", "staged": ids})
        else:
            _log({"event": "done", "mode": "all-beats", "picked": len(live)})
        return

    news_terms, headlines = (pulse.fetch_news_terms(beats, args.news_days)
                             if not args.no_news else (Counter(), []))
    ranked = pulse.rank_turns(turns, movers, hot_terms, news_terms, idf, args.top, args.w_corpus, args.w_news)
    _log({"event": "start", "pool": len(turns), "movers": len(movers), "headlines": len(headlines),
          "no_news": args.no_news, "distill": args.distill})

    print(f"\n=== PULSE — what to write this week (top {len(ranked)}; pool {len(turns)}) ===")
    for n, p in enumerate(ranked, 1):
        _print_pick(n, p)
        _log({"event": "ranked", "rank": n, **p})
    if not ranked:
        print("\n(no turns scored above zero — widen --days, add --news-query, or lower --min-citations)")

    if args.distill and ranked:
        verb = "Previewing" if args.dry_run else "Staging"
        print(f"\n{verb} {len(ranked)} {args.distill} piece(s)…")
        ids = await _distill_picks(ranked, turns_by_key, args.distill, args.pair_size, args.dry_run)
        if not args.dry_run:
            print(f"Staged {len(ids)} draft(s): {', '.join(ids) or '(none eligible)'}")
        _log({"event": "done", "staged": ids, "dry_run": args.dry_run})
    else:
        _log({"event": "done", "ranked": len(ranked), "staged": []})


if __name__ == "__main__":
    asyncio.run(main())
