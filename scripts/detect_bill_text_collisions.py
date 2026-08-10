"""Find bill_texts rows holding the WRONG bill's text (same number, different session).

Legislatures reuse bill numbers every session. The LegiScan rung of the text ladder used to resolve
an id by (state, bill_number) with no session constraint, and getSearch skews to the CURRENT
session — so an older bill could silently adopt a same-numbered new bill's document. Prod evidence:
CA SB-54 (2022 packaging EPR) held the 2025-26 "court fee waivers" text, and every extracted
compliance dimension came back not_applicable because the extractor was reading a court statute.

app/ingestion/bill_text.py now constrains the search by year and verifies the resolved bill's
session window, so new fetches cannot do this. This script finds the rows already stored that way.

READ-ONLY. It never writes; --json emits the bill ids so a repair pass can clear and re-fetch them.

Two independent signals, either one flags a row:

  title_overlap  bills.title is trusted metadata (it comes from the bill record, not the text
                 fetch). If the stored text is the right document, the title's distinctive words
                 appear in it. CA SB-54's title is "Solid waste: reporting, packaging..." against
                 court-fee text — zero overlap. Applies to every region and text source.

  session_year   Many US bill documents print their session in a header ("CALIFORNIA LEGISLATURE—
                 2025-2026 REGULAR SESSION", "THIRTY-THIRD LEGISLATURE, 2025"). A session year
                 later than the bill's own year is proof of a collision, not a heuristic.

Usage:
    python scripts/detect_bill_text_collisions.py                       # local
    python scripts/detect_bill_text_collisions.py --dsn "postgresql://…"  # prod via Cloud SQL proxy
    python scripts/detect_bill_text_collisions.py --json suspects.json --min-overlap 0.25
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402

# Words too common in bill titles to carry signal — their presence in a document says nothing about
# whether it is the RIGHT document.
_STOP = set("""a an the of and or to in for on by with from as at is are be shall may act relating
concerning provide provides providing amend amends amending certain other relate relates state
section sections code chapter law laws bill new requirement requirements program programs""".split())

_WORD_RE = re.compile(r"[a-z]{4,}")
# "2025-2026 REGULAR SESSION" / "2025–2026 Regular Session" — the en-dash variant matters, CA uses it.
_SESSION_RE = re.compile(r"(20\d{2})\s*[-–—]\s*20\d{2}\s+REGULAR\s+SESSION", re.I)
# "THIRTY-THIRD LEGISLATURE, 2025" (HI and friends).
_LEG_YEAR_RE = re.compile(r"LEGISLATURE,?\s+(20\d{2})", re.I)


def _normalize_dsn(dsn: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return dsn if prefix == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(prefix):]
    return dsn


def _tokens(s: str | None) -> set[str]:
    return {w for w in _WORD_RE.findall((s or "").lower()) if w not in _STOP}


def title_overlap(title: str | None, body: str) -> float | None:
    """Fraction of the title's distinctive words that appear in the document. None when the title
    carries no distinctive words at all (e.g. a bare "AN ACT" or an empty title), so an unscoreable
    title is reported as such rather than silently counted as a 0% miss and flagged."""
    t = _tokens(title)
    if not t:
        return None
    return len(t & _tokens(body[:6000])) / len(t)


def text_session_year(body: str) -> int | None:
    """The session year the document prints in its own header, if it prints one."""
    head = body[:1500]
    for rx in (_SESSION_RE, _LEG_YEAR_RE):
        m = rx.search(head)
        if m:
            return int(m.group(1))
    return None


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", help="Database URL (defaults to settings.database_url).")
    ap.add_argument("--min-overlap", type=float, default=0.25,
                    help="Flag when under this fraction of title words appear in the text (default 0.25).")
    ap.add_argument("--region", default=None, help="Limit to one region (e.g. US).")
    # The collision is a property of the LegiScan rung of the text ladder, so only ladder-fetched
    # rows can exhibit it. Foreign/enabler imports (bill_texts.source IS NULL) carry a CURATED title
    # — "Loi AGEC (anti-waste & circular economy)" against article text — which scores near-zero
    # overlap while being perfectly correct. Scanning them produces nothing but false positives.
    ap.add_argument("--all-sources", action="store_true",
                    help="Also scan rows with no ladder source (foreign imports). Noisy — these "
                         "have curated titles that never match their document text.")
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--json", dest="json_path", help="Write flagged bill ids + reasons to this file.")
    ap.add_argument("--show", type=int, default=25, help="How many flagged rows to print (default 25).")
    args = ap.parse_args()

    engine = create_async_engine(_normalize_dsn(args.dsn or settings.database_url))
    sql = (
        "select b.id, b.region, b.state, b.bill_number, b.title, b.legiscan_bill_id, "
        "       extract(year from coalesce(b.status_date, b.last_action_date))::int as bill_year, "
        "       t.source, t.text "
        "from bills b join bill_texts t on t.bill_id = b.id "
        "where t.text is not null "
        + ("" if args.all_sources else "and t.source is not null ")
        + ("and b.region = :region " if args.region else "")
        + "order by b.id limit :limit"
    )
    params: dict = {"limit": args.limit}
    if args.region:
        params["region"] = args.region

    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params)).all()
    await engine.dispose()

    flagged: list[dict] = []
    reasons: Counter = Counter()
    unscoreable = 0

    for r in rows:
        body = r.text or ""
        why: list[str] = []
        codes: list[str] = []

        ty = text_session_year(body)
        if ty and r.bill_year and ty > r.bill_year:
            why.append(f"text says session {ty}, bill is {r.bill_year}")
            codes.append("session_year")

        ov = title_overlap(r.title, body)
        if ov is None:
            unscoreable += 1
        elif ov < args.min_overlap:
            why.append(f"title overlap {ov:.0%}")
            codes.append("title_overlap")

        if why:
            reasons.update(codes)
            if len(codes) > 1:
                reasons.update(["both_signals"])
            flagged.append({
                "signals": codes,
                "bill_id": r.id, "region": r.region, "state": r.state,
                "bill_number": r.bill_number, "bill_year": r.bill_year,
                "title": r.title, "source": r.source,
                "had_stored_legiscan_id": r.legiscan_bill_id is not None,
                "text_head": body[:160].strip(), "reasons": why,
            })

    print(f"scanned {len(rows)} bill_texts rows"
          + (f" (region={args.region})" if args.region else ""))
    print(f"unscoreable titles (too few distinctive words): {unscoreable}")
    print(f"FLAGGED: {len(flagged)}")
    # session_year is proof (a document cannot postdate its own bill); title_overlap is a heuristic.
    # Rows carrying BOTH are the highest-confidence repair candidates.
    for code in ("session_year", "title_overlap", "both_signals"):
        if reasons.get(code):
            print(f"  by signal — {code:14s} {reasons[code]}")
    # A flagged row that HAD a stored legiscan_bill_id did not come from the search fallback, so it
    # needs a different explanation — worth separating rather than lumping into one repair batch.
    from_search = sum(1 for f in flagged if not f["had_stored_legiscan_id"])
    print(f"  of which resolved via the search fallback (the known bug): {from_search}")
    print(f"  with a stored legiscan_bill_id (investigate separately):   {len(flagged) - from_search}")

    for f in flagged[: args.show]:
        print(f"\n  id={f['bill_id']} {f['state'] or f['region']} {f['bill_number']} ({f['bill_year']}) "
              f"[{f['source']}] {'; '.join(f['reasons'])}")
        print(f"     title: {(f['title'] or '')[:78]}")
        print(f"     text : {f['text_head'][:110]}")
    if len(flagged) > args.show:
        print(f"\n  … {len(flagged) - args.show} more (raise --show, or use --json for the full set)")

    if args.json_path:
        Path(args.json_path).write_text(json.dumps(flagged, indent=2, default=str), encoding="utf-8")
        print(f"\nwrote {len(flagged)} flagged rows to {args.json_path}")


if __name__ == "__main__":
    asyncio.run(main())
