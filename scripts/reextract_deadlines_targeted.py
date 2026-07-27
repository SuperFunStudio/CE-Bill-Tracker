"""Re-extract compliance deadlines for LARGE, under-extracted laws — full-text, not front-windowed.

Why this exists: the live pipeline sends only ~40K chars to Sonnet (select_text_window: a 4K head +
a 36K window anchored on the first EPR keyword). For a big regulation that's just the front matter.
EU regs in particular put their staged obligations mid-document and their authoritative
"entry into force / application" article at the very END — e.g. PPWR (Regulation (EU) 2025/40,
451K chars) states "It shall apply from 12 August 2026" at ~82% through the text, far past the
window. So those bills got compliance_details but their real future deadlines were never captured.

This script re-runs SonnetExtractor over such bills with the WHOLE text (or a head+tail window for
the few that exceed the model context), then rebuilds their compliance_deadlines rows (region-tagged,
DELETE+INSERT — same replace semantics as scripts/backfill_deadlines.py / materialize_deadlines_from_details.py).

Two ways to run:
  * run     — synchronous, live Sonnet calls. Good for a handful of bills / validation.
  * submit  — enqueue an Anthropic Message Batch (50% of live pricing, async) and print a state path.
    collect — poll that batch; when it has ended, write every bill's rebuilt deadlines. Resumable:
              re-run collect until it prints DONE (each call polls briefly, then yields).

DB access is raw asyncpg (no ORM) so it survives prod schema drift, like the materialize script.
compliance_details / compliance_deadlines are NOT copied by push_bills_to_prod.py, so run this straight
against prod via the Cloud SQL Auth Proxy. Password comes from env (PW / PGPASSWORD), never the DSN.

    PW=$(gcloud secrets versions access latest --secret=SIGNALSCOUT_DB_PASSWORD --project=ce-bill-tracker)
    AK=$(gcloud secrets versions access latest --secret=ANTHROPIC_API_KEY --project=ce-bill-tracker)
    DSN="postgresql://signalscout@127.0.0.1:5462/signalscout"

    # dry-run the candidate set:
    PW=$PW venv/Scripts/python scripts/reextract_deadlines_targeted.py run --dsn "$DSN" --dry-run
    # BATCH (50% cost): submit, then collect until DONE:
    PW=$PW ANTHROPIC_API_KEY=$AK venv/Scripts/python scripts/reextract_deadlines_targeted.py submit --dsn "$DSN"
    PW=$PW ANTHROPIC_API_KEY=$AK venv/Scripts/python scripts/reextract_deadlines_targeted.py collect --state <path>

Costs Anthropic (Sonnet) — one large-context call per bill (batch = half price). Idempotent.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import anthropic
import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", "placeholder"))
os.environ.setdefault("DATABASE_URL", "postgresql://placeholder")

from anthropic.types.message_create_params import MessageCreateParamsNonStreaming  # noqa: E402
from anthropic.types.messages.batch_create_params import Request  # noqa: E402

from app.classification.sonnet_extractor import SONNET_MODEL, SonnetExtractor  # noqa: E402

# Keep whole-text calls inside the model's 200K-token context (leaving room for prompt + 16K output).
# ~3.6 chars/token on dense legal text -> ~480K chars ~= 133K tokens.
WHOLE_TEXT_CAP = 480_000
SCRATCH = os.environ.get("CLAUDE_SCRATCH", str(Path(__file__).parent.parent / ".batch_state"))


def _window(text: str, cap: int) -> tuple[str, str]:
    """Return (windowed_text, how). Whole if it fits; else head+tail so both the front obligations
    and the final application/transitional article survive (the two ends EU law front/back-loads)."""
    if len(text) <= cap:
        return text, "whole"
    half = cap // 2
    return f"{text[:half]}\n\n[... middle of the text omitted for length ...]\n\n{text[-half:]}", "head+tail"


def _parse_date(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _rows_for(extraction, bill_number):
    """Deduped [(deadline_type, date, description)] from an extraction: the deadlines[] array plus the
    headline effective_date / compliance_date (mirrors materialize_deadlines_from_details._rows_for)."""
    out = []
    for dl in (extraction.deadlines or []):
        if not isinstance(dl, dict):
            continue
        d = _parse_date(dl.get("date"))
        if d:
            out.append((dl.get("type") or "compliance", d, dl.get("description") or ""))
    eff = _parse_date(extraction.effective_date)
    if eff:
        out.append(("effective", eff, f"{bill_number or 'Bill'} takes effect"))
    comp = _parse_date((extraction.raw_json or {}).get("compliance_date"))
    if comp:
        out.append(("compliance", comp, f"{bill_number or 'Bill'} compliance date"))
    seen, deduped = set(), []
    for dtype, ddate, desc in out:
        k = (ddate, dtype)
        if k in seen:
            continue
        seen.add(k)
        deduped.append((dtype, ddate, desc))
    return deduped


def _api_key() -> str:
    # .strip() is load-bearing: `gcloud secrets access` on Windows emits a trailing \r, which httpx
    # rejects as an illegal header value (surfaces as APIConnectionError, not an auth error).
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key or key == "placeholder":
        print("ERROR: ANTHROPIC_API_KEY not set in env.", file=sys.stderr)
        sys.exit(1)
    return key


async def _connect(dsn):
    pw = (os.environ.get("PW") or os.environ.get("PGPASSWORD") or "").strip() or None
    return await (asyncpg.connect(dsn, password=pw) if pw else asyncpg.connect(dsn))


async def _candidates(c, min_chars, max_future, bill_numbers, limit, status, ids=None):
    if ids:
        return await c.fetch(
            """
            select b.id, coalesce(b.region,'US') region, b.state, b.bill_number, b.title, b.source_url,
                   (select max(length(text)) from bill_texts where bill_id=b.id) tlen,
                   (select count(*) from compliance_deadlines cd
                      where cd.bill_id=b.id and cd.deadline_date>=current_date) fut
            from bills b where b.id = any($1::int[]) order by tlen desc nulls last""",
            ids,
        )
    if bill_numbers:
        return await c.fetch(
            """
            select b.id, coalesce(b.region,'US') region, b.state, b.bill_number, b.title, b.source_url,
                   (select max(length(text)) from bill_texts where bill_id=b.id) tlen,
                   (select count(*) from compliance_deadlines cd
                      where cd.bill_id=b.id and cd.deadline_date>=current_date) fut
            from bills b where b.bill_number = any($1::text[]) order by tlen desc nulls last""",
            bill_numbers,
        )
    status_clause = "and b.status = $4" if status else ""
    params = [min_chars, max_future, limit]
    if status:
        params.append(status)
    return await c.fetch(
        f"""
        select b.id, coalesce(b.region,'US') region, b.state, b.bill_number, b.title, b.source_url,
               t.tlen,
               (select count(*) from compliance_deadlines cd
                  where cd.bill_id=b.id and cd.deadline_date>=current_date) fut
        from bills b
        join lateral (select max(length(text)) tlen from bill_texts where bill_id=b.id) t on true
        where b.ce_relevant is true and b.compliance_details is not null
          and t.tlen > $1
          and (select count(*) from compliance_deadlines cd
                 where cd.bill_id=b.id and cd.deadline_date>=current_date) <= $2
          {status_clause}
        order by t.tlen desc
        limit $3
        """,
        *params,
    )


async def _text(c, bill_id):
    return await c.fetchval(
        "select text from bill_texts where bill_id=$1 order by length(text) desc limit 1", bill_id)


async def _write_result(c, bill_id, extraction):
    """Overwrite compliance_details and rebuild region-tagged deadline rows for one bill. Returns
    (n_rows, n_future). Re-reads the bill's region/state/source_url so batch collect needs no state."""
    b = await c.fetchrow(
        "select coalesce(region,'US') region, state, bill_number, source_url from bills where id=$1", bill_id)
    if b is None:
        return 0, 0
    rows = _rows_for(extraction, b["bill_number"])
    n_future = sum(1 for _, d, _ in rows if d >= date.today())
    async with c.transaction():
        await c.execute(
            "update bills set compliance_details = cast($1 as jsonb), updated_at = now() where id = $2",
            json.dumps(extraction.raw_json), bill_id)
        await c.execute("delete from compliance_deadlines where bill_id=$1", bill_id)
        for dtype, ddate, desc in rows:
            await c.execute(
                "insert into compliance_deadlines "
                "(bill_id,state,deadline_type,deadline_date,description,source_url,region) "
                "values ($1,$2,$3,$4,$5,$6,$7)",
                bill_id, b["state"], dtype, ddate, desc, b["source_url"], b["region"])
    return len(rows), n_future


def _print_candidates(cands, cap, label):
    print(f"{len(cands)} candidate bills ({label})\n")
    for b in cands:
        _, how = _window("x" * (b["tlen"] or 0), cap)
        print(f"  [{b['region']:>3}] {b['bill_number'] or '?':<22} {b['tlen']:>8}c  fut={b['fut']:<2} "
              f"send={how:<9} {(b['title'] or '')[:48]}")


def _filter_label(args, bill_numbers):
    return (f"min_chars={args.min_chars}, max_future={args.max_future}, status={args.status or 'any'}, "
            f"{'explicit list' if bill_numbers else 'auto-filter'}, limit={args.limit}")


# ---------- run (synchronous, live) ----------
async def run(args):
    bill_numbers = [b.strip() for b in args.bills.split(",")] if args.bills else None
    ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    c = await _connect(args.dsn)
    try:
        cands = await _candidates(c, args.min_chars, args.max_future, bill_numbers, args.limit,
                                  args.status or None, ids)
        _print_candidates(cands, args.cap, _filter_label(args, bill_numbers or ids))
        if args.dry_run:
            print("\n(dry run — no API calls, no writes)")
            return
        client = anthropic.AsyncAnthropic(api_key=_api_key(), timeout=300.0, max_retries=2)
        extractor = SonnetExtractor(client=client)
        processed = failed = total_rows = future_rows = 0
        by_region = Counter()
        print()
        for i, b in enumerate(cands, 1):
            tag = f"[{b['region']}] {b['bill_number']}"
            text = await _text(c, b["id"])
            if not text:
                print(f"  [{i}/{len(cands)}] {tag}: no text, skip")
                continue
            windowed, how = _window(text, args.cap)
            try:
                extraction = await extractor.extract(
                    state=b["state"] or "", bill_number=b["bill_number"] or "", title=b["title"] or "",
                    full_text=windowed, region=b["region"], max_chars=len(windowed) + 1,
                    max_output_tokens=args.max_tokens)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  [{i}/{len(cands)}] {tag}: extract failed: {type(e).__name__}: {e}")
                continue
            if not extraction.raw_json:
                # Nothing parsed/salvaged — leave the bill's existing details+rows untouched.
                # (Writing here would DELETE its deadlines and blank compliance_details.)
                failed += 1
                print(f"  [{i}/{len(cands)}] {tag}: empty/parse-fail — left as-is (not written)")
                continue
            n_rows, n_future = await _write_result(c, b["id"], extraction)
            processed += 1
            total_rows += n_rows
            future_rows += n_future
            by_region[b["region"]] += n_rows
            print(f"  [{i}/{len(cands)}] {tag}: {n_rows} rows ({n_future} future)  [{how}]")
        print(f"\nDONE. processed {processed}/{len(cands)} ({failed} failed). "
              f"wrote {total_rows} deadline rows ({future_rows} future).")
        for reg, n in by_region.most_common():
            print(f"  {reg:>4} {n}")
    finally:
        await c.close()


# ---------- submit (enqueue a Message Batch) ----------
async def submit(args):
    bill_numbers = [b.strip() for b in args.bills.split(",")] if args.bills else None
    ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    c = await _connect(args.dsn)
    try:
        cands = await _candidates(c, args.min_chars, args.max_future, bill_numbers, args.limit,
                                  args.status or None, ids)
        _print_candidates(cands, args.cap, _filter_label(args, bill_numbers or ids))
        if not cands:
            print("\nno candidates — nothing to submit")
            return
        extractor = SonnetExtractor(model=SONNET_MODEL)  # build_params only; no live client needed
        reqs, skipped = [], 0
        for b in cands:
            text = await _text(c, b["id"])
            if not text:
                skipped += 1
                continue
            windowed, _how = _window(text, args.cap)
            params = extractor.build_params(
                b["state"] or "", b["bill_number"] or "", b["title"] or "",
                windowed, b["region"], max_chars=len(windowed) + 1, max_output_tokens=args.max_tokens)
            reqs.append(Request(custom_id=str(b["id"]),
                                params=MessageCreateParamsNonStreaming(**params)))
        if not reqs:
            print("\nno usable text on any candidate — nothing to submit")
            return
    finally:
        await c.close()

    client = anthropic.Anthropic(api_key=_api_key())
    batch = client.messages.batches.create(requests=reqs)
    os.makedirs(SCRATCH, exist_ok=True)
    state_path = args.state or os.path.join(SCRATCH, f"deadlines_batch_{int(len(reqs))}.json")
    Path(state_path).write_text(json.dumps(
        {"dsn": args.dsn, "batch_id": batch.id, "n": len(reqs), "phase": "batch"}, indent=2))
    print(f"\nsubmitted Message Batch {batch.id} over {len(reqs)} bills "
          f"({skipped} skipped — no text). 50% of live pricing.")
    print(f"state: {state_path}")
    print(f"next: ... reextract_deadlines_targeted.py collect --state {state_path}")


# ---------- collect (poll + write) ----------
def _poll(client, batch_id, wait_s):
    t0 = time.time()
    while True:
        b = client.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            return b
        rc = b.request_counts
        print(f"  {batch_id}: {b.processing_status} "
              f"(processing={rc.processing} succeeded={rc.succeeded} errored={rc.errored})", flush=True)
        if time.time() - t0 >= wait_s:
            return b
        time.sleep(min(15, wait_s))


async def collect(args):
    st = json.loads(Path(args.state).read_text())
    if st.get("phase") == "done":
        print("state phase is 'done' — nothing to collect.")
        return
    client = anthropic.Anthropic(api_key=_api_key())
    b = _poll(client, st["batch_id"], args.wait)
    if b.processing_status != "ended":
        print("batch still processing — re-run collect to resume.")
        return
    extractor = SonnetExtractor(model=SONNET_MODEL)  # parse only
    c = await _connect(st["dsn"])
    try:
        wrote = failed = total_rows = future_rows = 0
        by_region = Counter()
        for r in client.messages.batches.results(st["batch_id"]):
            bid = int(r.custom_id)
            if r.result.type != "succeeded":
                failed += 1
                print(f"  bill {bid}: {r.result.type}")
                continue
            text = next((blk.text for blk in r.result.message.content if blk.type == "text"), "")
            extraction = extractor.parse_response(text, bill_number=str(bid))
            if not extraction.raw_json:
                failed += 1
                print(f"  bill {bid}: empty/parse-fail (left for retry)")
                continue
            n_rows, n_future = await _write_result(c, bid, extraction)
            wrote += 1
            total_rows += n_rows
            future_rows += n_future
            reg = await c.fetchval("select coalesce(region,'US') from bills where id=$1", bid)
            by_region[reg] += n_rows
        st["phase"] = "done"
        Path(args.state).write_text(json.dumps(st, indent=2))
        print(f"\nDONE. wrote {wrote}/{st['n']} bills ({failed} failed/empty). "
              f"{total_rows} deadline rows ({future_rows} future).")
        for reg, n in by_region.most_common():
            print(f"  {reg:>4} {n}")
    finally:
        await c.close()


def _add_filters(p):
    p.add_argument("--dsn", required=True, help="Target DSN via the auth proxy (no password — use env PW).")
    p.add_argument("--min-chars", type=int, default=60000, help="Only bills whose text exceeds this.")
    p.add_argument("--max-future", type=int, default=1,
                   help="Only bills with at most this many FUTURE deadline rows today (under-extracted).")
    p.add_argument("--status", default="enacted", help="Bill status to target ('' = any). Default enacted.")
    p.add_argument("--bills", default=None, help="CSV of explicit bill_numbers (overrides the filters).")
    p.add_argument("--ids", default=None, help="CSV of explicit bill IDs (overrides everything). For retrying failures.")
    p.add_argument("--limit", type=int, default=200, help="Max bills to process.")
    p.add_argument("--cap", type=int, default=WHOLE_TEXT_CAP, help="Char budget before head+tail windowing.")
    p.add_argument("--max-tokens", type=int, default=16000,
                   help="Output token budget. Raise (e.g. 32000) for huge omnibus laws whose JSON truncates.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="synchronous live re-extraction")
    _add_filters(r)
    r.add_argument("--dry-run", action="store_true", help="List candidates + windowing; no API calls or writes.")
    s = sub.add_parser("submit", help="enqueue a Message Batch (50% cost)")
    _add_filters(s)
    s.add_argument("--state", default=None, help="Where to write the batch state file.")
    col = sub.add_parser("collect", help="poll the batch and write results")
    col.add_argument("--state", required=True)
    col.add_argument("--wait", type=int, default=90, help="seconds to poll before yielding (re-run to resume)")
    args = ap.parse_args()
    asyncio.run({"run": run, "submit": submit, "collect": collect}[args.cmd](args))


if __name__ == "__main__":
    main()
