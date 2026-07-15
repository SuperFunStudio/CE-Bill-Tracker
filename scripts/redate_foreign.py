"""Re-date the remaining dateless FOREIGN bills by re-fetching each through its own adapter and reading
the real source date the adapters now capture (app/ingestion/foreign). One generic pass over every
non-US source — FR code articles (dateDebut), DE Ausfertigungsdatum, NL datum_inwerkingtreding, CA BC
<deposited> / Ontario reg-code year, LV/CL publication dates, AT RIS Inkrafttretensdatum, EE
avaldamiseKuupaev, JP/CN, … — so re-dated and newly-ingested dates use identical logic.

Reuses each adapter's fetch() (no reclassification, text is fetched then discarded — only status_date is
written). Idempotent: only rows with status_date IS NULL are updated. Sources whose site is down, or that
genuinely expose no date (e.g. a few CN municipal regs), simply resolve to None and are left dateless.

    venv/Scripts/python.exe scripts/redate_foreign.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout" [--dry-run] [--region FR]
"""
import argparse
import asyncio
import re
import sys
from collections import defaultdict
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.foreign import (  # noqa: E402
    AustriaRisClient,
    AustraliaFederalClient,
    CanadaBcLawsClient,
    CanadaJusticeClient,
    CanadaOntarioClient,
    ChileLeychileClient,
    ChinaFlkClient,
    GermanyGiiClient,
    EstoniaRiigiClient,
    JapanEgovClient,
    LatviaLikumiClient,
    LegifranceClient,
    LegifranceCodeClient,
    LithuaniaESeimasClient,
    NetherlandsBwbClient,
    PolandEliClient,
    SwedenRiksdagenClient,
    UKLegislationClient,
)

# foreign_id = "<region>:<source>:<native_id>"; map the `source` segment to the adapter that fetches it.
SOURCE_CLIENTS = {
    "legifrance-code": LegifranceCodeClient,
    "legifrance": LegifranceClient,
    "gii": GermanyGiiClient,
    "bwb": NetherlandsBwbClient,
    "bclaws": CanadaBcLawsClient,
    "elaws": CanadaOntarioClient,
    "justice": CanadaJusticeClient,
    "likumi": LatviaLikumiClient,
    "ris": AustriaRisClient,
    "riigiteataja": EstoniaRiigiClient,
    "leychile": ChileLeychileClient,
    "egov": JapanEgovClient,
    "flk": ChinaFlkClient,
    # These have no explicit real-date capture yet, but resolved_status_date derives a year from the
    # id/title (UK uksi/2020/…, AU F2020L…, PL 2021/…, SE sfs-2022-…) — already forward-compat.
    "leggov": UKLegislationClient,
    "legislation": AustraliaFederalClient,
    "eli": PolandEliClient,
    "sfs": SwedenRiksdagenClient,
    "eseimas": LithuaniaESeimasClient,
}

_LEGIARTI_RE = re.compile(r"(LEGIARTI\d+)")


def _parse_fid(foreign_id: str) -> tuple[str, str]:
    """(source, native_id) from '<region>:<source>:<native_id>'."""
    parts = foreign_id.split(":", 2)
    return (parts[1], parts[2]) if len(parts) == 3 else ("", foreign_id)


async def _resolve_source(source: str, rows) -> list[tuple]:
    """Re-fetch every bill of one source through its adapter; return (status_date, bill_id) pairs."""
    cls = SOURCE_CLIENTS.get(source)
    if cls is None:
        print(f"  [{source}] no adapter registered — skipping {len(rows)} rows")
        return []
    out = []
    async with cls() as client:
        for r in rows:
            sid = _parse_fid(r["foreign_id"])[1]
            # FR code articles need the LEGIARTI id (normally set by discover()); recover it from source_url.
            if source == "legifrance-code":
                m = _LEGIARTI_RE.search(r["source_url"] or "")
                if not m:
                    continue
                client._artid = getattr(client, "_artid", {})
                client._artid[sid] = m.group(1)
            try:
                law = await client.fetch(sid, r["title"] or "")
                d = law.resolved_status_date if law else None
            except Exception as e:  # noqa: BLE001 — one bad law must not abort the source
                print(f"    {source}:{sid} fetch error: {str(e)[:70]}")
                d = None
            if d:
                out.append((d, r["id"]))
    print(f"  [{source}] resolved {len(out)}/{len(rows)}")
    return out


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--region", help="Limit to one region (e.g. FR) for a targeted run.")
    args = ap.parse_args()

    conn = await asyncpg.connect(args.dsn)
    try:
        where = "region <> 'US' AND status_date IS NULL AND foreign_id IS NOT NULL"
        params = []
        if args.region:
            where += " AND region = $1"
            params.append(args.region)
        rows = await conn.fetch(
            f"SELECT id, region, foreign_id, source_url, title FROM bills WHERE {where}", *params)

        by_source = defaultdict(list)
        for r in rows:
            by_source[_parse_fid(r["foreign_id"])[0]].append(r)
        print(f"dateless foreign rows: {len(rows)} across sources "
              f"{ {s: len(v) for s, v in sorted(by_source.items(), key=lambda kv: -len(kv[1]))} }")

        updates = []
        for source in sorted(by_source, key=lambda s: -len(by_source[s])):
            updates += await _resolve_source(source, by_source[source])

        print(f"\nresolved a date for {len(updates)} / {len(rows)}")
        for d, i in sorted(updates, key=lambda t: t[0])[:10]:
            print(f"  bill {i}: {d}")
        if args.dry_run:
            print("\n[dry-run] no writes.")
            return
        await conn.executemany(
            "UPDATE bills SET status_date = $1 WHERE id = $2 AND status_date IS NULL", updates)
        print(f"\napplied: set status_date on {len(updates)} rows.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
