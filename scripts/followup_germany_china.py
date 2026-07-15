"""Reproduce the founder's exact Germany→China thread through the real /ask handler (post-fix),
so we can read the turn-2 comparison answer that previously "broke the charm"."""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.api.auth import AuthedUser
from app.api.research import ask_the_bills
from app.database import AsyncSessionLocal
from app.schemas import ResearchAskRequest

USER = AuthedUser(uid="fix-test-germany-china", email="t@t.local", email_verified=True)

async def ask(q, sid=None):
    async with AsyncSessionLocal() as db:
        return await ask_the_bills(ResearchAskRequest(question=q, session_id=sid), USER, db)

async def main():
    r1 = await ask("What can other regions learn from Germany's circularity legislation?")
    print("── TURN 1 ──  total=%s strategy=%s" % (r1.bills.total, r1.bills.strategy))
    print(r1.answer[:400].strip(), "\n")
    r2 = await ask("How does this compare to china's approach?", sid=r1.session_id)
    print("── TURN 2 ──  total=%s strategy=%s  rq=%r" % (r2.bills.total, r2.bills.strategy, r2.retrieval_query))
    print(r2.answer[:700].strip())

if __name__ == "__main__":
    asyncio.run(main())
