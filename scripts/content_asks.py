"""Content-lane asks: run a fixed list of PUBLISHABLE questions through the REAL Ask-the-Atlas
handler in-process, persisting each as its own research_session/turn under the given owner uid so
they land in My Library + the /admin/research log, ready for thread-draft / Friday-Fact distill.

Same pattern as scripts/corpus_survey_ask.py (which stays the corpus-INVENTORY list). The questions
here are written for publication: each asks for NAMED laws, jurisdictions and dates rather than
corpus counts, because count-based answers disagree run-to-run and can't be fact-checked later.

Lanes: (2) the mirror — what the US lacks; (3) the compliance calendar; (4) design cost / conflict.
Lane 1 (real-world outcomes) is deliberately ABSENT — ask_the_atlas does not read the bill_outcome
table, so those posts are written from that table directly, not from an ask.

Run against PROD via the Cloud SQL proxy (127.0.0.1:5436):

    PW=$(gcloud secrets versions access latest --secret=SIGNALSCOUT_DB_PASSWORD --project=ce-bill-tracker)
    AK=$(gcloud secrets versions access latest --secret=ANTHROPIC_API_KEY --project=ce-bill-tracker)
    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
    DATABASE_URL="postgresql://signalscout:$PW@127.0.0.1:5436/signalscout" ANTHROPIC_API_KEY="$AK" \
        venv/Scripts/python.exe scripts/content_asks.py
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
PROGRESS = Path(__file__).parent.parent / "data" / "exports" / "content_asks_progress.jsonl"

QUESTIONS = [
    # Lane 2 — the mirror: what the US doesn't have. Phrased with US-foil contrast cues so
    # resolve_facets demotes "United States" to a reference label instead of scoping to it.
    "Which policy instruments appear in enacted law in five or more foreign countries but in no US state? Name the instrument, the countries, and one example law for each.",
    "Name foreign laws that regulate a product category no US state regulates, and describe what each one actually requires of producers.",
    "Where has a foreign jurisdiction already revised or tightened a circular-economy law that US states are now introducing in its original, weaker form?",
    # Lane 3 — the compliance calendar.
    "Which enacted laws have compliance obligations that bind within the next 12 months? For each, name the law, the date, and the specific obligation.",
    "Which enacted packaging laws impose producer obligations but name no producer responsibility organization or plan-filing pathway yet?",
    "Which enacted laws impose a compliance obligation with no stated deadline at all? Name the law and the obligation that was left undated.",
    "Among laws with deadlines in the next 24 months, which impose the earliest producer registration or first-fee milestone, and what does a producer have to do first?",
    # Lane 4 — design cost and cross-jurisdiction conflict.
    "Which single packaging format or material is banned, taxed, or fee-differentiated in the greatest number of distinct jurisdictions? Name each jurisdiction and what it does to that format.",
    "Where do two jurisdictions treat the same product or material in contradictory ways, so that a design compliant in one is non-compliant in the other? Name both laws and the conflict.",
    "Which recycled-content requirements conflict in threshold or measurement basis between jurisdictions covering the same product?",
    "Which materials are promoted as substitutes by one jurisdiction while being restricted or discouraged by another? Name the laws on both sides.",
    "Across enacted eco-modulation schemes worldwide, which specific design attributes are rewarded with lower fees and which are penalized? Name the jurisdiction and the attribute.",
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
