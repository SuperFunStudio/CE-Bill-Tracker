"""Extract compliance deadlines for the HISTORICAL backfill bills using LegiScan bill text.

Why a separate script
---------------------
scripts/backfill_deadlines.py fetches full text from OpenStates by openstates_id. The
historical backfill rows have synthetic ids ("hist:<hash>") with no OpenStates text, so that
script can't reach them. This variant pulls full text from LegiScan instead — getBill ->
pick the best text document -> getBillText -> Sonnet compliance extraction -> write
bills.compliance_details + compliance_deadlines rows (identical output shape to the
OpenStates backfill, so the Upcoming Deadlines page treats them the same).

Targets recent (>= 2022) hist rows missing compliance_details — older laws' deadlines are
in the past and the timeline is future-only, so they'd never surface.

Text source per bill: the wired legiscan_bill_id when present, else a LegiScan getSearch
(exact bill# + state). HTML documents are preferred (tags stripped); image/scanned PDFs that
yield no readable text are skipped (left as future candidates), never written empty.

Run (free LegiScan tier + a few Sonnet calls — costs <$1):
    python scripts/backfill_deadlines_legiscan.py --dry-run            # list + show text availability, no Sonnet/writes
    python scripts/backfill_deadlines_legiscan.py                      # local
    python scripts/backfill_deadlines_legiscan.py --dsn "postgresql://signalscout:...@127.0.0.1:55432/signalscout"
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

import base64  # noqa: E402

import httpx  # noqa: E402

from app.classification.sonnet_extractor import SonnetExtractor  # noqa: E402
from app.ingestion.legiscan import LegiScanClient  # noqa: E402
from app.ingestion.openstates import _extract_pdf_text  # noqa: E402

# Bills LegiScan can't resolve (year-prefixed CO numbers, DC law-numbers, search misses):
# fetch text from a hand-supplied page (codified law / legislature / official program /
# EPR tracker) instead. Keyed by (state, DB bill_number).
TEXT_URL_OVERRIDES: dict[tuple[str, str], str] = {
    ("DC", "D.C. Law 24-320"): "https://code.dccouncil.gov/us/dc/council/laws/24-320",
    ("IL", "SB-836"): "https://epa.illinois.gov/topics/waste-management/waste-disposal/paint.html",
    ("MN", "HF-3911"): "https://epr.sustainablepackaging.org/policies/HF3911",
    ("CO", "HB26-1111"): "https://leg.colorado.gov/bills/HB26-1111",
    ("CO", "HB22-1355"): "https://leg.colorado.gov/bills/hb22-1355",
}

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Prefer the most final version when several text docs exist.
_TYPE_RANK = {"chaptered": 6, "act": 6, "enrolled": 5, "engrossed": 4,
              "comm sub": 3, "amended": 3, "introduced": 1}


def _normalize_dsn(dsn: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return dsn if prefix == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(prefix):]
    return dsn


def _parse_date(value) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _canon(num: str | None) -> str:
    if not num:
        return ""
    raw = num.upper().replace("-", "").replace(" ", "").replace(".", "")
    m = re.match(r"^([A-Z]+)0*(\d+)", raw)
    return f"{m.group(1)}{m.group(2)}" if m else raw


def _html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


# Date/deadline cues used to build a focused excerpt for long bills.
_DATE_SIGNAL = re.compile(
    r"(20[2-3]\d|January|February|March|April|May|June|July|August|September|October|"
    r"November|December|no later than|effective date|deadline|shall (?:register|submit|"
    r"report|begin|implement)|begins on|due (?:by|no)|by which date)", re.I)


def _focus_excerpt(s: str, head: int = 2500, limit: int = 11500, win: int = 350) -> str:
    """For bills longer than the extractor's 12k cap, return the head (covered products /
    definitions usually live up top) plus the date-bearing windows, so compliance deadlines
    deep in the text aren't truncated away. Short bills pass through unchanged.
    """
    if len(s) <= limit:
        return s
    out = s[:head]
    spans: list[tuple[int, int]] = []
    for m in _DATE_SIGNAL.finditer(s, head):
        a, b = max(head, m.start() - win), m.end() + win
        if spans and a <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], b))
        else:
            spans.append((a, b))
    for a, b in spans:
        if len(out) >= limit:
            break
        out += "\n…\n" + s[a:b]
    return out[:limit]


def _readable(s: str) -> bool:
    """Heuristic: enough printable content to be bill text (not decoded PDF binary)."""
    if len(s) < 400:
        return False
    printable = sum(c.isprintable() or c in "\n\t" for c in s[:4000])
    return printable / min(len(s), 4000) > 0.85


async def _resolve_bill_id(client: LegiScanClient, row) -> int | None:
    if row.legiscan_bill_id:
        return int(row.legiscan_bill_id)
    # Fallback: search for an exact bill#/state match near the enactment year.
    year = row.status_date.year if row.status_date else None
    target = _canon(row.bill_number)
    if not target:
        return None
    for y in ([year, None] if year else [None]):
        try:
            res = await client.search(row.bill_number.replace("-", " "), state=row.state, year=y)
        except Exception:
            continue
        for r in res:
            if r.get("state") == row.state and _canon(r.get("bill_number")) == target:
                return int(r["bill_id"])
    return None


async def _doc_text(client: LegiScanClient, doc_id: int, mime: str) -> str:
    """Fetch one text document and decode it to plain text by mime (html/pdf/plain)."""
    data = await client._get("getBillText", id=doc_id)
    encoded = (data.get("text") or {}).get("doc", "")
    if not encoded:
        return ""
    try:
        blob = base64.b64decode(encoded)
    except Exception:  # noqa: BLE001
        return ""
    m = (mime or "").lower()
    if "pdf" in m or blob[:5] == b"%PDF-":
        return _extract_pdf_text(blob)
    try:
        s = blob.decode("utf-8")
    except UnicodeDecodeError:
        s = blob.decode("latin-1", errors="replace")
    return _html_to_text(s) if ("html" in m or "<" in s[:200]) else s


async def _fetch_url_text(url: str) -> str:
    """Fetch a page/PDF and return plain text (HTML tags stripped). '' on failure."""
    try:
        async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=30,
                                     headers={"User-Agent": _UA, "Accept": "text/html,application/pdf,*/*"}) as c:
            r = await c.get(url)
    except Exception:  # noqa: BLE001
        return ""
    if r.status_code >= 400:
        return ""
    ct = (r.headers.get("content-type") or "").lower()
    if "pdf" in ct or r.content[:5] == b"%PDF-":
        return _extract_pdf_text(r.content)
    return _html_to_text(r.text)


async def _fetch_text(client: LegiScanClient, bill_id: int) -> tuple[str, str]:
    """Return (plain_text, doc_label). Prefers HTML, then PDF; most-final version first."""
    bill = await client.get_bill(bill_id)
    docs = bill.get("texts") or []
    if not docs:
        return "", "no-docs"

    def rank(d):
        is_html = "html" in (d.get("mime") or "").lower()
        return (1 if is_html else 0, _TYPE_RANK.get((d.get("type") or "").lower(), 2))

    for d in sorted(docs, key=rank, reverse=True):
        doc_id = d.get("doc_id")
        if not doc_id:
            continue
        txt = await _doc_text(client, int(doc_id), d.get("mime") or "")
        if _readable(txt):
            return txt, f"{d.get('type','?')}/{d.get('mime','?')}"
    return "", "no-readable-text"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--since-year", type=int, default=2022)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--all", action="store_true", help="Reprocess even rows that already have compliance_details.")
    ap.add_argument("--only", default=None,
                    help="Force-reprocess only these bills (comma-separated STATE:bill_number, "
                         "e.g. 'NY:S-5027C,SC:S-171'), ignoring the missing-details filter.")
    ap.add_argument("--dry-run", action="store_true", help="Show text availability via LegiScan; no Sonnet, no writes.")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    cols = "id, state, bill_number, title, source_url, legiscan_bill_id, status_date"
    if args.only:
        pairs = [tuple(p.split(":", 1)) for p in args.only.split(",") if ":" in p]
        ors = " OR ".join(f"(state = :s{i} AND bill_number = :b{i})" for i in range(len(pairs)))
        sql = f"SELECT {cols} FROM bills WHERE openstates_id LIKE 'hist:%' AND ({ors})"
        params: dict = {}
        for i, (s, b) in enumerate(pairs):
            params[f"s{i}"], params[f"b{i}"] = s.strip(), b.strip()
    else:
        clauses = ["openstates_id LIKE 'hist:%'", "ce_relevant = true",
                   "(status_date IS NULL OR status_date >= :since)"]
        if not args.all:
            clauses.append("compliance_details IS NULL")
        sql = (f"SELECT {cols} FROM bills WHERE {' AND '.join(clauses)} "
               "ORDER BY status_date DESC NULLS LAST LIMIT :limit")
        params = {"since": date(args.since_year, 1, 1), "limit": args.limit}

    async with Session() as db:
        bills = list((await db.execute(text(sql), params)).all())
        print(f"{len(bills)} historical candidates (>= {args.since_year}, "
              f"{'all' if args.all else 'missing-details only'})\n")

        extractor = None if args.dry_run else SonnetExtractor()
        processed = wrote = skipped = 0
        async with LegiScanClient() as client:
            for b in bills:
                tag = f"{b.state} {b.bill_number or '?'}"
                try:
                    override = TEXT_URL_OVERRIDES.get((b.state, b.bill_number or ""))
                    if override:
                        full_text = await _fetch_url_text(override)
                        label = f"url:{httpx.URL(override).host}"
                        if not full_text:
                            skipped += 1
                            print(f"  [skip] {tag}: no text from {override}")
                            continue
                    else:
                        bill_id = await _resolve_bill_id(client, b)
                        if not bill_id:
                            skipped += 1
                            print(f"  [skip] {tag}: no LegiScan bill id")
                            continue
                        full_text, label = await _fetch_text(client, bill_id)
                        if not full_text:
                            skipped += 1
                            print(f"  [skip] {tag}: {label} (id {bill_id})")
                            continue
                    if args.dry_run:
                        print(f"  [text] {tag}: {len(full_text):>6} chars  {label}")
                        continue

                    ex = await extractor.extract(state=b.state, bill_number=b.bill_number or "",
                                                 title=b.title or "", full_text=_focus_excerpt(full_text))
                    await db.execute(
                        text("UPDATE bills SET compliance_details = CAST(:cd AS jsonb), updated_at = now() WHERE id = :id"),
                        {"cd": json.dumps(ex.raw_json), "id": b.id})
                    await db.execute(text("DELETE FROM compliance_deadlines WHERE bill_id = :bid"), {"bid": b.id})

                    rows: list[tuple[str, date, str]] = []
                    for dl in ex.deadlines:
                        d = _parse_date(dl.get("date"))
                        if d:
                            rows.append((dl.get("type", "compliance"), d, dl.get("description", "")))
                    eff = _parse_date(ex.effective_date)
                    if eff:
                        rows.append(("effective", eff, f"{b.bill_number or 'Bill'} takes effect"))
                    comp = _parse_date(ex.raw_json.get("compliance_date"))
                    if comp:
                        rows.append(("compliance", comp, f"{b.bill_number or 'Bill'} compliance date"))

                    seen = set()
                    for dtype, ddate, desc in rows:
                        if (ddate, dtype) in seen:
                            continue
                        seen.add((ddate, dtype))
                        await db.execute(
                            text("INSERT INTO compliance_deadlines "
                                 "(bill_id, state, deadline_type, deadline_date, description, source_url) "
                                 "VALUES (:bid, :state, :dtype, :ddate, :desc, :src)"),
                            {"bid": b.id, "state": b.state, "dtype": dtype, "ddate": ddate,
                             "desc": desc, "src": b.source_url})
                        wrote += 1
                    await db.commit()
                    processed += 1
                    fut = sum(1 for dd, _ in seen if dd >= date.today())
                    print(f"  [ok]   {tag}: {len(seen)} deadline(s), {fut} future  ({label})")
                except Exception as e:  # noqa: BLE001
                    await db.rollback()
                    print(f"  [fail] {tag}: {type(e).__name__}: {e}")

        if args.dry_run:
            print(f"\n(dry run — no Sonnet calls, no writes)")
        else:
            print(f"\nprocessed {processed}/{len(bills)} ({skipped} skipped), wrote {wrote} deadline rows")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
