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

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.sonnet_extractor import SonnetExtractor  # noqa: E402
from app.ingestion.openstates import OpenStatesClient  # noqa: E402
from app.models import Bill, ComplianceDeadline  # noqa: E402


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


async def _candidates(db: AsyncSession, status: str | None, only_missing: bool, limit: int) -> list[Bill]:
    q = select(Bill).where(Bill.epr_relevant == True)  # noqa: E712
    if status:
        q = q.where(Bill.status == status)
    if only_missing:
        q = q.where(Bill.compliance_details.is_(None))
    q = q.where(Bill.openstates_id.isnot(None)).order_by(Bill.status_date.desc().nullslast()).limit(limit)
    return list((await db.execute(q)).scalars().all())


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
        processed = deadlines_written = 0
        async with OpenStatesClient() as os_client:
            for b in bills:
                try:
                    full_text = await os_client.get_bill_text(b.openstates_id) if b.openstates_id else ""
                    extraction = await extractor.extract(
                        state=b.state, bill_number=b.bill_number or "", title=b.title or "",
                        full_text=full_text,
                    )
                    b.compliance_details = extraction.raw_json

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
                        db.add(ComplianceDeadline(
                            bill_id=b.id, state=b.state, deadline_type=dtype,
                            deadline_date=ddate, description=desc, source_url=b.source_url,
                        ))
                        deadlines_written += 1

                    await db.commit()
                    processed += 1
                    print(f"  ✓ {b.state} {b.bill_number}: {len(seen)} deadline(s)"
                          f"{' [no text]' if not full_text else ''}")
                except Exception as e:
                    await db.rollback()
                    print(f"  ✗ {b.state} {b.bill_number}: {type(e).__name__}: {e}")

        print(f"\nprocessed {processed}/{len(bills)} bills, wrote {deadlines_written} deadline rows")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
