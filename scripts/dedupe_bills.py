"""Find — and optionally merge — bills stored twice.

WHY THE MATCH RULE IS THIS STRICT
---------------------------------
The obvious rule, "same (state, bill_number)", is wrong: states reuse bill numbers every
session, so MD SB-901 legitimately names 7 DIFFERENT bills across 2020-2026.

The next-obvious rule, "same (state, bill_number, year, title)", is also wrong, and this is
the trap. It flags 116 rows that are NOT duplicates:

  * Hawaii (66) and Oklahoma (42) carry bills over between the two years of a biennium. Open
    States models each session as its OWN record with its own ocd-bill id and its own source
    URL (HI "year=2023" vs "year=2024"; OK "session=2100" vs "session=2200"). The carryover
    copy keeps the original action date, so it lands in the same calendar year as its sibling
    and looks like a duplicate. Deleting one would destroy a real legislative record.

So a row counts as a duplicate ONLY when it is indistinguishable on every field that would
otherwise mark it as a separate legislative event: state, bill_number, status_date, title AND
source_url. On the corpus this matches exactly one pair — CA SB-212 (2018), entered twice by
the historical seed under two `hist:` keys, once framed as the pharmaceutical stewardship
program and once as the sharps program, both pointing at the same statute and the same URL.

MERGE RULES
-----------
Keeper is the richer row: the one carrying a legiscan_bill_id, else the lowest id. The loser's
prose is folded into the keeper — filling an empty field, or APPENDED when the keeper has its own,
because the two rows may describe different real facets of one statute. Nothing is overwritten. Because compliance_pathway is UNIQUE(bill_id) and the two
rows' impact_score sets cover the SAME companies, the loser's child rows are deleted rather
than repointed; repointing would violate the constraint or double-count the scores.

Run:
    python scripts/dedupe_bills.py             # dry run — report only, writes nothing
    python scripts/dedupe_bills.py --apply     # perform the merge
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Every table with a FK to bills.id, and the column. Children of a deleted duplicate must be
# removed too or the delete fails on the constraint.
CHILD_TABLES = [
    ("bill_changes", "bill_id"),
    ("compliance_deadlines", "bill_id"),
    ("impact_score", "bill_id"),
    ("exposure_brief", "bill_id"),
    ("bill_design_signal", "bill_id"),
    ("bill_product_coverage", "bill_id"),
    ("user_watchlist", "bill_id"),
    ("bill_fee_citation", "bill_id"),
    ("compliance_pathway", "bill_id"),
    ("bill_outcome", "bill_id"),
    ("bill_texts", "bill_id"),
    ("bill_outcome", "remediated_by_bill_id"),
    ("classification_changes", "bill_id"),
    ("litigation_cases", "related_law_id"),
]

# Prose fields folded from loser -> keeper. The seed sometimes enters ONE statute twice to
# describe two facets of it (CA SB-212: the pharmaceutical program and the sharps program), so
# the two rows carry genuinely different, both-correct prose. Merging must not silently pick a
# winner: an empty keeper field takes the loser's text, and a populated one has the loser's text
# APPENDED, so collapsing the rows never costs a fact.
TEXT_FIELDS = ["description", "ai_summary"]


def _fold(keeper_val: str | None, loser_val: str | None) -> str | None:
    """Merged value for one prose field, or None when the keeper already covers it."""
    if not loser_val:
        return None
    if not keeper_val:
        return loser_val
    # Idempotency: never append text the keeper already contains.
    if loser_val.strip() in keeper_val:
        return None
    return f"{keeper_val.rstrip().rstrip('.')}. {loser_val.lstrip()}"

FIND_SQL = """
select state, bill_number, status_date, title, source_url, array_agg(id order by id) ids
from bills
where bill_number is not null
group by 1, 2, 3, 4, 5
having count(*) > 1
order by state, bill_number
"""


async def run(apply: bool) -> int:
    from sqlalchemy import text
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        groups = (await db.execute(text(FIND_SQL))).fetchall()
        if not groups:
            print("no duplicate bills found.")
            return 0

        print(f"{len(groups)} duplicate group(s):\n")
        total_deleted = 0

        for g in groups:
            ids = list(g.ids)
            rows = (await db.execute(text(
                "select id, legiscan_bill_id, openstates_id, description, ai_summary "
                "from bills where id = any(:ids) order by id"
            ), {"ids": ids})).mappings().all()

            # Keeper: the row with a LegiScan link (richest), else the lowest id.
            keeper = next((r for r in rows if r["legiscan_bill_id"]), rows[0])
            losers = [r for r in rows if r["id"] != keeper["id"]]

            print(f"  {g.state} {g.bill_number} ({g.status_date})  {g.title[:60]}")
            print(f"    keep   id={keeper['id']}  legiscan={keeper['legiscan_bill_id']}  "
                  f"openstates={keeper['openstates_id']}")

            for loser in losers:
                print(f"    DELETE id={loser['id']}  openstates={loser['openstates_id']}")
                # Show what happens to prose the loser holds. Nothing is discarded: an
                # empty keeper field takes it, a populated one has it appended.
                for f in TEXT_FIELDS:
                    merged = _fold(keeper[f], loser[f])
                    if merged is None:
                        continue
                    fate = "folded in (keeper empty)" if not keeper[f] else "APPENDED to keeper"
                    print(f"      {f}: {str(loser[f])[:70]!r} -> {fate}")

                child_counts = []
                for tbl, col in CHILD_TABLES:
                    n = (await db.execute(text(
                        f"select count(*) from {tbl} where {col} = :i"), {"i": loser["id"]})).scalar()
                    if n:
                        child_counts.append(f"{tbl}.{col}={n}")
                if child_counts:
                    print(f"      children removed: {', '.join(child_counts)}")

                if apply:
                    updates = {}
                    for f in TEXT_FIELDS:
                        merged = _fold(keeper[f], loser[f])
                        if merged is not None:
                            updates[f] = merged
                    if updates:
                        sets = ", ".join(f"{f} = :{f}" for f in updates)
                        await db.execute(text(f"update bills set {sets} where id = :i"),
                                         {**updates, "i": keeper["id"]})
                    for tbl, col in CHILD_TABLES:
                        await db.execute(text(f"delete from {tbl} where {col} = :i"),
                                         {"i": loser["id"]})
                    await db.execute(text("delete from bills where id = :i"), {"i": loser["id"]})
                    total_deleted += 1

        if apply:
            await db.commit()
            print(f"\napplied: {total_deleted} duplicate row(s) deleted.")
        else:
            print("\nDRY RUN — nothing written. Re-run with --apply to perform the merge.")
        return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="perform the merge (default is a dry run)")
    args = p.parse_args()
    sys.exit(asyncio.run(run(apply=args.apply)))


if __name__ == "__main__":
    main()
