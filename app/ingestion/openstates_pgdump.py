"""Backfill the bills table from a restored OpenStates PostgreSQL dump.

Why this exists
---------------
The OpenStates v3 search API is too rate-limited for a full historical load (one state
took ~54 min, ~66% throttled). The maintained bulk source is OpenStates' monthly Postgres
dump (https://data.openstates.org/postgres/monthly/YYYY-MM-public.pgdump) — the entire
public dataset (all states, all sessions) in one file. You restore it into a scratch
Postgres database once; this module reads from that restored DB and upserts the bills we
care about into our own `bills` table. After that, only the lightweight daily API
incremental cycle runs. Because we hold the full corpus locally, the same dump can later be
re-filtered for OTHER topics (voting, healthcare) with zero new downloads.

Restore runbook (run once, in a shell with the OpenStates dump downloaded)
--------------------------------------------------------------------------
    createdb openstates_dump
    pg_restore --no-owner --no-acl -d openstates_dump 2026-06-public.pgdump
    # (pg_restore prints some ignorable errors about missing roles — that's fine)

Then, from the project venv:
    python scripts/import_openstates_pgdump.py --inspect          # confirm tables/row counts
    python scripts/import_openstates_pgdump.py --dry-run --states TX,CA   # preview mapping
    python scripts/import_openstates_pgdump.py --since-year 2023          # do the import

Schema (OpenStates / opencivicdata)
-----------------------------------
    opencivicdata_bill(id, identifier, title, classification[], legislative_session_id, ...)
    opencivicdata_legislativesession(id, identifier, jurisdiction_id, start_date 'YYYY[-MM[-DD]]', ...)
    opencivicdata_billabstract(bill_id, abstract, note)
    opencivicdata_billsource(bill_id, url, note)
    opencivicdata_billaction(bill_id, description, date 'YYYY-MM-DD HH:MM:SS+TZ')
Bill ids are OCD strings (ocd-bill/<uuid>) and map to our Bill.openstates_id, so a dump
import and the API cycle converge on the same rows (upsert on openstates_id).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine

from app.classification.keywords import KeywordFilter
from app.database import AsyncSessionLocal
from app.ingestion.coordinator import (
    _infer_openstates_status,
    _normalize_bill_number,
    _parse_date,
    _pick_source_url,
)
from app.models import Bill

log = structlog.get_logger()

# State/territory code embedded in an OCD jurisdiction id, e.g.
# ocd-jurisdiction/country:us/state:ca/government  or  .../district:dc/government
_JURIS_CODE_RE = re.compile(r"/(?:state|district|territory):([a-z]{2})/")


def _dump_engine(dump_dsn: str):
    url = dump_dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(url, echo=False, pool_pre_ping=True)


def _state_from_jurisdiction(jid: str | None) -> str | None:
    if not jid:
        return None
    m = _JURIS_CODE_RE.search(jid)
    return m.group(1).upper() if m else None


def _load_known_law_keys() -> set:
    """(state, normalized_bill_number) for the known enacted EPR laws.

    Some flagship laws have bland titles and no abstract (e.g. ME LD 1541 — "An Act To
    Support And Improve Municipal Recycling Programs") so the keyword filter misses them.
    We keep the old hand-curated list (data/seed/known_epr_laws.json) only as identifiers:
    bills matching these keys bypass the keyword filter so their fresh dump data (correct
    URL/status/title) is always imported. We do NOT use the list's stale content.
    """
    import json
    from pathlib import Path

    p = Path(__file__).parent.parent.parent / "data" / "seed" / "known_epr_laws.json"
    keys: set = set()
    try:
        for law in json.loads(p.read_text(encoding="utf-8")):
            st, num = law.get("state"), law.get("bill_number")
            if st and num:
                keys.add((st, _normalize_bill_number(num)))
    except Exception as e:
        log.warning("known_law_allowlist_unavailable", error=str(e))
    return keys


# One row per bill, with latest action + best abstract + all source urls folded in.
# Written set-based (CTEs, single pass per child table) rather than per-bill LATERAL so it
# stays fast even when the dump is restored WITHOUT indexes — a selective `pg_restore -t`
# of just the tables we need (to save disk) does not bring the indexes along.
_EXTRACT_SQL = """
WITH sess AS (
    SELECT id, jurisdiction_id
    FROM opencivicdata_legislativesession
    WHERE jurisdiction_id ~ '/(state|district|territory):[a-z]{2}/'
      AND start_date >= :since
),
b AS (
    SELECT bl.id, bl.identifier, bl.title, s.jurisdiction_id,
           bl.latest_action_date, bl.latest_action_description
    FROM opencivicdata_bill bl
    JOIN sess s ON s.id = bl.legislative_session_id
),
abs AS (
    SELECT DISTINCT ON (ab.bill_id) ab.bill_id, ab.abstract
    FROM opencivicdata_billabstract ab
    JOIN b ON b.id = ab.bill_id
    WHERE ab.abstract <> ''
    ORDER BY ab.bill_id, length(ab.abstract) DESC
),
src AS (
    SELECT s.bill_id, array_agg(s.url) AS urls
    FROM opencivicdata_billsource s
    JOIN b ON b.id = s.bill_id
    GROUP BY s.bill_id
)
SELECT
    b.id                        AS openstates_id,
    b.identifier                AS identifier,
    b.title                     AS title,
    b.jurisdiction_id           AS jurisdiction_id,
    b.latest_action_date        AS latest_action_date,
    b.latest_action_description AS latest_action_description,
    abs.abstract                AS abstract,
    src.urls                    AS source_urls
FROM b
LEFT JOIN abs ON abs.bill_id = b.id
LEFT JOIN src ON src.bill_id = b.id
"""


def _map_row(row) -> dict | None:
    state = _state_from_jurisdiction(row.jurisdiction_id)
    if not row.openstates_id or not state:
        return None
    last_action = _parse_date(row.latest_action_date)
    status = _infer_openstates_status({
        "classification": [],
        "latest_action_description": row.latest_action_description or "",
    })
    urls = [{"url": u} for u in (row.source_urls or [])]
    return {
        "openstates_id": row.openstates_id,
        "state": state,
        "bill_number": _normalize_bill_number(row.identifier or ""),
        "title": row.title,
        "description": row.abstract,
        "status": status,
        "status_date": last_action,
        "last_action_date": last_action,
        "source_url": _pick_source_url(urls),
        "last_fetched_at": datetime.now(timezone.utc),
    }


async def mark_known_laws(db) -> int:
    """Force the known enacted EPR laws to relevant, with correct (dump-sourced) data.

    Flagship laws often have bland titles (e.g. ME LD 1541 — "...Municipal Recycling
    Programs") that fail the keyword filter at classification time, so without this they'd
    never show. Bill numbers are reused across sessions, so for each known law we pick the
    single best matching row: prefer status='enacted', then the row whose last_action_date
    is closest to the known enactment year. Only the bill's relevance/confidence is set —
    its URL, title and status come from the dump, not the old (bad) seed content.
    """
    import json
    from pathlib import Path

    from sqlalchemy import select

    p = Path(__file__).parent.parent.parent / "data" / "seed" / "known_epr_laws.json"
    try:
        laws = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("known_laws_unavailable", error=str(e))
        return 0

    marked = 0
    for law in laws:
        st = law.get("state")
        num = _normalize_bill_number(law.get("bill_number") or "")
        if not st or not num:
            continue
        rows = (await db.execute(
            select(Bill).where(Bill.state == st, Bill.bill_number == num)
        )).scalars().all()
        if not rows:
            continue
        try:
            enacted_year = int(str(law.get("enacted_date"))[:4])
        except (TypeError, ValueError):
            enacted_year = 0

        def _rank(b):
            is_enacted = 1 if (b.status or "") == "enacted" else 0
            yr = b.last_action_date.year if b.last_action_date else 0
            return (is_enacted, -abs(yr - enacted_year) if enacted_year else 0)

        best = max(rows, key=_rank)
        best.ce_relevant = True
        best.confidence_score = 1.0
        if not best.urgency:
            best.urgency = "high"
        if not best.instrument_type:
            best.instrument_type = law.get("instrument_type")
        marked += 1
    await db.commit()
    log.info("known_laws_marked", marked=marked)
    return marked


async def inspect_dump(dump_dsn: str) -> dict:
    """List the opencivicdata bill tables and row counts to confirm the restore worked."""
    engine = _dump_engine(dump_dsn)
    out: dict = {"tables": {}}
    try:
        async with engine.connect() as conn:
            tables = (await conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE 'opencivicdata_bill%' "
                "   OR table_name = 'opencivicdata_legislativesession' "
                "ORDER BY table_name"
            ))).scalars().all()
            for t in tables:
                count = (await conn.execute(text(f"SELECT count(*) FROM {t}"))).scalar()
                out["tables"][t] = count
    finally:
        await engine.dispose()
    return out


async def import_from_dump(
    dump_dsn: str,
    since_year: int = 2023,
    states: list[str] | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    keyword_filter: bool = True,
    commit_every: int = 1000,
) -> dict:
    """Stream bills from the restored dump and upsert into our bills table.

    states: optional uppercase state codes to restrict to (filtered in Python after the
            jurisdiction code is parsed).
    keyword_filter: when True (default), only import bills whose title/abstract pass the EPR
            KeywordFilter — keeps the bills table focused, mirroring the API ingest path.
            Pass False to import the full corpus (e.g. to re-filter later for another topic).
    dry_run reports counts + a sample without writing.
    """
    state_set = {s.upper() for s in states} if states else None
    kf = KeywordFilter() if keyword_filter else None
    allowlist = _load_known_law_keys() if keyword_filter else set()
    engine = _dump_engine(dump_dsn)
    summary = {
        "since_year": since_year, "states": sorted(state_set) if state_set else "ALL",
        "keyword_filter": keyword_filter, "allowlist_size": len(allowlist),
        "scanned": 0, "matched": 0, "imported": 0, "skipped_no_state": 0,
        "filtered_out_state": 0, "filtered_out_keyword": 0, "allowlisted": 0,
        "dry_run": dry_run, "sample": None,
    }

    def _keep(values: dict) -> bool:
        if state_set and values["state"] not in state_set:
            summary["filtered_out_state"] += 1
            return False
        # Known enacted laws always pass — their titles often lack EPR keywords.
        if (values["state"], values["bill_number"]) in allowlist:
            summary["allowlisted"] += 1
            return True
        if kf and not kf.passes_threshold(values["title"] or "", values["description"] or ""):
            summary["filtered_out_keyword"] += 1
            return False
        return True
    sql = _EXTRACT_SQL + ("\nLIMIT :limit" if limit else "")
    params = {"since": str(since_year)}
    if limit:
        params["limit"] = limit

    batch: list[dict] = []

    async def _flush(db):
        if not batch:
            return
        for values in batch:
            stmt = insert(Bill).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["openstates_id"],
                set_={
                    "state": stmt.excluded.state,
                    "bill_number": stmt.excluded.bill_number,
                    "title": stmt.excluded.title,
                    "description": stmt.excluded.description,
                    "status": stmt.excluded.status,
                    "status_date": stmt.excluded.status_date,
                    "last_action_date": stmt.excluded.last_action_date,
                    "source_url": stmt.excluded.source_url,
                    "last_fetched_at": stmt.excluded.last_fetched_at,
                },
            )
            await db.execute(stmt)
        await db.commit()
        batch.clear()

    try:
        async with engine.connect() as conn:
            result = await conn.stream(text(sql), params)
            if dry_run:
                async for row in result:
                    summary["scanned"] += 1
                    values = _map_row(row)
                    if values is None:
                        summary["skipped_no_state"] += 1
                        continue
                    if not _keep(values):
                        continue
                    summary["matched"] += 1
                    if summary["sample"] is None:
                        summary["sample"] = values
            else:
                async with AsyncSessionLocal() as db:
                    async for row in result:
                        summary["scanned"] += 1
                        values = _map_row(row)
                        if values is None:
                            summary["skipped_no_state"] += 1
                            continue
                        if not _keep(values):
                            continue
                        summary["matched"] += 1
                        batch.append(values)
                        summary["imported"] += 1
                        if len(batch) >= commit_every:
                            await _flush(db)
                    await _flush(db)
    finally:
        await engine.dispose()

    # Force known enacted laws to relevant (they often fail keyword classification).
    if keyword_filter and not dry_run:
        async with AsyncSessionLocal() as db:
            summary["known_laws_marked"] = await mark_known_laws(db)

    log.info("openstates_pgdump_import_done",
             imported=summary["imported"], matched=summary["matched"],
             scanned=summary["scanned"])
    return summary
