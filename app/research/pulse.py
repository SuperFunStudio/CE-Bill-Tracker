"""Shared core for the research "pulse" timeliness ranker — used by BOTH scripts/research_pulse.py (the CLI
briefing) and the admin POST /research/pulse endpoint (the staging-page button), so they rank identically.

The discipline: the pulse signal picks the TOPIC and TIMING; it never supplies FACTS. It re-ranks candidate
research turns by two grounded, keyless signals and hands back which turn to distill — the fact itself still
comes only from that turn's cited corpus bills, via the unchanged crop/fact/pair distillers.

  corpus deltas — recent legislative movement in our own DB (last `days`): bills whose status_date /
                  last_action_date landed IN [cutoff, today] (future effective dates excluded), enacted-in-
                  window weighted highest. A turn scores when its cited bills are among the movers, plus a
                  lighter theme bonus when it's ABOUT what's moving.
  news          — recent Google News RSS headlines over an EPR / circular keyword set. Every term overlap is
                  IDF-weighted by the turn pool, so distinctive current-events terms (colorado, textile) drive
                  the ranking and ubiquitous ones (epr, packaging) barely move it.

IO lives at the edges: DB helpers are async and take a session; `fetch_news_terms` is blocking urllib (wrap
it in asyncio.to_thread from async callers). The scoring/ranking/beat-picking functions are pure.
"""
from __future__ import annotations

import math
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bill, ResearchSession, ResearchTurn

# The seeded corpus-survey account (kenny@superfun.studio) — the CLI's default source pool. The endpoint
# pools across ALL admin-visible turns (owner_uid=None), matching the research log.
CORPUS_SURVEY_UID = "L8BeKGapUcPfK9IydeE2gu2kV7z2"

# Default news vocabulary for the EPR / circular-economy beat. Each entry is also a "beat" in all-beats mode.
DEFAULT_NEWS_QUERIES = [
    "extended producer responsibility",
    "packaging EPR law",
    "right to repair legislation",
    "post-consumer recycled content",  # was "recycled content mandate" — returned 0 headlines; this ~22
    "plastic packaging regulation",
    "textile EPR",
    "circular economy policy",
]

# Terms too generic to carry a timeliness signal — dropped before headline/turn overlap scoring.
_STOP = set("""a an the of to in on for and or but with without from by at as is are was were be been being
this that these those it its into over under after before between during about against per via than then
new law bill act plan rule state states says will would could may can new news report update announces
year years week month new plc inc ltd co corp company companies group amid set sets get gets one two
com www org net http https news000 what who how why when where which whose""".split())

_WORD = re.compile(r"[a-z][a-z\-]{2,}")


def cited_ids(turn) -> list[int]:
    """The bills a turn's answer actually cites (falls back to the full ranked set for older turns).
    Inlined from app.api.research._cited_ids to keep this module free of an app.api import cycle."""
    ans = turn.answer or {}
    return list(ans.get("cited_bill_ids") or turn.bill_ids or [])


def _humanize(v) -> list[str]:
    """A JSONB list / scalar / None -> lowercased term tokens for theme matching."""
    if not v:
        return []
    items = v if isinstance(v, list) else [v]
    return [str(x).replace("_", " ").lower() for x in items if x]


# --- news signal (blocking; wrap in asyncio.to_thread from async callers) ---------------------------

def fetch_news_terms(queries: list[str], news_days: int) -> tuple[Counter, list[dict]]:
    """Google News RSS over each query -> (term Counter across recent headlines, headline records). Keyless
    and read-only; headlines older than `news_days` are dropped, and one flaky feed never sinks the pass."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=news_days)
    terms: Counter = Counter()
    headlines: list[dict] = []
    seen_titles: set[str] = set()
    for q in queries:
        url = ("https://news.google.com/rss/search?q="
               + urllib.parse.quote(q) + "&hl=en-US&gl=US&ceid=US:en")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research-pulse)"})
            with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 — fixed Google News host
                root = ET.fromstring(r.read())
        except Exception:  # noqa: BLE001 — one flaky feed shouldn't sink the whole pass
            continue
        for item in root.iterfind(".//item"):
            title = (item.findtext("title") or "").strip()
            pub = item.findtext("pubDate")
            when = None
            if pub:
                try:
                    when = parsedate_to_datetime(pub)
                except Exception:  # noqa: BLE001 — malformed date -> keep, don't discard the headline
                    when = None
            if when and when < cutoff:
                continue
            key = title.lower()
            if not title or key in seen_titles:
                continue
            seen_titles.add(key)
            headlines.append({"title": title, "query": q,
                              "date": when.date().isoformat() if when else None})
            # Google News titles are "Headline - Publisher" — drop the trailing publisher before tokenizing
            # so source names (Waste Dive, PlasticsToday) don't pollute the term signal.
            for w in _WORD.findall(key.rsplit(" - ", 1)[0]):
                if w not in _STOP:
                    terms[w] += 1
    return terms, headlines


# --- corpus-delta signal ----------------------------------------------------------------------------

async def recent_movers(db: AsyncSession, days: int) -> tuple[dict[int, dict], Counter]:
    """Bills that MOVED in the last `days` (status/action date in [cutoff, today]), ce_relevant only.
    Returns (by_id mover detail, combined hot-theme Counter over material + instrument). Future dates are
    excluded — foreign status_dates are synthetic (year-only) and enacted laws carry future EFFECTIVE
    dates; neither is news that broke this month. enacted-in-window is flagged for the score weighting."""
    today = date.today()
    cutoff = today - timedelta(days=days)
    rows = (await db.execute(
        select(Bill.id, Bill.state, Bill.bill_number, Bill.status, Bill.status_date,
               Bill.last_action_date, Bill.material_categories, Bill.instrument_type, Bill.title)
        .where(Bill.ce_relevant.is_(True),
               or_(Bill.status_date >= cutoff, Bill.last_action_date >= cutoff)))).all()
    movers: dict[int, dict] = {}
    hot: Counter = Counter()
    for r in rows:
        in_window = [d for d in (r.status_date, r.last_action_date) if d and cutoff <= d <= today]
        if not in_window:
            continue
        moved = max(in_window)
        mats = _humanize(r.material_categories)
        insts = _humanize(r.instrument_type)
        enacted = ((r.status or "").lower() == "enacted"
                   and bool(r.status_date and cutoff <= r.status_date <= today))
        movers[r.id] = {
            "ref": f"{r.state} {r.bill_number}" if r.bill_number else r.state,
            "status": r.status, "date": moved.isoformat() if moved else None,
            "enacted_in_window": enacted, "materials": mats, "instruments": insts,
            "title": (r.title or "")[:120],
        }
        for m in mats:
            hot[m] += 1
        for i in insts:
            hot[i] += 1
    return movers, hot


async def candidate_turns(db: AsyncSession, owner_uid: str | None, pool: int, min_citations: int) -> list:
    """Newest-first research turns with answers, filtered by owner (None = all) and min-citations."""
    q = (select(ResearchTurn)
         .join(ResearchSession, ResearchSession.id == ResearchTurn.session_id)
         .order_by(ResearchTurn.created_at.desc()))
    if owner_uid:
        q = q.where(ResearchSession.owner_uid == owner_uid)
    turns = (await db.execute(q.limit(pool))).scalars().all()
    out = []
    for t in turns:
        if not ((t.answer or {}).get("text") or "").strip():
            continue
        if len(cited_ids(t)) < min_citations:
            continue
        out.append(t)
    return out


# --- scoring + ranking (pure) -----------------------------------------------------------------------

def build_idf(turns: list) -> dict[str, float]:
    """Turn-level document frequency -> IDF, so scoring rewards terms RARE across the pool (colorado,
    textile) over ones in nearly every turn (epr, packaging). Without it the ubiquitous terms saturate."""
    df: Counter = Counter()
    for t in turns:
        toks = set(_WORD.findall(f"{t.question}\n{(t.answer or {}).get('text') or ''}".lower()))
        df.update(toks)
    n = len(turns) or 1
    return {term: math.log(1 + n / (1 + c)) for term, c in df.items()}


def score_turn(turn, movers: dict, hot_terms: Counter, news_terms: Counter, idf: dict,
               w_corpus: float = 1.0, w_news: float = 1.0) -> dict:
    """Blend the two signals for one turn -> a flat scored record incl. the 'why now' evidence. corpus =
    cited bills that just moved (+enacted bonus) + an idf-weighted theme bonus; news = idf-weighted
    headline-term overlap with the turn text."""
    cited = cited_ids(turn)
    text = f"{turn.question}\n{(turn.answer or {}).get('text') or ''}".lower()
    tokens = set(_WORD.findall(text))

    def w(term):  # distinctiveness weight: ~0 for a term in every turn, up toward 1 for a rare one.
        return idf.get(term, 1.0)

    cited_movers = [movers[i] for i in cited if i in movers]
    corpus_direct = sum(3 if m["enacted_in_window"] else 1 for m in cited_movers)
    theme_hits = sorted({t for t in hot_terms if t in text}, key=lambda t: -hot_terms[t] * w(t))[:5]
    corpus_theme = sum(min(hot_terms[t], 3) * w(t) for t in theme_hits)
    corpus = round(corpus_direct * 3 + corpus_theme, 1)

    news_hits = sorted((t for t in news_terms if t in tokens), key=lambda t: -news_terms[t] * w(t))[:8]
    news = round(sum(min(news_terms[t], 5) * w(t) for t in news_hits), 1)

    total = round(corpus * w_corpus + news * w_news, 1)
    return {
        "session_id": str(turn.session_id), "seq": turn.seq,
        "question": (turn.question or "")[:200], "cited": len(cited),
        "score": total, "corpus": corpus, "news": news,
        "moved_bills": [f'{m["ref"]} ({m["status"]}, {m["date"]})'
                        + (" *enacted*" if m["enacted_in_window"] else "") for m in cited_movers][:6],
        "hot_themes": theme_hits,
        "news_terms": news_hits,
    }


def rank_turns(turns: list, movers: dict, hot_terms: Counter, news_terms: Counter, idf: dict,
               top: int, w_corpus: float = 1.0, w_news: float = 1.0) -> list[dict]:
    """Score every turn against one news signal, keep score>0, newest-strongest first, capped at `top`."""
    scored = [score_turn(t, movers, hot_terms, news_terms, idf, w_corpus, w_news) for t in turns]
    scored.sort(key=lambda s: s["score"], reverse=True)
    return [s for s in scored if s["score"] > 0][:top]


def pick_beats(beats_news: list[tuple[str, Counter, int]], turns: list, movers: dict, hot_terms: Counter,
               idf: dict, w_corpus: float = 1.0, w_news: float = 1.0) -> list[dict]:
    """One deduped pick PER beat: each beat (with its own pre-fetched news) claims its top turn that no
    earlier beat took, so 'all beats' yields DISTINCT picks. A beat whose winner has zero news overlap fell
    back to the shared corpus signal — it's flagged (skipped=True, no distill) rather than dressed up as an
    on-beat pick. `beats_news` is [(beat, news_terms, n_headlines)] so the IO stays at the caller."""
    claimed: set[str] = set()
    picks: list[dict] = []
    for beat, news_terms, n_headlines in beats_news:
        scored = [score_turn(t, movers, hot_terms, news_terms, idf, w_corpus, w_news) for t in turns]
        scored.sort(key=lambda s: s["score"], reverse=True)
        chosen = next((s for s in scored if s["score"] > 0 and s["session_id"] not in claimed), None)
        if chosen is None:
            picks.append({"beat": beat, "headlines": n_headlines, "skipped": True,
                          "reason": "no unclaimed turn scored above zero"})
            continue
        if chosen["news"] <= 0:
            picks.append({"beat": beat, "headlines": n_headlines, "skipped": True,
                          "reason": "top pick has no news signal (dead/too-narrow query)"})
            continue
        claimed.add(chosen["session_id"])
        picks.append({"beat": beat, "headlines": n_headlines, "skipped": False, **chosen})
    return picks
