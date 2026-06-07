"""Backfill compliance deadlines for already-classified bills.

The "Upcoming Deadlines" page is populated by Stage 3 (Sonnet) extraction, which historically
only ran on a handful of high-confidence bills. As a result most enacted EPR bills have no
compliance_details and no compliance_deadlines rows, so the page is nearly empty.

This script runs the Sonnet compliance extraction over already-relevant bills (default: enacted
bills missing compliance_details), fetches each bill's full text from OpenStates, and writes:
  - bills.compliance_details (the full extraction JSON), and
  - compliance_deadlines rows for every dated deadline, PLUS the bill's effective_date and
    compliance_date (the key implementation/enforcement dates companies care about).

Existing compliance_deadlines rows for a re-processed bill are replaced (not duplicated).

IMPORTANT: this calls the Anthropic API (Claude Sonnet) and the OpenStates API — it costs money
and is rate-limited. Always run --dry-run first to see how many bills would be processed.

compliance_details / compliance_deadlines are NOT copied by push_bills_to_prod.py, so to populate
the live dashboard run this straight against prod via the Cloud SQL Auth Proxy:
    set PGPASSWORD=...   (or $env:PGPASSWORD on PowerShell)
    python scripts/backfill_deadlines.py \
        --dsn "postgresql://signalscout@127.0.0.1:5434/signalscout" --limit 20 [--dry-run]

Local default uses the app's DATABASE_URL.
"""
import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.sonnet_extractor import SonnetExtractor  # noqa: E402
from app.ingestion.openstates import OpenStatesClient  # noqa: E402

# Deliberately raw SQL, not the ORM Bill model: prod's schema may lag the model (new
# columns like policy_stance), and selecting the full entity would fail there. This script
# only touches columns that have long existed (compliance_details, compliance_deadlines).


def _normalize_dsn(dsn: str) -> str:
    """Ensure the DSN uses the asyncpg driver SQLAlchemy needs."""
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    if dsn.startswith("postgresql://"):
        return "postgresql+asyncpg://" + dsn[len("postgresql://"):]
    if dsn.startswith("postgres://"):
        return "postgresql+asyncpg://" + dsn[len("postgres://"):]
    return dsn


def _parse_date(value) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


async def _candidates(db: AsyncSession, status: str | None, only_missing: bool, limit: int) -> list:
    clauses = ["epr_relevant = true", "openstates_id IS NOT NULL"]
    params: dict = {"limit": limit}
    if status:
        clauses.append("status = :status")
        params["status"] = status
    if only_missing:
        clauses.append("compliance_details IS NULL")
    sql = (
        "SELECT id, state, bill_number, title, openstates_id, source_url, status "
        f"FROM bills WHERE {' AND '.join(clauses)} "
        "ORDER BY status_date DESC NULLS LAST LIMIT :limit"
    )
    return list((await db.execute(text(sql), params)).all())


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--status", default="enacted", help="Bill status to target ('' = any).")
    ap.add_argument("--limit", type=int, default=20, help="Max bills to process.")
    ap.add_argument("--all", action="store_true", help="Reprocess even bills that already have compliance_details.")
    ap.add_argument("--dry-run", action="store_true", help="List candidates; no API calls or writes.")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    status = args.status or None
    only_missing = not args.all

    async with Session() as db:
        bills = await _candidates(db, status, only_missing, args.limit)
        print(f"{len(bills)} candidate bills (status={status or 'any'}, "
              f"{'missing-details only' if only_missing else 'all'}, limit={args.limit})")
        for b in bills:
            print(f"  {b.state} {b.bill_number or '?':12s} {b.status:14s} {b.title[:60] if b.title else ''}")

        if args.dry_run:
            print("\n(dry run — no API calls, no writes)")
            await engine.dispose()
            return

        extractor = SonnetExtractor()
        processed = deadlines_written = skipped = 0
        async with OpenStatesClient() as os_client:
            for b in bills:
                tag = f"{b.state} {b.bill_number}"
                try:
                    full_text = await os_client.get_bill_text(b.openstates_id) if b.openstates_id else ""
                    if not full_text:
                        # No usable text (e.g. scanned/image PDF) — leave the bill as a future
                        # candidate rather than writing empty compliance_details.
                        skipped += 1
                        print(f"  [skip] {tag}: no extractable text")
                        continue
                    extraction = await extractor.extract(
                        state=b.state, bill_number=b.bill_number or "", title=b.title or "",
                        full_text=full_text,
                    )
                    await db.execute(
                        text("UPDATE bills SET compliance_details = CAST(:cd AS jsonb), "
                             "updated_at = now() WHERE id = :id"),
                        {"cd": json.dumps(extraction.raw_json), "id": b.id},
                    )

                    # Replace any existing deadline rows for this bill.
                    await db.execute(
                        text("DELETE FROM compliance_deadlines WHERE bill_id = :bid"), {"bid": b.id}
                    )

                    # Collect dated deadlines from the extraction, plus the headline
                    # effective_date / compliance_date that aren't in the deadlines array.
                    rows: list[tuple[str, date, str]] = []
                    for dl in extraction.deadlines:
                        d = _parse_date(dl.get("date"))
                        if d:
                            rows.append((dl.get("type", "compliance"), d, dl.get("description", "")))
                    eff = _parse_date(extraction.effective_date)
                    if eff:
                        rows.append(("effective", eff, f"{b.bill_number or 'Bill'} takes effect"))
                    comp = _parse_date(extraction.raw_json.get("compliance_date"))
                    if comp:
                        rows.append(("compliance", comp, f"{b.bill_number or 'Bill'} compliance date"))

                    seen = set()
                    for dtype, ddate, desc in rows:
                        key = (ddate, dtype)
                        if key in seen:
                            continue
                        seen.add(key)
                        await db.execute(
                            text("INSERT INTO compliance_deadlines "
                                 "(bill_id, state, deadline_type, deadline_date, description, source_url) "
                                 "VALUES (:bid, :state, :dtype, :ddate, :desc, :src)"),
                            {"bid": b.id, "state": b.state, "dtype": dtype, "ddate": ddate,
                             "desc": desc, "src": b.source_url},
                        )
                        deadlines_written += 1

                    await db.commit()
                    processed += 1
                    print(f"  [ok]   {tag}: {len(seen)} deadline(s)")
                except Exception as e:
                    await db.rollback()
                    print(f"  [fail] {tag}: {type(e).__name__}: {e}")

        print(f"\nprocessed {processed}/{len(bills)} bills "
              f"({skipped} skipped, no text), wrote {deadlines_written} deadline rows")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
