"""Accuracy pass over management_model, using two HIGH-PRECISION signals the first
backfill (extract_management_model.py) couldn't see, because it relied on whatever a
bill's source_url happened to return — often a chapter index or program summary that
omitted the PRO clause, yielding confident-but-wrong not_specified labels.

Signal A — clean pro_requirements text. 19 enacted laws already carry a Sonnet-extracted
  `pro_requirements` blurb (a precise description of the stewardship/PRO structure). When
  present, re-classify FROM THAT TEXT instead of the web fetch — it's the cleanest evidence
  we have. This fixes WA SB-5284, MN HF-3911, NY S-5027C, ME LD-474, VT H-67, SC S-171…

Signal B — known PRO-org domains. A law whose source_url lives on a national stewardship
  org's site (PaintCare, Mattress Recycling Council, Call2Recycle, Thermostat Recycling
  Corp, …) is collective-PRO-run by definition. For laws still not_specified/unknown after
  Signal A, set pro_collective + multistate, basis="pro_domain".

Each correction stamps compliance_details.management with `_corrected` + `_basis` so it's
auditable and distinguishable from the first-pass extraction.

Usage:
  venv/Scripts/python scripts/correct_management_model.py --test
  venv/Scripts/python scripts/correct_management_model.py
"""
import argparse
import asyncio
import json

import anthropic
from sqlalchemy import create_engine, text

from app.config import settings

MODEL = "claude-sonnet-4-6"

PRO_DOMAINS = {
    "paintcare.org": "PaintCare",
    "mattressrecyclingcouncil.org": "Mattress Recycling Council",
    "thermostat-recycle.org": "Thermostat Recycling Corp",
    "batterynetwork.org": "Call2Recycle",
    "call2recycle": "Call2Recycle",
    "elvsolutions.org": "ELVS (mercury switch)",
    "lamprecycle.org": "lamp recycling PRO",
}

SYSTEM = ("You are an EPR compliance analyst. From a short description of a program's "
          "stewardship/PRO structure, classify how the program is administered.")

PROMPT = """Classify the MANAGEMENT MODEL from this description of an enacted EPR law's
producer-responsibility structure.

State: {state}   Bill: {bill_number}
Structure description (already extracted from the statute):
{blurb}

Choose ONE management_model:
- pro_collective  : producers must JOIN or FORM a single stewardship organization / PRO
- pro_multiple    : MORE THAN ONE competing PRO is allowed (often a coordinating body)
- individual      : individual producer responsibility — each producer runs its own plan
- government_run  : a government agency or government-owned enterprise administers it
- market_contract : NO PRO; obligation met via private contracts (e.g. retailer hires a hauler)
- not_specified   : the description establishes no management structure

Respond ONLY with JSON:
{{"management_model":"<one>","individual_option":<bool>,"coordination_scope":"<single_state|multistate|national|unspecified>","evidence":"<short quote>","confidence":<0-1>}}"""


def parse_json(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        s = raw.find("{")
        if s != -1:
            try:
                return json.JSONDecoder().raw_decode(raw[s:])[0]
            except json.JSONDecodeError:
                pass
    return {"management_model": "unknown", "confidence": 0.0}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--prod-dsn", default=None)
    args = ap.parse_args()
    engine = create_engine(args.prod_dsn or settings.database_url)
    base = "ce_relevant and state!='US' and status='enacted'"
    mm = "compliance_details->'management'->>'management_model'"
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key,
                                      timeout=90.0, max_retries=1)

    def write(bid, res):
        if args.test:
            return
        with engine.begin() as c:
            c.execute(text(
                "update bills set compliance_details = "
                "coalesce(compliance_details,'{}'::jsonb) || "
                "jsonb_build_object('management', cast(:m as jsonb)) where id=:bid"),
                {"m": json.dumps(res), "bid": bid})

    # --- Signal A: re-classify from clean pro_requirements text ---
    with engine.connect() as c:
        rows = list(c.execute(text(f"""
            select id,state,bill_number,
                   compliance_details->>'pro_requirements'
            from bills where {base}
              and compliance_details->>'pro_requirements' is not null
              and length(compliance_details->>'pro_requirements')>40""")))
    print(f"== Signal A: re-classify {len(rows)} laws from pro_requirements ==")
    for bid, st, bn, blurb in rows:
        resp = await client.messages.create(
            model=MODEL, max_tokens=400, temperature=0, system=SYSTEM,
            messages=[{"role": "user", "content": PROMPT.format(
                state=st, bill_number=bn or "?", blurb=blurb[:4000])}])
        res = parse_json(resp.content[0].text.strip())
        res["_corrected"] = True
        res["_basis"] = "pro_requirements_text"
        print(f"  {st} {bn:14s} -> {res.get('management_model'):14s} "
              f"(scope={res.get('coordination_scope')}, conf={res.get('confidence')})")
        write(bid, res)

    # --- Signal B: domain heuristic for still-unresolved laws ---
    like = " or ".join([f"source_url ilike '%{d}%'" for d in PRO_DOMAINS])
    with engine.connect() as c:
        rows = list(c.execute(text(f"""
            select id,state,bill_number,source_url from bills where {base}
              and {mm} in ('not_specified','unknown') and ({like})""")))
    print(f"\n== Signal B: domain heuristic for {len(rows)} PRO-site laws ==")
    for bid, st, bn, surl in rows:
        org = next((v for k, v in PRO_DOMAINS.items() if k in (surl or "").lower()), "PRO")
        res = {"management_model": "pro_collective", "individual_option": False,
               "coordination_scope": "multistate", "confidence": 0.9,
               "evidence": f"Program administered by {org} (national stewardship org).",
               "_corrected": True, "_basis": "pro_domain"}
        print(f"  {st} {bn:14s} -> pro_collective  ({org})")
        write(bid, res)

    print("\n(test mode — no writes)" if args.test else "\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
