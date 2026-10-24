"""Build the butterfly coverage explorer (a single self-contained HTML page) from the database.

Reads every in-scope bill, places it on the butterfly with app.classification.butterfly (no LLM), tags its
cycle with app.classification.cycles, and inlines the result into docs/butterfly-explorer/explorer.src.html.
Read-only against the DB.

    python scripts/build_butterfly_explorer.py --dsn "postgresql://...@127.0.0.1:5462/signalscout" \
        --out butterfly-explorer.html
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.classification.butterfly import butterfly_steps, remanufacturing_evidence  # noqa: E402
from app.classification.cycles import wing_of  # noqa: E402
from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402

TEMPLATE = ROOT / "docs" / "butterfly-explorer" / "explorer.src.html"
WING = {"technical": "t", "biological": "b", "both": "x", "unclassified": "u"}


def _list(v):
    return json.loads(v) if isinstance(v, str) else (v or [])


def _row(b: dict) -> list:
    insts = _list(b["instrument_types"]) or ([b["instrument_type"]] if b["instrument_type"] else [])
    mats = _list(b["material_categories"])
    details = json.loads(b["compliance_details"]) if isinstance(b["compliance_details"], str) else b["compliance_details"]
    bill = {**b, "instrument_types": insts, "material_categories": mats, "compliance_details": details}
    date = str(b["status_date"] or b["last_action_date"] or "")
    # Positional on purpose: the page decodes these by index (see the BILLS map in the template).
    return [
        b["id"], b["region"] or "", b["state"] or "", b["bill_number"] or "", (b["title"] or "").strip()[:240],
        b["status"] or "", date[:4], ",".join(insts), WING[wing_of(mats, insts)], ",".join(mats),
        (b["ai_summary"] or "").strip(), b["source_url_final"] or b["source_url"] or "",
        str(b["effective_date"] or ""), str(b["last_action_date"] or ""),
        ",".join(f"{s}:{how}" for s, how in butterfly_steps(bill).items()),
        b["adjacency"] or "", (remanufacturing_evidence(details) or "")[:420],
    ]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=None, help="Postgres DSN; defaults to app settings (local).")
    ap.add_argument("--out", default="butterfly-explorer.html")
    args = ap.parse_args()
    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, region, state, bill_number, title, status, status_date, last_action_date, effective_date, "
            "       instrument_type, instrument_types, material_categories, ai_summary, source_url, "
            "       source_url_final, adjacency, compliance_details "
            "FROM bills WHERE ce_relevant ORDER BY id"))).mappings().all()
    await engine.dispose()

    data = json.dumps([_row(dict(r)) for r in rows], ensure_ascii=False, separators=(",", ":"))
    html = TEMPLATE.read_text(encoding="utf-8").replace("__BILLS__", data.replace("</", "<\\/"), 1)
    Path(args.out).write_text(html, encoding="utf-8")
    print(f"{len(rows)} bills -> {args.out} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    asyncio.run(main())
