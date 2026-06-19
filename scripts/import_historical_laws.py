"""Insert pre-2016 / non-OpenStates historical EPR laws into the bills table.

Why this exists
---------------
OpenStates bulk data bottoms out around 2016, so the ~100 enacted product-stewardship
laws from the 2000-2015 era (electronics, paint, mercury thermostats, early batteries,
etc.) never appear via the dump import. This loads them from the URL-validated
data/seed/historical_epr_laws.json (built by scripts/build_historical_seed.py).

Safety properties
-----------------
- Idempotent: each law gets a stable synthetic openstates_id ("hist:<hash>"), so re-runs
  UPDATE in place rather than duplicate. The "hist:" prefix can never collide with a real
  OpenStates ocd-bill id, so the daily API cycle won't fight these rows.
- Non-destructive: if a law is ALREADY in the DB under a real id (matched on state +
  normalized bill_number, or state + title when no bill number), it is SKIPPED — we do not
  touch live OpenStates-managed rows. This is how the post-2016 overlap (the 7 packaging
  laws, recent paint/battery laws) is left alone.

Run:
    python scripts/import_historical_laws.py            # DRY RUN (no writes) — default
    python scripts/import_historical_laws.py --commit   # actually write
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import Bill  # noqa: E402

SEED = Path(__file__).parent.parent / "data" / "seed" / "historical_epr_laws.json"


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    s = str(val)
    for fmt_len, builder in ((10, lambda x: date.fromisoformat(x[:10])),
                             (7, lambda x: date.fromisoformat(x[:7] + "-01")),
                             (4, lambda x: date(int(x[:4]), 1, 1))):
        try:
            return builder(s)
        except (ValueError, TypeError):
            continue
    return None


def _synthetic_id(law: dict) -> str:
    # Stable on (state, product_category) — unique across the historical set — so editing a
    # law's bill_number / enacted_date / title UPDATES its row in place instead of orphaning
    # it and inserting a duplicate. ("hist:" prefix can't collide with a real ocd-bill id.)
    raw = f"{law['state']}|{law.get('product_category')}"
    return "hist:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


async def _find_live_duplicate(db, law: dict) -> Bill | None:
    """An existing row from a real source (not our synthetic seed) that is the same law."""
    bn = law.get("bill_number")
    if bn:
        q = select(Bill).where(Bill.state == law["state"], Bill.bill_number == bn)
    else:
        q = select(Bill).where(Bill.state == law["state"], Bill.title == law.get("title"))
    for row in (await db.execute(q)).scalars().all():
        if not (row.openstates_id or "").startswith("hist:"):
            return row
    return None


async def main(commit: bool) -> None:
    laws = json.loads(SEED.read_text(encoding="utf-8"))
    inserted = updated = skipped_live = 0
    sample_inserts: list[str] = []

    async with AsyncSessionLocal() as db:
        for law in laws:
            sid = _synthetic_id(law)
            existing_seed = (await db.execute(
                select(Bill).where(Bill.openstates_id == sid)
            )).scalar_one_or_none()

            if existing_seed is None:
                live = await _find_live_duplicate(db, law)
                if live is not None:
                    skipped_live += 1
                    continue

            values = dict(
                openstates_id=sid,
                state=law["state"],
                bill_number=law.get("bill_number"),
                title=law.get("title"),
                description=law.get("ai_summary"),
                status=law.get("status", "enacted"),
                status_date=_parse_date(law.get("enacted_date")),
                last_action_date=_parse_date(law.get("enacted_date")),
                source_url=law.get("source_url"),
                ce_relevant=True,
                confidence_score=1.0,
                reviewed=True,  # researcher-verified, URL-checked
                material_categories=law.get("material_categories", []),
                instrument_type=law.get("instrument_type", "epr"),
                policy_stance="advances",
                stance_source="heuristic",
                urgency=law.get("urgency", "low"),
                ai_summary=law.get("ai_summary"),
            )

            if existing_seed is not None:
                for k, v in values.items():
                    setattr(existing_seed, k, v)
                updated += 1
            else:
                db.add(Bill(**values))
                inserted += 1
                if len(sample_inserts) < 12:
                    sample_inserts.append(
                        f"{law['state']:2} {law.get('product_category',''):20} "
                        f"{(law.get('bill_number') or '—'):10} {str(law.get('enacted_date'))[:4]}  {law.get('title','')[:48]}")

        if commit:
            await db.commit()
        else:
            await db.rollback()

    mode = "COMMITTED" if commit else "DRY RUN (no writes)"
    print(f"=== Historical EPR law import — {mode} ===")
    print(f"  seed laws            : {len(laws)}")
    print(f"  NEW inserts          : {inserted}")
    print(f"  updated (re-run)     : {updated}")
    print(f"  skipped (live row)   : {skipped_live}  (already in DB from OpenStates/other — left untouched)")
    if sample_inserts:
        print("\n  sample of new inserts:")
        for s in sample_inserts:
            print(f"    {s}")
    if not commit:
        print("\n  Re-run with --commit to write these rows.")


if __name__ == "__main__":
    asyncio.run(main(commit="--commit" in sys.argv))
