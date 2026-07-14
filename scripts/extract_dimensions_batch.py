"""Backfill the v5 compliance dimensions across the corpus using the Anthropic Message Batches API
(50% of live pricing, async). Two-phase Haiku-triage hybrid (see docs/DIMENSION_EXPANSION_PLAN.md 2a):

  Phase 1 — a Haiku batch over ALL candidates ("does this bill carry any dimension?").
  Phase 2 — a Sonnet batch over only the bills Haiku flagged (or that Haiku failed to parse).
            Bills Haiku found empty are written directly from the Haiku result (triage=haiku_only).

Resumable. State lives in a JSON file; run `submit` once, then `collect` repeatedly until it prints
DONE. Each `collect` polls the current batch briefly and, when it has ended, writes results and submits
the next phase — so a batch that takes minutes-to-hours doesn't pin a single process.

    # 1) submit the Haiku triage batch (fast — returns a batch id)
    venv/Scripts/python.exe scripts/extract_dimensions_batch.py submit \
        --dsn postgresql://postgres:dev@localhost:5432/signalscout --region FR

    # 2) run collect until it says DONE (each call advances the pipeline)
    venv/Scripts/python.exe scripts/extract_dimensions_batch.py collect --state <path printed by submit>

DSN targets: non-English rows live locally (extract local → push to dev with --with-compliance-details);
US full text is prod-only, so run US against prod via the Cloud SQL proxy.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic  # noqa: E402
import asyncpg  # noqa: E402
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming  # noqa: E402
from anthropic.types.messages.batch_create_params import Request  # noqa: E402

from app.classification.sonnet_extractor import (  # noqa: E402
    EXTRACTION_VERSION, SONNET_MODEL, SonnetExtractor,
)
from app.config import settings  # noqa: E402

HAIKU_MODEL = "claude-haiku-4-5-20251001"
ENVELOPES = ("eco_modulation", "recycled_content", "penalties", "collection_targets",
             "pro_structure", "bans_restrictions", "fee_amounts", "labeling",
             "repairability", "reuse_refill", "digital_product_passport", "remanufacturing")
SCRATCH = os.environ.get("CLAUDE_SCRATCH", str(Path(__file__).parent.parent / ".batch_state"))


def _pg(dsn: str) -> str:
    return re.sub(r"^postgres(ql)?(\+asyncpg)?://", "postgresql://", dsn)


def _any_present(res) -> bool:
    return any((getattr(res, e) or {}).get("status") == "present" for e in ENVELOPES)


async def _candidates(conn, regions, limit):
    clauses = ["b.ce_relevant = true", "bt.text IS NOT NULL",
               "COALESCE((b.compliance_details->>'extraction_version')::int, 0) < $1"]
    params = [EXTRACTION_VERSION]
    if regions:
        clauses.append("b.region = ANY($2)")
        params.append(regions)
    sql = (f"SELECT b.id, b.region, b.state, b.bill_number, b.title, bt.text AS full_text "
           f"FROM bills b JOIN bill_texts bt ON bt.bill_id = b.id WHERE {' AND '.join(clauses)} "
           f"ORDER BY b.status_date DESC NULLS LAST LIMIT {int(limit)}")
    return await conn.fetch(sql, *params)


async def _fetch_by_ids(conn, ids):
    rows = await conn.fetch(
        "SELECT b.id, b.region, b.state, b.bill_number, b.title, bt.text AS full_text "
        "FROM bills b JOIN bill_texts bt ON bt.bill_id = b.id WHERE b.id = ANY($1)", ids)
    return {r["id"]: r for r in rows}


def _build_batch(rows, model):
    ex = SonnetExtractor(model=model)
    reqs = []
    for r in rows:
        params = ex.build_params(r["state"], r["bill_number"] or "", r["title"] or "",
                                 r["full_text"], r["region"])
        reqs.append(Request(custom_id=str(r["id"]),
                            params=MessageCreateParamsNonStreaming(**params)))
    return reqs


async def _write(conn, bill_id, res, source):
    cd = await conn.fetchval("SELECT compliance_details FROM bills WHERE id=$1", bill_id)
    cd = json.loads(cd) if isinstance(cd, str) else (cd or {})
    for e in ENVELOPES:
        cd[e] = getattr(res, e) or {}
    cd["extraction_version"] = EXTRACTION_VERSION
    cd["extraction_triage"] = source  # sonnet_escalated | haiku_only
    await conn.execute("UPDATE bills SET compliance_details = CAST($1 AS jsonb), updated_at = now() "
                       "WHERE id = $2", json.dumps(cd, ensure_ascii=False), bill_id)


def _client():
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _load_state(path):
    return json.loads(Path(path).read_text())


def _save_state(path, st):
    Path(path).write_text(json.dumps(st, indent=2))


# ---------- submit ----------
async def submit(args):
    dsn = _pg(args.dsn)
    regions = [r.strip().upper() for r in (args.region or "").split(",") if r.strip()] or None
    conn = await asyncpg.connect(dsn)
    rows = await _candidates(conn, regions, args.limit)
    await conn.close()
    if not rows:
        print("no candidates below v{} — nothing to do".format(EXTRACTION_VERSION))
        return
    batch = _client().messages.batches.create(requests=_build_batch(rows, HAIKU_MODEL))
    os.makedirs(SCRATCH, exist_ok=True)
    tag = (args.region or "all").replace(",", "_")
    state_path = args.state or os.path.join(SCRATCH, f"dims_batch_{tag}.json")
    _save_state(state_path, {
        "dsn": dsn, "regions": regions, "phase": "haiku",
        "haiku_batch_id": batch.id, "haiku_written": False,
        "sonnet_batch_id": None, "escalated_ids": None,
        "n_candidates": len(rows),
    })
    print(f"submitted Haiku triage batch {batch.id} over {len(rows)} bills")
    print(f"state: {state_path}")
    print(f"next: venv/Scripts/python.exe scripts/extract_dimensions_batch.py collect --state {state_path}")


def _poll(client, batch_id, wait_s):
    """Poll until ended or wait_s elapses. Returns the batch (ended or not)."""
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


# ---------- collect ----------
async def collect(args):
    st = _load_state(args.state)
    client = _client()
    conn = await asyncpg.connect(st["dsn"])
    try:
        if st["phase"] == "haiku":
            b = _poll(client, st["haiku_batch_id"], args.wait)
            if b.processing_status != "ended":
                print("Haiku batch still processing — re-run collect to resume.")
                return
            ex = SonnetExtractor(model=HAIKU_MODEL)
            escalate, wrote_empty, parse_fail = [], 0, 0
            for r in client.messages.batches.results(st["haiku_batch_id"]):
                bid = int(r.custom_id)
                if r.result.type != "succeeded":
                    escalate.append(bid); continue  # errored/expired → let Sonnet do it
                text = next((c.text for c in r.result.message.content if c.type == "text"), "")
                res = ex.parse_response(text, bill_number=str(bid))
                if not res.raw_json:
                    parse_fail += 1; escalate.append(bid); continue
                if _any_present(res):
                    escalate.append(bid)
                else:
                    await _write(conn, bid, res, "haiku_only"); wrote_empty += 1
            print(f"Haiku triage: {wrote_empty} empty (written), {len(escalate)} escalate "
                  f"({parse_fail} parse-fail escalated)")
            st.update(phase="sonnet", haiku_written=True, escalated_ids=escalate)
            if not escalate:
                st["phase"] = "done"; _save_state(args.state, st); print("DONE (nothing to escalate)"); return
            rows = list((await _fetch_by_ids(conn, escalate)).values())
            sb = client.messages.batches.create(requests=_build_batch(rows, SONNET_MODEL))
            st["sonnet_batch_id"] = sb.id
            _save_state(args.state, st)
            print(f"submitted Sonnet batch {sb.id} over {len(rows)} escalated bills — re-run collect.")
            return

        if st["phase"] == "sonnet":
            b = _poll(client, st["sonnet_batch_id"], args.wait)
            if b.processing_status != "ended":
                print("Sonnet batch still processing — re-run collect to resume.")
                return
            ex = SonnetExtractor(model=SONNET_MODEL)
            wrote = fail = 0
            for r in client.messages.batches.results(st["sonnet_batch_id"]):
                bid = int(r.custom_id)
                if r.result.type != "succeeded":
                    fail += 1; continue
                text = next((c.text for c in r.result.message.content if c.type == "text"), "")
                res = ex.parse_response(text, bill_number=str(bid))
                if not res.raw_json:
                    fail += 1; continue  # left below-version for a future re-run
                await _write(conn, bid, res, "sonnet_escalated"); wrote += 1
            st["phase"] = "done"; _save_state(args.state, st)
            print(f"Sonnet batch written: {wrote} bills ({fail} failed/empty, left for retry)")
            print("DONE")
            return

        print("state phase is 'done' — nothing to collect.")
    finally:
        await conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit"); s.add_argument("--dsn", required=True)
    s.add_argument("--region", default=None); s.add_argument("--limit", type=int, default=5000)
    s.add_argument("--state", default=None)
    c = sub.add_parser("collect"); c.add_argument("--state", required=True)
    c.add_argument("--wait", type=int, default=90, help="seconds to poll before yielding (re-run to resume)")
    args = ap.parse_args()
    asyncio.run(submit(args) if args.cmd == "submit" else collect(args))


if __name__ == "__main__":
    main()
