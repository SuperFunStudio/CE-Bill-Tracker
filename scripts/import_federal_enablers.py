"""Insert curated US-FEDERAL circular-economy *enablers* (statutes / CFR / programs / EOs)
into the bills table, and fetch their circular-economy-relevant full text into bill_texts.

Why this exists
---------------
Landmark federal enablers — RCRA, Save Our Seas 2.0, the IIJA recycling provisions, the EPA
Comprehensive Procurement Guideline (FAR Part 23 / 40 CFR 247), USDA BioPreferred, buy-recycled
Executive Orders — are the framework the Atlas's analyst tool ("Ask the Atlas") should be able
to CITE, but they are not congressional bills OpenStates/LegiScan ingest, so they were absent
from the corpus. This loads them from the URL-validated data/seed/federal_enablers.json (built
by scripts/build_federal_seed.py) and pulls their full text (windowed to the CE-relevant
portions by app/ingestion/federal_text.py) into bill_texts so citations quote real passages.

Safety properties (same contract as import_historical_laws.py)
--------------------------------------------------------------
- Idempotent: stable synthetic openstates_id "fed:<hash(key)>" -> re-runs UPDATE in place.
  The "fed:" prefix can't collide with a real ocd-bill id or the "hist:" historical seed.
- Non-destructive: if the same law is already in the DB under a real id (state 'US' +
  bill_number), it is SKIPPED — we never clobber a live OpenStates/Congress row.
- Gated: DRY RUN by default; text is fetched only on --commit (network op). --with-text also
  fetches during a dry run to preview per-law stored sizes.

Run:
    python scripts/import_federal_enablers.py                 # DRY RUN (no writes, no fetch)
    python scripts/import_federal_enablers.py --with-text     # DRY RUN + fetch text (size preview)
    python scripts/import_federal_enablers.py --commit        # write rows + bill_texts
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402
from app.models import Bill, BillText  # noqa: E402
from app.ingestion.federal_text import fetch_text  # noqa: E402

SEED = Path(__file__).parent.parent / "data" / "seed" / "federal_enablers.json"


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    s = str(val)
    for builder in (lambda x: date.fromisoformat(x[:10]),
                    lambda x: date.fromisoformat(x[:7] + "-01"),
                    lambda x: date(int(x[:4]), 1, 1)):
        try:
            return builder(s)
        except (ValueError, TypeError):
            continue
    return None


def _synthetic_id(law: dict) -> str:
    # Stable on the curated `key` slug — editing a law's citation/date/title UPDATES in place.
    return "fed:" + hashlib.sha1(law["key"].encode("utf-8")).hexdigest()[:16]


async def _find_live_duplicate(db, law: dict) -> Bill | None:
    """An existing row from a real source (not our synthetic seed) that is the same law."""
    bn = law.get("bill_number")
    if not bn:
        return None
    q = select(Bill).where(Bill.state == "US", Bill.bill_number == bn)
    for row in (await db.execute(q)).scalars().all():
        oid = row.openstates_id or ""
        if not oid.startswith("fed:") and not oid.startswith("hist:"):
            return row
    return None


async def _upsert_text(db, bill_id: int, txt: str) -> None:
    existing = (await db.execute(
        select(BillText).where(BillText.bill_id == bill_id))).scalar_one_or_none()
    if existing is None:
        db.add(BillText(bill_id=bill_id, text=txt, char_len=len(txt)))
    else:
        existing.text = txt
        existing.char_len = len(txt)


async def main(commit: bool, with_text: bool, dsn: str | None = None) -> None:
    laws = json.loads(SEED.read_text(encoding="utf-8"))
    fetch = commit or with_text
    inserted = updated = skipped_live = 0
    text_rows = 0
    report: list[str] = []

    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        for law in laws:
            sid = _synthetic_id(law)
            existing_seed = (await db.execute(
                select(Bill).where(Bill.openstates_id == sid))).scalar_one_or_none()

            if existing_seed is None:
                live = await _find_live_duplicate(db, law)
                if live is not None:
                    skipped_live += 1
                    report.append(f"  SKIP (live)  {law['key']:30} matches existing #{live.id} {law.get('bill_number')}")
                    continue

            instr = law.get("instrument_type", "other")
            # Rolled-back enablers stay in the corpus as historical record: status "repealed"
            # (drops them from in-force counts) with the rescission/supersession recorded in a
            # structured lifecycle envelope. They still `advances` CE — the movement is tracked
            # via status, not by flipping their stance.
            lifecycle_status = law.get("lifecycle_status", "in_force")
            compliance_details = None
            if lifecycle_status != "in_force":
                compliance_details = {"lifecycle": {
                    "status": lifecycle_status,           # rescinded | superseded | repealed
                    "date": law.get("lifecycle_date"),
                    "by": law.get("lifecycle_by"),
                }}
            values = dict(
                openstates_id=sid,
                region="US",
                state="US",
                bill_number=law.get("bill_number"),
                title=law.get("title"),
                description=law.get("ai_summary"),
                status=law.get("status", "enacted"),
                status_date=_parse_date(law.get("enacted_date")),
                last_action_date=_parse_date(law.get("lifecycle_date") or law.get("enacted_date")),
                source_url=law.get("source_url"),
                ce_relevant=True,
                confidence_score=1.0,
                reviewed=True,  # researcher-verified, URL-checked
                material_categories=law.get("material_categories", []),
                instrument_type=instr,
                instrument_types=[instr],
                policy_stance="advances",
                stance_source="heuristic",
                urgency=law.get("urgency", "low"),
                ai_summary=law.get("ai_summary"),
                compliance_details=compliance_details,
            )

            if existing_seed is not None:
                for k, v in values.items():
                    setattr(existing_seed, k, v)
                bill = existing_seed
                updated += 1
                tag = "UPDATE"
            else:
                bill = Bill(**values)
                db.add(bill)
                inserted += 1
                tag = "INSERT"

            # Fetch + attach full text. On INSERT we need the bill id first (flush), which
            # requires a session that will be committed; on dry run we can't flush safely, so
            # we fetch-and-size only (no bill_texts write) to preview.
            txt_note = ""
            if fetch and law.get("fulltext_url") and law.get("fulltext_kind") not in (None, "none"):
                try:
                    txt, raw_len = fetch_text(law["fulltext_url"], law["fulltext_kind"])
                    txt_note = f"  text={len(txt):,}ch (raw {raw_len:,})"
                    if commit:
                        await db.flush()  # ensure bill.id is populated
                        await _upsert_text(db, bill.id, txt)
                        text_rows += 1
                except Exception as e:  # noqa: BLE001
                    txt_note = f"  TEXT-FETCH FAILED: {type(e).__name__}: {e}"

            life = "" if lifecycle_status == "in_force" else f" [{lifecycle_status.upper()} {law.get('lifecycle_date','')}]"
            report.append(f"  {tag}  {instr:16} {(law.get('bill_number') or '—'):20} "
                          f"{str(law.get('enacted_date'))[:4]}  {(law.get('title') or '')[:42]}{life}{txt_note}")

        if commit:
            await db.commit()
        else:
            await db.rollback()
    await engine.dispose()

    mode = "COMMITTED" if commit else ("DRY RUN + text preview" if with_text else "DRY RUN (no writes)")
    print(f"=== Federal enabler import — {mode} ===")
    print(f"  seed laws          : {len(laws)}")
    print(f"  NEW inserts        : {inserted}")
    print(f"  updated (re-run)   : {updated}")
    print(f"  skipped (live row) : {skipped_live}")
    if commit:
        print(f"  bill_texts written : {text_rows}")
    print()
    for line in report:
        print(line)
    if not commit:
        print("\n  Re-run with --commit to write these rows (+ fetch text into bill_texts).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", action="store_true", help="Write rows + bill_texts (default dry run).")
    ap.add_argument("--with-text", action="store_true", help="Dry run but fetch text to preview sizes.")
    ap.add_argument("--dsn", default=None, help="Postgres DSN; defaults to app settings (local).")
    a = ap.parse_args()
    asyncio.run(main(commit=a.commit, with_text=a.with_text, dsn=a.dsn))
