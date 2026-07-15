"""End-to-end smoke test for research follow-up threading — drives the real /ask handler in-process
(no HTTP/auth) for a 2-turn conversation, then reads the session back.

Turn 1 (no session): "what can the rest of the regions learn from the Chinese bills?"
Turn 2 (session_id):  "what about Japan?"   -> must rewrite to a standalone Japan query, scope to JP,
                                              and persist as seq 2 in the SAME session.

    DATABASE_URL=postgresql+asyncpg://signalscout:PW@127.0.0.1:5434/signalscout \
    ANTHROPIC_API_KEY=... venv/Scripts/python.exe scripts/followup_smoke.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.auth import AuthedUser  # noqa: E402
from app.api.research import ask_the_bills, research_session, _rewrite_followup  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.schemas import ResearchAskRequest  # noqa: E402

USER = AuthedUser(uid="smoke-followup-test", email="smoke@test.local", email_verified=True)


async def ask(question, session_id=None):
    async with AsyncSessionLocal() as db:
        return await ask_the_bills(ResearchAskRequest(question=question, session_id=session_id), USER, db)


async def main():
    print("── TURN 1 (new session) ─────────────────────────────────────────")
    r1 = await ask("what can the rest of the regions learn from the Chinese bills?")
    print(f"  session_id={r1.session_id}  seq={r1.seq}")
    print(f"  bills.total={r1.bills.total}  strategy={r1.bills.strategy}")
    print(f"  answer[:180]: {r1.answer[:180].strip()}")

    # Peek at what the rewrite alone produces for the follow-up (visibility)
    hist = [{"question": "what can the rest of the regions learn from the Chinese bills?", "answer": r1.answer}]
    rq = await _rewrite_followup(hist, "what about Japan?")
    print(f"\n  [rewrite] 'what about Japan?' -> {rq!r}")

    print("\n── TURN 2 (follow-up, same session) ─────────────────────────────")
    r2 = await ask("what about Japan?", session_id=r1.session_id)
    print(f"  session_id={r2.session_id}  seq={r2.seq}  (same session: {r2.session_id == r1.session_id})")
    print(f"  retrieval_query={r2.retrieval_query!r}")
    print(f"  bills.total={r2.bills.total}  strategy={r2.bills.strategy}")
    print(f"  answer[:180]: {r2.answer[:180].strip()}")

    print("\n── SESSION READBACK ─────────────────────────────────────────────")
    async with AsyncSessionLocal() as db:
        sess = await research_session(r1.session_id, USER, db)
    print(f"  title={sess.title!r}")
    for t in sess.turns:
        print(f"   seq {t.seq}: q={t.question!r}  rq={t.retrieval_query!r}  total={t.bill_total}")


if __name__ == "__main__":
    asyncio.run(main())
