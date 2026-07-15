"""Re-date the JP/CN residual: bills whose real promulgation date the tier-1 id/title derivation could
not reach (Japan's e-Gov era-year LawIds, China's Chinese-only titles). Fetches the REAL source date —
JP from the e-Gov <Law> tag (Era/Year/PromulgateMonth/Day), CN from flk `gbrq` (公布日期) — and sets
status_date. Uses the SAME parsers the live adapters now use (app/ingestion/foreign), so re-dated and
newly-ingested dates agree. Lightweight: one metadata request per law (CN skips the DOCX body), no
reclassification. Idempotent — only rows with status_date IS NULL are touched.

    # via the Cloud SQL Auth Proxy (prod is source of truth):
    venv/Scripts/python.exe scripts/redate_jp_cn.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout" [--dry-run]
"""
import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.foreign import (  # noqa: E402
    JP_API_BASE,
    ChinaFlkClient,
    JapanEgovClient,
    cn_date,
    jp_promulgation_date,
)


def _source_id(foreign_id: str) -> str:
    # foreign_id = "<REGION>:<source>:<native_id>"; native ids may themselves contain no colon.
    return foreign_id.split(":", 2)[-1]


async def _resolve_jp(rows) -> list[tuple]:
    out = []
    async with JapanEgovClient() as c:
        for r in rows:
            sid = _source_id(r["foreign_id"])
            try:
                resp = await c.http.get(f"{JP_API_BASE}/lawdata/{sid}")
                resp.raise_for_status()
                d = jp_promulgation_date(resp.text, sid)
            except Exception as e:  # noqa: BLE001
                d = None
            if d:
                out.append((d, r["id"]))
    return out


async def _resolve_cn(rows) -> list[tuple]:
    out = []
    async with ChinaFlkClient() as c:
        for r in rows:
            bbbs = _source_id(r["foreign_id"])
            try:
                det = await c._details(bbbs)  # flfgDetails JSON only — no DOCX download
                lsyg = det.get("lsyg") or []
                gbrq = det.get("gbrq") or (lsyg[0].get("gbrq") if lsyg else None)
                d = cn_date(gbrq)
            except Exception:  # noqa: BLE001
                d = None
            if d:
                out.append((d, r["id"]))
    return out


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--dry-run", action="store_true", help="Resolve + report without writing.")
    args = ap.parse_args()

    conn = await asyncpg.connect(args.dsn)
    try:
        rows = await conn.fetch(
            "SELECT id, region, foreign_id FROM bills "
            "WHERE region IN ('JP', 'CN') AND status_date IS NULL AND foreign_id IS NOT NULL"
        )
        jp = [r for r in rows if r["region"] == "JP"]
        cn = [r for r in rows if r["region"] == "CN"]
        print(f"dateless residual: JP={len(jp)}  CN={len(cn)}")

        updates = await _resolve_jp(jp) + await _resolve_cn(cn)
        print(f"resolved a real date for {len(updates)} / {len(rows)}")
        for d, i in sorted(updates, key=lambda t: t[0])[:10]:
            print(f"  bill {i}: {d}")

        if args.dry_run:
            print("\n[dry-run] no writes. Re-run without --dry-run to apply.")
            return
        await conn.executemany(
            "UPDATE bills SET status_date = $1 WHERE id = $2 AND status_date IS NULL", updates)
        print(f"\napplied: set status_date on {len(updates)} rows.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
