"""Classify the producer-responsibility MANAGEMENT MODEL of enacted EPR laws.

Answers "is this law run by a collective PRO, by individual producers, or by a
government body" — the structured dimension SignalScout was missing (the old
compliance_details only had a free-text `pro_requirements` blurb, on 19/180 laws).

Discovery (scripts run 2026-06-15) found these statutory models actually occur:
  pro_collective   producers must JOIN or FORM a single stewardship org / PRO
  pro_multiple     statute explicitly allows MORE THAN ONE competing PRO
  individual       individual producer responsibility: each producer files/operates
                   its own plan, OR may self-implement instead of joining a PRO
  government_run   a state agency or government-owned enterprise administers it
  market_contract  no PRO; obligation met via private contracts (e.g. retailer hires
                   a permitted hauler) — the SC waste-tire pattern
  not_specified    fee / study / amendment with no management structure

"Regional" is intentionally NOT a model value — in US EPR it's an operational fact
(one PRO serving many states), captured separately as coordination_scope when the
statute mentions multistate/reciprocal coordination.

Result is merged into bills.compliance_details under the "management" key (no clobber
of existing extraction). Run --test to print without writing.

Usage:
  venv/Scripts/python scripts/extract_management_model.py --test --limit 10
  venv/Scripts/python scripts/extract_management_model.py --limit 200          # full backfill
  venv/Scripts/python scripts/extract_management_model.py --prod-dsn "..."     # run against prod
"""
import argparse
import asyncio
import json

import anthropic
from sqlalchemy import create_engine, text

from app.config import settings
from app.ingestion.openstates import OpenStatesClient

MODEL = "claude-sonnet-4-6"

# Below this many characters the fetched page is a stub/summary/JS-shell, not statutory
# text — the model would emit a confident but baseless not_specified (see RI S0996 in
# testing). Record management_model="unknown" instead so thin text never undercounts PROs.
MIN_CHARS = 1500

ENUM = [
    "pro_collective", "pro_multiple", "individual",
    "government_run", "market_contract", "not_specified",
    "unknown",  # text too thin to judge — not a real classification, a known-unknown
]

SYSTEM = (
    "You are an EPR compliance analyst. You classify HOW a producer-responsibility "
    "program is administered, based strictly on the bill text. Be conservative: if the "
    "text does not establish a management structure, say not_specified."
)

PROMPT = """Classify the MANAGEMENT MODEL of this enacted law from its text.

State: {state}
Bill: {bill_number}
Title: {title}

Text (may be truncated):
{full_text}

Choose ONE management_model from this controlled list:
- pro_collective  : producers must JOIN or FORM a single stewardship organization / PRO that runs the program
- pro_multiple    : the statute explicitly allows MORE THAN ONE competing PRO (often with a coordinating body)
- individual      : individual producer responsibility — each producer files/operates its OWN plan, or may self-implement instead of joining a PRO
- government_run  : a government agency or government-owned enterprise administers the program directly
- market_contract : NO PRO; the obligation is met through private market contracts (e.g. a retailer contracts a permitted hauler)
- not_specified   : a fee / study / amendment / preemption bill that establishes no management structure

Respond with ONLY valid JSON, no prose:
{{
  "management_model": "<one of the list>",
  "individual_option": <true|false>,   // true if an individual-compliance alternative is offered ALONGSIDE a PRO
  "coordination_scope": "<single_state|multistate|national|unspecified>",  // only multistate/national if the text mentions regional reciprocity or a multi-state program
  "evidence": "<short verbatim quote from the text that justifies the model; empty string if not_specified>",
  "confidence": <0.0-1.0>
}}"""


async def get_text(os_client, osid, source_url):
    """Prefer real OpenStates text; for hist:/null ids fall back to the source_url
    document (state bill page, agency program page, or PRO website)."""
    if osid and not osid.startswith("hist:"):
        try:
            t = await os_client.get_bill_text(osid)
            if t:
                return t, "openstates"
        except Exception:  # noqa: BLE001
            pass
    if source_url:
        try:
            t = await os_client.get_text_from_source(source_url)
            if t:
                return t, "source_url"
        except Exception:  # noqa: BLE001
            pass
    return "", "none"


async def classify(client, os_client, row):
    bid, state, bill_number, title, osid, source_url = row
    full_text, text_source = await get_text(os_client, osid, source_url)
    if len(full_text) < MIN_CHARS:
        return {"management_model": "unknown", "individual_option": False,
                "coordination_scope": "unspecified", "evidence": "",
                "confidence": 0.0, "_text_chars": len(full_text),
                "_text_source": text_source if full_text else "none"}
    resp = await client.messages.create(
        model=MODEL, max_tokens=600, temperature=0, system=SYSTEM,
        messages=[{"role": "user", "content": PROMPT.format(
            state=state, bill_number=bill_number or "?", title=title or "",
            full_text=full_text[:14000])}],
    )
    raw = resp.content[0].text.strip()
    res = _parse_json(raw)
    res["_text_source"] = text_source
    return res


def _parse_json(raw: str) -> dict:
    """Tolerant JSON parse: full string, then the first balanced object via raw_decode
    (handles trailing prose / extra data the model sometimes appends). Never raises."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    if start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[start:])
            return obj
        except json.JSONDecodeError:
            pass
    return {"management_model": "unknown", "_parse_failed": True, "confidence": 0.0,
            "individual_option": False, "coordination_scope": "unspecified", "evidence": ""}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="print only, no DB writes")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--only-missing", action="store_true",
                    help="skip laws that already have compliance_details.management")
    ap.add_argument("--prod-dsn", default=None)
    args = ap.parse_args()

    dsn = args.prod_dsn or settings.database_url
    engine = create_engine(dsn)

    where = "epr_relevant and state!='US' and status='enacted'"
    if args.only_missing:
        where += " and (compliance_details->'management') is null"
    order = "random()"
    sql = (f"select id, state, bill_number, title, openstates_id, source_url from bills "
           f"where {where} order by {order} limit :lim")

    with engine.connect() as c:
        rows = list(c.execute(text(sql), {"lim": args.limit}))
    print(f"Classifying {len(rows)} enacted laws (model={MODEL}, test={args.test})\n")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key,
                                      timeout=90.0, max_retries=1)
    tally = {}
    for bid, state, bn, title, osid, surl in rows:
        print(f"  [{bid}] {state} {bn} — {(title or '')[:55]}", flush=True)
        try:
            async with OpenStatesClient() as os_client:
                res = await classify(client, os_client, (bid, state, bn, title, osid, surl))
        except Exception as ex:  # noqa: BLE001
            print(f"      !! error: {str(ex)[:80]}", flush=True)
            res = {"management_model": "unknown", "_error": str(ex)[:120],
                   "confidence": 0.0, "individual_option": False,
                   "coordination_scope": "unspecified", "evidence": ""}
        mm = res.get("management_model", "?")
        tally[mm] = tally.get(mm, 0) + 1
        flag = f" [thin text: {res.get('_text_chars')} chars]" if mm == "unknown" else ""
        print(f"      -> {mm}  (indiv_option={res.get('individual_option')}, "
              f"scope={res.get('coordination_scope')}, conf={res.get('confidence')}, "
              f"src={res.get('_text_source')}){flag}")
        ev = (res.get("evidence") or "").strip()
        if ev:
            print(f"         \"{ev[:140]}\"")
        if not args.test:
            with engine.begin() as c:
                c.execute(text(
                    "update bills set compliance_details = "
                    "coalesce(compliance_details, '{}'::jsonb) || "
                    "jsonb_build_object('management', cast(:m as jsonb)) "
                    "where id = :bid"),
                    {"m": json.dumps(res), "bid": bid})
        print()

    print("TALLY:")
    for k, v in sorted(tally.items(), key=lambda x: -x[1]):
        print(f"  {v:3d}  {k}")


if __name__ == "__main__":
    asyncio.run(main())
