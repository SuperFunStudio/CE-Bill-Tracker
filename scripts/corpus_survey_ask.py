"""One-off: run a fixed list of corpus-survey questions through the REAL Ask-the-Atlas handler
(app.api.research.ask_the_atlas) in-process, persisting each as its own research_session/turn under
the given owner uid so they show up in My Library + the admin research log.

Each question is a NEW session (no session_id) so it's asked VERBATIM — no follow-up query-rewrite.

Run against PROD via the Cloud SQL proxy (127.0.0.1:5436):

    PW=$(gcloud secrets versions access latest --secret=SIGNALSCOUT_DB_PASSWORD --project=ce-bill-tracker)
    AK=$(gcloud secrets versions access latest --secret=ANTHROPIC_API_KEY --project=ce-bill-tracker)
    DATABASE_URL="postgresql://signalscout:$PW@127.0.0.1:5436/signalscout" ANTHROPIC_API_KEY="$AK" \
        venv/Scripts/python.exe scripts/corpus_survey_ask.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.research import ask_the_atlas, _AskAccess  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.schemas import ResearchAskRequest  # noqa: E402

OWNER_UID = "L8BeKGapUcPfK9IydeE2gu2kV7z2"  # kenny@superfun.studio
CONCURRENCY = 3
PROGRESS = Path(__file__).parent.parent / "data" / "exports" / "corpus_survey_progress.jsonl"

QUESTIONS = [
    # Trends over time
    "How has the annual volume of enacted vs. introduced EPR measures changed year over year, and where is the inflection point?",
    "Which instrument types are accelerating between 2023 and 2026, and which are flat or declining?",
    "What is the average lag between a policy first appearing (introduced) and its first enactment, broken down by material category?",
    "Which materials moved from zero enacted laws to having an enacted regime during the corpus window, and when?",
    "Is eco-modulation (fee differentiation) showing up in more recent bills than older ones — is it the leading edge of policy design?",
    # Jurisdictional comparison & diffusion
    "Which US states are policy originators versus followers — who enacts EPR laws first and who adopts similar laws later?",
    "For packaging EPR specifically, rank jurisdictions by regime maturity, comparing US states and foreign countries side by side.",
    "Which foreign countries have enacted circular-economy laws with no US analog — what policy approaches are we missing domestically?",
    "Where does the EU lead the US by the widest margin across material and instrument, and where does the US lead the EU?",
    "Which sub-national jurisdictions (US states or foreign provinces) punch above their country's baseline on circular-economy law?",
    # Instrument & policy design
    "What is the distribution of management model (PRO, individual producer, government-run) across enacted laws, and does it correlate with material?",
    "Among enacted laws, how many actually specify penalties or enforcement mechanisms versus leaving enforcement vague?",
    "Which bills combine multiple instruments (for example an EPR fee plus a disposal ban plus a recycled-content mandate), and are combined-instrument laws growing?",
    "What recycled-content thresholds appear across the corpus, by material, and are jurisdictions converging on common percentages?",
    "What kinds of bills are still sitting in the 'other' instrument-type bucket, and what emergent policy clusters deserve to be promoted into named instruments?",
    # Material coverage
    "Which materials have the deepest regulatory regime (many enacted laws with rich compliance detail) versus being named but bare?",
    "For batteries and electronics specifically, which jurisdictions have covered-product-level detail versus blanket coverage?",
    "How much of the corpus touches biomaterials, organics, and regenerative agriculture, and is that scope actually filling in or still thin?",
    "Which materials appear almost exclusively in foreign law and are underrepresented in US legislation?",
    "Where do covered-product taxonomies conflict across jurisdictions — the same product categorized differently in different places?",
    # Compliance mechanics
    "Which enacted laws have concrete upcoming compliance deadlines in the next 12 to 24 months, sorted by date?",
    "For each major enacted packaging law, is there a named producer responsibility organization or plan-filing pathway, or is the compliance path still a gap?",
    "Which laws impose compliance obligations but have no extractable deadline — the silent-deadline gap?",
    "Across the corpus, what is the typical sequence and timing from a law being enacted to a PRO being stood up to producer registration to first fees?",
    # Outcomes & real-world impact
    "Which enacted laws have a recorded real-world outcome, and what measurable results (tonnage, recovery rate, fees collected) exist versus are missing?",
    "Of laws enacted three or more years ago, how many have any documented downstream effect, and what is the evidence-gap rate?",
    "Are there laws that were enacted but effectively stalled in implementation — no PRO, no fees, on paper only?",
    # Gaps, outliers & data quality
    "Where is the corpus most incomplete — which combinations of jurisdiction and material are empty that should plausibly have law?",
    "What are the most unique or unusual types of circular-economy bills in the corpus — the genuine outliers?",
    "What share of foreign bills still have year-only or missing status dates, and which source adapters are the worst offenders?",
]


def _log(rec: dict):
    line = json.dumps(rec, ensure_ascii=False)
    print(line, flush=True)
    with PROGRESS.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


async def ask_one(i: int, q: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        t0 = time.monotonic()
        try:
            async with AsyncSessionLocal() as db:
                resp = await ask_the_atlas(
                    None,
                    ResearchAskRequest(question=q),
                    _AskAccess(uid=OWNER_UID, is_member=True),
                    db,
                )
            rec = {
                "i": i, "ok": True, "q": q,
                "session_id": resp.session_id, "seq": resp.seq,
                "total": resp.bills.total if resp.bills else None,
                "strategy": resp.bills.strategy if resp.bills else None,
                "citations": len(resp.citations or []),
                "answer_chars": len(resp.answer or ""),
                "secs": round(time.monotonic() - t0, 1),
            }
        except Exception as e:  # noqa: BLE001
            rec = {"i": i, "ok": False, "q": q, "error": f"{type(e).__name__}: {e}",
                   "secs": round(time.monotonic() - t0, 1)}
        _log(rec)
        return rec


async def main():
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text("", encoding="utf-8")
    _log({"event": "start", "n": len(QUESTIONS), "owner_uid": OWNER_UID, "concurrency": CONCURRENCY})
    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(ask_one(i, q, sem) for i, q in enumerate(QUESTIONS, 1)))
    ok = [r for r in results if r.get("ok")]
    bad = [r for r in results if not r.get("ok")]
    _log({"event": "done", "ok": len(ok), "failed": len(bad),
          "session_ids": [r["session_id"] for r in ok]})
    if bad:
        _log({"event": "failures", "items": bad})


if __name__ == "__main__":
    asyncio.run(main())
