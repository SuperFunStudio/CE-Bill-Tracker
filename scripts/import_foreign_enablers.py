"""Gap-B: import curated EU + UK circular-economy *enablers* (green/sustainable procurement,
right-to-repair, framework CE acts, funding/incentives) that were never ingested — so Ask-the-Atlas
can cite them and the cross-jurisdiction enabler skew (UK recycled_content 0 / right_to_repair 0,
EU thin) is closed. See docs/GAP_B_ENABLER_CURATION_PLAN.md.

Sourcing reuses the existing, proven fetchers — near-zero new fetch code:
  - EU rows  -> app/ingestion/eurlex.py  EurLexClient.fetch_act(celex)   (celex_id-keyed)
  - UK rows  -> app/ingestion/foreign.py UKLegislationClient.fetch(path) (foreign_id UK:leggov:<path>)

Unlike the region's normal Haiku-classified sync, these are CURATED + verified, so the enabler
instrument is FORCED from the seed `theme` (that's the coverage fix) and rows land ce_relevant=true,
reviewed=true. Rollback tracking carries over (status="repealed" + compliance_details.lifecycle).

Safety: dedup on celex_id / foreign_id — an act already in the corpus is SKIPPED (never clobbered).
DEFAULTS TO DRY RUN (still fetches, to validate every CELEX / leg id and preview text sizes).

Run:
    python scripts/import_foreign_enablers.py                 # dry run (local) — fetch + preview
    python scripts/import_foreign_enablers.py --commit
    python scripts/import_foreign_enablers.py --commit --dsn "postgresql://...@127.0.0.1:5436/signalscout"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402
from scripts.build_federal_seed import THEME_INSTRUMENT  # noqa: E402  (region-neutral theme->instrument)
from app.models import Bill, BillText  # noqa: E402
from app.ingestion.eurlex import EurLexClient  # noqa: E402
from app.ingestion.foreign import UKLegislationClient, cap_for_tsvector  # noqa: E402
from app.ingestion.law_dates import derive_status_date  # noqa: E402

SEED = Path(__file__).parent.parent / "data" / "seed" / "foreign_enablers.json"

_REPEALED = {"rescinded", "superseded", "repealed"}

# For this curated set the FAMILY is the reliable instrument signal (the whole point is fixing the
# per-family coverage gaps). Family wins for the three enabler families; `framework` falls back to the
# theme map (so WEEE->epr, a waste-hierarchy transposition->incentives, a strategy->other, etc.).
_FAMILY_INSTRUMENT = {
    "procurement": "recycled_content",
    "right_to_repair": "right_to_repair",
    "funding": "incentives",
}


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


def _curated_fields(law: dict) -> dict:
    """The forced enabler fields shared by EU + UK rows."""
    instr = _FAMILY_INSTRUMENT.get(law.get("family"), THEME_INSTRUMENT.get(law.get("theme", "other"), "other"))
    lifecycle_status = law.get("lifecycle_status", "in_force")
    compliance_details = None
    status = "enacted"
    if lifecycle_status in _REPEALED:
        status = "repealed"
        compliance_details = {"lifecycle": {
            "status": lifecycle_status, "date": law.get("lifecycle_date"), "by": law.get("lifecycle_by")}}
    return dict(
        status=status,
        ce_relevant=True,
        confidence_score=1.0,
        reviewed=True,
        material_categories=law.get("materials", []) or [],
        instrument_type=instr,
        instrument_types=[instr],
        policy_stance="advances",
        stance_source="heuristic",
        urgency="low",
        compliance_details=compliance_details,
    ), instr


async def main(commit: bool, dsn: str | None) -> None:
    laws = json.loads(SEED.read_text(encoding="utf-8"))
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    eu = [l for l in laws if (l.get("region") or "").upper() == "EU"]
    uk = [l for l in laws if (l.get("region") or "").upper() == "UK"]
    inserted = skipped_existing = failed = 0
    report: list[str] = []

    async with Session() as db:
        # --- EU (EurLexClient, celex_id) ---
        async with EurLexClient() as ec:
            for law in eu:
                celex = law.get("celex")
                if not celex:
                    report.append(f"  SKIP(no celex) {law.get('key')}"); failed += 1; continue
                existing = (await db.execute(select(Bill).where(Bill.celex_id == celex))).scalar_one_or_none()
                if existing is not None:
                    skipped_existing += 1
                    report.append(f"  SKIP(exists)  EU {celex:12} #{existing.id} {law.get('title','')[:44]}")
                    continue
                act = await ec.fetch_act(celex, fallback_name=law.get("title", ""))
                if act is None:
                    failed += 1
                    report.append(f"  FETCH-FAIL    EU {celex:12} {law.get('title','')[:44]}")
                    continue
                fields, instr = _curated_fields(law)
                bill = Bill(celex_id=celex, region="EU", state="EU", bill_number=celex,
                            title=act.title, description=act.summary, source_url=act.source_url,
                            status_date=_parse_date(law.get("enacted_date")) or derive_status_date(celex, act.title),
                            last_action_date=_parse_date(law.get("lifecycle_date")),
                            ai_summary=law.get("summary"), **fields)
                db.add(bill)
                await db.flush()
                txt = cap_for_tsvector(act.full_text)
                db.add(BillText(bill_id=bill.id, text=txt, char_len=len(txt)))
                inserted += 1
                life = "" if fields["status"] != "repealed" else f" [{law.get('lifecycle_status','').upper()}]"
                report.append(f"  INSERT  EU {instr:16} {celex:12} {(law.get('title','') or '')[:42]}{life}  text={len(txt):,}ch")

        # --- UK (UKLegislationClient, foreign_id UK:leggov:<path>) ---
        async with UKLegislationClient() as uc:
            for law in uk:
                path = law.get("leg_uk_id")
                if not path:
                    report.append(f"  SKIP(no leg id) {law.get('key')}"); failed += 1; continue
                fid = f"UK:leggov:{path}"
                existing = (await db.execute(select(Bill).where(Bill.foreign_id == fid))).scalar_one_or_none()
                if existing is not None:
                    skipped_existing += 1
                    report.append(f"  SKIP(exists)  UK {path:16} #{existing.id} {law.get('title','')[:40]}")
                    continue
                lw = await uc.fetch(path, english_label=law.get("title", ""))
                if lw is None:
                    failed += 1
                    report.append(f"  FETCH-FAIL    UK {path:16} {law.get('title','')[:40]}")
                    continue
                fields, instr = _curated_fields(law)
                bill = Bill(foreign_id=fid, region="UK", state="UK", bill_number=lw.bill_number,
                            title=law.get("title") or lw.title, description=lw.summary, source_url=lw.source_url,
                            status_date=_parse_date(law.get("enacted_date")) or lw.resolved_status_date,
                            last_action_date=_parse_date(law.get("lifecycle_date")),
                            ai_summary=law.get("summary"), **fields)
                db.add(bill)
                await db.flush()
                txt = cap_for_tsvector(lw.full_text)
                db.add(BillText(bill_id=bill.id, text=txt, char_len=len(txt)))
                inserted += 1
                life = "" if fields["status"] != "repealed" else f" [{law.get('lifecycle_status','').upper()}]"
                report.append(f"  INSERT  UK {instr:16} {path:16} {(law.get('title','') or '')[:40]}{life}  text={len(txt):,}ch")

        if commit:
            await db.commit()
        else:
            await db.rollback()
    await engine.dispose()

    mode = "COMMITTED" if commit else "DRY RUN (no writes; fetched to validate)"
    print(f"=== Foreign enabler import (Gap-B, EU+UK) — {mode} ===")
    print(f"  seed laws        : {len(laws)}  (EU {len(eu)} / UK {len(uk)})")
    print(f"  NEW inserts      : {inserted}")
    print(f"  skipped (exists) : {skipped_existing}")
    print(f"  fetch failures   : {failed}")
    print()
    for line in report:
        print(line)
    if not commit:
        print("\n  Re-run with --commit to write these rows (+ bill_texts).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", action="store_true", help="Write rows + bill_texts (default dry run).")
    ap.add_argument("--dsn", default=None, help="Postgres DSN; defaults to app settings (local).")
    a = ap.parse_args()
    asyncio.run(main(commit=a.commit, dsn=a.dsn))
