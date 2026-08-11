"""Repair bill_texts rows holding the WRONG bill's text (see detect_bill_text_collisions.py).

The LegiScan rung of the text ladder used to resolve an id by (state, bill_number) with no session
constraint, so older bills silently adopted a same-numbered newer bill's document. On prod that hit
471 ce_relevant bills. app/ingestion/bill_text.py now constrains by year and verifies the session
window, so nothing NEW can land this way — this script heals what is already stored.

Per bill, in order:
  1. BACK UP the current bill_texts row and compliance_details to a JSON file. Nothing is touched
     until that file is written, and --restore feeds it straight back, so every step is reversible.
  2. Delete the bill_texts row and NULL compliance_details. An extraction derived from the wrong
     statute is not salvageable, and clearing it makes the bill read as unanalyzed — which is true —
     rather than continuing to serve confident, cited, wrong figures.
  3. With --refetch, pull text again through the FIXED ladder. Bills it cannot pin to a session get
     no text, which is the correct outcome, not a failure.

Re-extraction is deliberately NOT done here — it costs Sonnet calls. Clearing compliance_details
drops the bill below EXTRACTION_VERSION, so the existing backfill picks it up:

    python scripts/extract_dimensions.py --dsn "<prod>" --region US --limit 200

Usage (dry-run is the default; --apply is required to write):

    # what would change, no writes
    python scripts/repair_bill_text_collisions.py --from-json suspects.json --fee-only --dsn "<prod>"
    # do it
    python scripts/repair_bill_text_collisions.py --from-json suspects.json --fee-only --dsn "<prod>" \
        --apply --backup fee_rows_backup.json --refetch
    # undo
    python scripts/repair_bill_text_collisions.py --restore fee_rows_backup.json --dsn "<prod>" --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402
from app.ingestion.bill_text import SOURCE_NONE, fetch_clean_text  # noqa: E402
from app.ingestion.legiscan import LegiScanClient  # noqa: E402
from app.ingestion.nysenate import NYSenateClient  # noqa: E402
from app.ingestion.openstates import OpenStatesClient  # noqa: E402


def _normalize_dsn(dsn: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return dsn if prefix == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(prefix):]
    return dsn


_SELECT = text(
    "select b.id, b.state, b.bill_number, b.title, b.region, b.openstates_id, b.legiscan_bill_id, "
    "       b.source_url, b.change_hash, b.status_date, b.last_action_date, "
    "       b.compliance_details, t.text, t.char_len, t.source, t.indexed_change_hash "
    "from bills b left join bill_texts t on t.bill_id = b.id "
    "where b.id = any(:ids) order by b.id"
)
_UPSERT_TEXT = text(
    "insert into bill_texts (bill_id, text, char_len, source, indexed_change_hash, fetched_at) "
    "values (:id, :text, :clen, :src, :hash, now()) "
    "on conflict (bill_id) do update set text = excluded.text, char_len = excluded.char_len, "
    "source = excluded.source, indexed_change_hash = excluded.indexed_change_hash, "
    "fetched_at = excluded.fetched_at"
)


async def _load_ids(args) -> list[int]:
    if args.ids:
        return [int(x) for x in args.ids.split(",") if x.strip()]
    rows = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
    if args.proof_only:
        # session_year is proof (a document cannot postdate its own bill); title_overlap is a
        # heuristic that will carry some detector false positives.
        rows = [r for r in rows if "session_year" in (r.get("signals") or [])]
    if args.bucket:
        rows = [r for r in rows if r.get("bucket") == args.bucket]
    ids = [int(r["bill_id"]) for r in rows]
    return ids[: args.limit] if args.limit else ids


async def _fee_dataset_ids(db, ids: list[int]) -> list[int]:
    q = text("select id from bills where id = any(:ids) "
             "and compliance_details->'fee_amounts'->>'status' = 'present' order by id")
    return [r[0] for r in (await db.execute(q, {"ids": ids})).all()]


async def restore(db, path: str, apply: bool) -> None:
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    print(f"restoring {len(saved)} bills from {path}")
    for row in saved:
        if not apply:
            continue
        await db.execute(
            text("update bills set compliance_details = cast(:cd as jsonb) where id = :id"),
            {"id": row["bill_id"], "cd": json.dumps(row["compliance_details"])
             if row["compliance_details"] is not None else None},
        )
        if row["text"] is not None:
            await db.execute(_UPSERT_TEXT, {
                "id": row["bill_id"], "text": row["text"], "clen": row["char_len"],
                "src": row["source"], "hash": row["indexed_change_hash"],
            })
    if apply:
        await db.commit()
        print("restored.")
    else:
        print("(dry run — pass --apply to write)")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-json", help="detect_bill_text_collisions.py --json output.")
    src.add_argument("--ids", help="Comma-separated bill ids.")
    src.add_argument("--restore", help="Undo a previous run from its backup file.")
    ap.add_argument("--dsn", help="Target DSN (defaults to settings.database_url).")
    ap.add_argument("--proof-only", action="store_true",
                    help="Only bills flagged by the session_year signal (proof, not heuristic).")
    ap.add_argument("--fee-only", action="store_true",
                    help="Only bills with a PRESENT fee_amounts envelope — the paid dataset.")
    ap.add_argument("--bucket", choices=("clear_text_and_extraction", "text_only_keep_extraction",
                                         "no_extraction"),
                    help="Only bills the detector put in this repair bucket.")
    ap.add_argument("--keep-extraction", action="store_true",
                    help="Replace the text but leave compliance_details alone. Required for the "
                         "text_only_keep_extraction bucket, where the extraction is correct and "
                         "only the stored text is junk.")
    ap.add_argument("--limit", type=int, help="Cap the batch (LegiScan quota is finite).")
    ap.add_argument("--apply", action="store_true", help="Actually write. Default is a dry run.")
    ap.add_argument("--backup", default="bill_text_repair_backup.json",
                    help="Where to write the pre-change snapshot (required for --apply).")
    ap.add_argument("--refetch", action="store_true",
                    help="After clearing, re-fetch text through the fixed ladder.")
    ap.add_argument("--os-delay", type=float, default=1.0)
    args = ap.parse_args()

    engine = create_async_engine(_normalize_dsn(args.dsn or settings.database_url))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        if args.restore:
            await restore(db, args.restore, args.apply)
            await engine.dispose()
            return

        ids = await _load_ids(args)
        if args.fee_only:
            ids = await _fee_dataset_ids(db, ids)
        rows = (await db.execute(_SELECT, {"ids": ids})).all()
        print(f"{len(rows)} bills targeted"
              f"{' (fee dataset only)' if args.fee_only else ''}"
              f"{' (proof signal only)' if args.proof_only else ''}\n")

        # 1. Back up BEFORE touching anything.
        snapshot = [{
            "bill_id": r.id, "state": r.state, "bill_number": r.bill_number,
            "compliance_details": r.compliance_details, "text": r.text,
            "char_len": r.char_len, "source": r.source,
            "indexed_change_hash": r.indexed_change_hash,
        } for r in rows]
        if args.apply:
            Path(args.backup).write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
            print(f"backed up {len(snapshot)} bills to {args.backup}")
        else:
            had_cd = sum(1 for r in rows if r.compliance_details)
            print(f"would back up {len(snapshot)} bills ({had_cd} carry compliance_details)")

        for r in rows[:10]:
            print(f"  id={r.id} {r.state} {r.bill_number} :: {(r.title or '')[:58]}")
        if len(rows) > 10:
            print(f"  … {len(rows) - 10} more")

        if not args.apply:
            print("\n(dry run — nothing written. Pass --apply.)")
            await engine.dispose()
            return

        # 2. Clear the wrong text, and the extraction only when it is also wrong. Keeping a correct
        # extraction beside a cleared text is the whole point of the bucket split — the RI
        # beverage-deposit bills hold real $0.10/$0.04 figures that a blanket clear would delete.
        await db.execute(text("delete from bill_texts where bill_id = any(:ids)"), {"ids": ids})
        if args.keep_extraction:
            print(f"\ncleared text for {len(ids)} bills; compliance_details preserved")
        else:
            await db.execute(
                text("update bills set compliance_details = null where id = any(:ids)"), {"ids": ids}
            )
            print(f"\ncleared text + compliance_details for {len(ids)} bills")
        await db.commit()

        # 3. Re-fetch through the fixed ladder.
        if args.refetch:
            by_source: Counter = Counter()
            async with (
                LegiScanClient() as ls, OpenStatesClient() as os_c, NYSenateClient() as ny
            ):
                for r in rows:
                    try:
                        txt, src = await fetch_clean_text(ls, os_c, r, args.os_delay, ny_client=ny)
                    except Exception as e:  # noqa: BLE001
                        print(f"  id={r.id} fetch failed: {e}")
                        by_source["error"] += 1
                        continue
                    by_source[src] += 1
                    if txt and src != SOURCE_NONE:
                        await db.execute(_UPSERT_TEXT, {
                            "id": r.id, "text": txt, "clen": len(txt),
                            "src": src, "hash": r.change_hash,
                        })
                        await db.commit()
                    print(f"  id={r.id} {r.state} {r.bill_number} -> {src} ({len(txt)} chars)")
            print("\nre-fetch by source:", dict(by_source))
            print("\nSOURCE_NONE is the guard working, not a failure: those bills could not be "
                  "pinned to a session, so they now hold no text instead of the wrong text.")

        print(f"\nNext: re-extract the cleared bills (Sonnet spend) —\n"
              f"  python scripts/extract_dimensions.py --dsn <dsn> --region US --limit {max(len(ids), 20)}")
        print(f"Undo:  python scripts/repair_bill_text_collisions.py --restore {args.backup} "
              f"--dsn <dsn> --apply")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
