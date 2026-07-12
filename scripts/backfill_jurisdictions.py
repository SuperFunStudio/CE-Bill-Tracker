"""Seed the Atlas Circular jurisdiction tree and map every bill to its node. Idempotent — safe to
re-run (upserts nodes by code, recomputes bills.jurisdiction_id + bill_count from scratch).

Run against the target DB via its DATABASE_URL (prod through the Cloud SQL proxy, e.g.):
    DATABASE_URL=postgresql://signalscout:PW@127.0.0.1:15432/signalscout \
        venv/Scripts/python.exe scripts/backfill_jurisdictions.py

Reads the tree + (region,state)->code mapping from app/geo/jurisdictions.py so it never drifts from
the resolver the engine uses. Requires migration 036 applied first.
"""
import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import bindparam, func, select, text, update  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models import Bill, Jurisdiction  # noqa: E402
from app.geo.jurisdictions import jurisdiction_code, seed_nodes  # noqa: E402


async def seed_tree(db) -> dict[str, int]:
    """Upsert every seed node; return {code: id}. Parents are set in a second pass."""
    nodes = seed_nodes()
    existing = {j.code: j for j in (await db.execute(select(Jurisdiction))).scalars()}
    code_to_id: dict[str, int] = {}
    # Pass 1: upsert fields (no parent yet).
    for n in nodes:
        aliases = sorted({a.lower() for a in n["aliases"]})
        row = existing.get(n["code"])
        if row is None:
            row = Jurisdiction(code=n["code"])
            db.add(row)
        row.name, row.level, row.path, row.aliases = n["name"], n["level"], n["path"], aliases
        await db.flush()
        code_to_id[n["code"]] = row.id
    # Pass 2: wire parents.
    for n in nodes:
        pid = code_to_id.get(n["parent_code"]) if n["parent_code"] else None
        await db.execute(update(Jurisdiction)
                         .where(Jurisdiction.id == code_to_id[n["code"]])
                         .values(parent_id=pid))
    await db.flush()
    return code_to_id


async def map_bills(db, code_to_id: dict[str, int]) -> tuple[int, list]:
    """Set bills.jurisdiction_id per (region,state). Returns (updated_count, unmapped_pairs)."""
    pairs = (await db.execute(
        select(Bill.region, Bill.state, func.count().label("n")).group_by(Bill.region, Bill.state)
    )).all()
    total, unmapped = 0, []
    for r in pairs:
        code = jurisdiction_code(r.region, r.state)
        jid = code_to_id.get(code)
        if jid is None:
            unmapped.append((r.region, r.state, code, r.n))
            continue
        res = await db.execute(
            update(Bill).where(Bill.region == r.region, Bill.state == r.state)
            .values(jurisdiction_id=jid)
        )
        total += res.rowcount or 0
    return total, unmapped


async def refresh_counts(db):
    """bill_count = bills directly assigned to each node (leaf-level; rollups can come later)."""
    await db.execute(text("""
        UPDATE jurisdictions j
        SET bill_count = COALESCE(c.n, 0)
        FROM (SELECT jurisdiction_id, count(*) n FROM bills
              WHERE jurisdiction_id IS NOT NULL GROUP BY jurisdiction_id) c
        WHERE c.jurisdiction_id = j.id
    """))
    await db.execute(text("""
        UPDATE jurisdictions j SET bill_count = 0
        WHERE NOT EXISTS (SELECT 1 FROM bills b WHERE b.jurisdiction_id = j.id)
    """))


async def main():
    async with AsyncSessionLocal() as db:
        code_to_id = await seed_tree(db)
        updated, unmapped = await map_bills(db, code_to_id)
        await refresh_counts(db)
        await db.commit()

        total_bills = (await db.execute(select(func.count()).select_from(Bill))).scalar()
        still_null = (await db.execute(
            select(func.count()).select_from(Bill).where(Bill.jurisdiction_id.is_(None)))).scalar()
        print(f"seeded {len(code_to_id)} jurisdiction nodes")
        print(f"mapped {updated} bills; {still_null}/{total_bills} still NULL")
        if unmapped:
            print("UNMAPPED pairs (region, state, code, n):")
            for u in unmapped:
                print("  ", u)
        else:
            print("no unmapped (region,state) pairs")


if __name__ == "__main__":
    asyncio.run(main())
