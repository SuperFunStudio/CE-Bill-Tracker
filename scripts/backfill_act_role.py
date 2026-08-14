"""Populate bills.is_amending — which rows EDIT another law rather than standing on their own.

Why this exists: a "circular-economy laws on the books" total counted each enacted row as a distinct
law, including the 114 that are amending instruments patching a law the corpus usually also holds.
That inflated the total, and inflated it unevenly — the UK and EU legislate heavily by amendment, so
they were overstated against jurisdictions that re-enact instead, which is fatal for a chart whose
whole purpose is cross-region comparison. See migration 050 and app/ingestion/act_role.py.

Assesses EVERY ce_relevant row, writing True or False; a row the classifier has never seen keeps NULL,
so a partial run can't be mistaken for a clean corpus. Idempotent and safe to re-run: it recomputes
from the title each time, so a refinement to the heuristic propagates on the next run. Re-run it after
any classification sweep that promotes new rows into ce_relevant.

    # via the Cloud SQL Auth Proxy (prod is the source of truth):
    venv/Scripts/python.exe scripts/backfill_act_role.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5462/signalscout" [--commit] [--show N]

DRY RUN BY DEFAULT — reports the flag distribution, every rule that fired, and a sample of the rows it
would newly flag. Pass --commit to write. --show N sets how many sample titles to print (default 15);
--show 0 skips the sample. Review the sample before committing: a false positive here deletes a real
law from the count, which is worse than the over-count being fixed.
"""
import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

# Single source of truth, shared with the forward ingest path so backfilled and newly-ingested rows
# agree — same arrangement as app/ingestion/law_dates.py for dates.
from app.ingestion.act_role import classify_act_role, is_revoked  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--commit", action="store_true", help="Write. Default is a dry run.")
    ap.add_argument("--show", type=int, default=15, help="Sample titles to print (0 = none).")
    ap.add_argument("--mark-revoked", action="store_true",
                    help="Also set status='repealed' on enacted rows whose TITLE declares them "
                         "revoked. Separate flag because status drives alerts, deadlines and the "
                         "pipeline charts, so it is a heavier change than setting is_amending.")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT id, region, state, status, title, is_amending FROM bills WHERE ce_relevant"
        )
        by_rule = Counter()
        by_region = Counter()
        changed: list[tuple[bool, int]] = []
        newly_flagged: list[tuple[str, str, str]] = []
        unflagged: list[tuple[str, str]] = []
        enacted_total = enacted_amending = 0

        revoked: list[tuple[int, str, str]] = []
        for r in rows:
            flag, rule = classify_act_role(r["title"], region=r["region"], state=r["state"])
            if r["status"] == "enacted" and is_revoked(r["title"]):
                revoked.append((r["id"], r["region"], r["title"] or ""))
            if r["status"] == "enacted":
                enacted_total += 1
                enacted_amending += int(flag)
            if flag:
                by_rule[rule] += 1
                by_region[r["region"]] += 1
                if r["is_amending"] is not True:
                    newly_flagged.append((r["region"], rule, r["title"] or ""))
            elif r["is_amending"] is True:
                # A heuristic refinement cleared a row a previous run had flagged. Surfaced explicitly
                # because it silently ADDS a law back to the count, and that deserves a look too.
                unflagged.append((r["region"], r["title"] or ""))
            if r["is_amending"] is not flag:
                changed.append((flag, r["id"]))

        print(f"ce_relevant rows assessed : {len(rows)}")
        print(f"  flagged is_amending=True: {sum(by_rule.values())}")
        print(f"  rows whose flag changes : {len(changed)}")
        print(f"    newly flagged         : {len(newly_flagged)}")
        print(f"    flag CLEARED          : {len(unflagged)}")
        print()
        print(f"enacted rows              : {enacted_total}")
        print(f"  of which amending       : {enacted_amending}")
        print(f"  DISTINCT LAWS           : {enacted_total - enacted_amending}")
        print()
        print("by rule  :", by_rule.most_common())
        print("by region:", by_region.most_common())

        if args.show and newly_flagged:
            print(f"\n-- sample of newly flagged (first {args.show}):")
            for region, rule, title in newly_flagged[:args.show]:
                print(f"   [{region}] {rule}: {title[:110]}")
        if unflagged:
            print("\n-- flag CLEARED (these return to the law count):")
            for region, title in unflagged[:args.show or 15]:
                print(f"   [{region}] {title[:110]}")
        if revoked:
            verb = "will be marked" if args.mark_revoked else "NOT touched (pass --mark-revoked)"
            print(f"\n-- enacted rows whose title declares them revoked — {verb}:")
            for _, region, title in revoked:
                print(f"   [{region}] {title[:110]}")
            print("   (a floor, not a census: acts repealed by LATER law without saying so in their "
                  "own title are invisible here — that needs CELLAR / legislation.gov.uk relations)")

        if not args.commit:
            print("\nDRY RUN — nothing written. Re-run with --commit to apply.")
            return

        # One statement per value rather than per row: the flag is a two-valued classification over a
        # few thousand rows, so two UPDATE … WHERE id = ANY($1) calls do the whole job in one round trip
        # each and keep the write atomic per value.
        async with conn.transaction():
            for value in (True, False):
                ids = [bid for flag, bid in changed if flag is value]
                if ids:
                    await conn.execute(
                        "UPDATE bills SET is_amending = $1, updated_at = now() WHERE id = ANY($2)",
                        value, ids,
                    )
            if args.mark_revoked and revoked:
                await conn.execute(
                    "UPDATE bills SET status = 'repealed', updated_at = now() WHERE id = ANY($1)",
                    [bid for bid, _, _ in revoked],
                )
        print(f"\nCOMMITTED — {len(changed)} rows updated"
              + (f", {len(revoked)} marked repealed." if args.mark_revoked and revoked else "."))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
