"""Read-only analytics over a restored OpenStates Postgres dump.

Two products, both computed WITHOUT altering the dump and WITHOUT any LLM/keyword classification:

  passage-rate baseline  — per (state, legislative session) introduced-vs-enacted over the FULL
                           corpus. This is the honest all-bills denominator our own `bills` table
                           can't provide (it's a keyword-filtered slice). Computing it from the dump
                           gives an apples-to-apples baseline: same source, same session boundaries,
                           and the same "enacted" definition (signed/chaptered) already stamped on
                           our CE cohort — so a state's CE passage rate can sit next to its general
                           rate and the GAP is meaningful.

  CE champion roster     — sponsors of the bills WE'VE ALREADY classified as advancing the circular
                           economy (ce_relevant + policy_stance='advances'). The dump is used only
                           as a sponsor lookup, joined on openstates_id; no bill is reclassified.

See app/ingestion/openstates_pgdump.py for the restore runbook and the dump DSN (PG18 server on
:5433). Always run `--inspect` first against a freshly-restored dump to confirm table/column names
before a full compute — opencivicdata column names drift between dump vintages.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import structlog
from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.ingestion.openstates_pgdump import _dump_engine
from app.models import Bill

log = structlog.get_logger()

# Every table this module reads — all read-only. Surfaced by inspect_schema so we can verify the
# restored dump's actual columns before trusting the compute queries below.
_BASELINE_TABLES = ["opencivicdata_bill", "opencivicdata_legislativesession", "opencivicdata_billaction"]
# Party + chamber live directly on opencivicdata_person (primary_party / current_role), so the
# roster needs only these two — no membership/organization join.
_ROSTER_TABLES = ["opencivicdata_billsponsorship", "opencivicdata_person"]


async def inspect_schema(dsn: str) -> dict:
    """Per-table row count + column list for the tables we touch — the pre-flight before a real run."""
    engine = _dump_engine(dsn)
    out: dict = {}
    try:
        async with engine.connect() as conn:
            for t in _BASELINE_TABLES + _ROSTER_TABLES:
                cols = (await conn.execute(
                    text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name = :t ORDER BY ordinal_position"
                    ),
                    {"t": t},
                )).all()
                if not cols:
                    out[t] = None  # table absent — likely not included in a selective restore
                    continue
                count = (await conn.execute(text(f"SELECT count(*) FROM {t}"))).scalar()
                out[t] = {"rows": count, "columns": [(c[0], c[1]) for c in cols]}
    finally:
        await engine.dispose()
    return out


# Enacted is detected from the NORMALIZED action classification (OpenStates' cross-state vocabulary:
# 'executive-signature' = signed by the governor, 'became-law' = took effect without signature), NOT
# the free-text latest_action_description — that field phrases enactment differently in every state
# ("governor signed" in CO, "filed with secretary of state" in OR, "effective immediately" in TX) and
# for low-yield states the enacting action often isn't even the latest one. classification is a text[]
# loaded as text (e.g. '{executive-signature}'), so a LIKE substring match is exact enough.
_BASELINE_SQL = """
WITH sess AS (
    SELECT id,
           identifier AS session,
           -- capture the 2-letter jurisdiction code. Pattern avoids any colon-word sequence
           -- because SQLAlchemy text() would mis-read it as a bind parameter.
           substring(jurisdiction_id from 'us/[a-z]+:([a-z]{2})') AS state,
           start_date
    FROM opencivicdata_legislativesession
    WHERE jurisdiction_id ~ '/(state|district|territory):[a-z]{2}/'
      AND start_date >= :since
),
enacted_bills AS (
    SELECT DISTINCT bill_id
    FROM opencivicdata_billaction
    WHERE classification LIKE '%executive-signature%'
       OR classification LIKE '%became-law%'
)
SELECT s.state,
       s.session,
       min(s.start_date)                          AS start_date,
       count(*)                                   AS introduced,
       count(*) FILTER (WHERE eb.bill_id IS NOT NULL) AS enacted
FROM opencivicdata_bill bl
JOIN sess s ON s.id = bl.legislative_session_id
LEFT JOIN enacted_bills eb ON eb.bill_id = bl.id
WHERE s.state IS NOT NULL
GROUP BY s.state, s.session
ORDER BY s.state, s.session
"""


def _rate(enacted: int, introduced: int) -> float | None:
    return round(enacted / introduced, 4) if introduced else None


async def compute_baseline(dsn: str, since_year: int = 2019, states: list[str] | None = None) -> dict:
    """Per (state, session) and per-state all-bills passage rate over the full restored corpus."""
    state_set = {s.upper() for s in states} if states else None
    engine = _dump_engine(dsn)
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(text(_BASELINE_SQL), {"since": str(since_year)})).all()
    finally:
        await engine.dispose()

    per_session: list[dict] = []
    rollup: dict[str, dict] = defaultdict(lambda: {"introduced": 0, "enacted": 0})
    for r in rows:
        st = (r.state or "").upper()
        if state_set and st not in state_set:
            continue
        per_session.append({
            "state": st,
            "session": r.session,
            "start_date": r.start_date,
            "introduced": r.introduced,
            "enacted": r.enacted,
            "passage_rate": _rate(r.enacted, r.introduced),
        })
        rollup[st]["introduced"] += r.introduced
        rollup[st]["enacted"] += r.enacted

    per_state = [
        {
            "state": st,
            "introduced": d["introduced"],
            "enacted": d["enacted"],
            "passage_rate": _rate(d["enacted"], d["introduced"]),
        }
        for st, d in sorted(rollup.items())
    ]
    return {"since_year": since_year, "per_state": per_state, "per_session": per_session}


_CHAMBER = {"upper": "Senate", "lower": "House", "legislature": "Legislature"}


def _truthy(v) -> bool:
    """opencivicdata_billsponsorship.primary arrives as a text boolean ('t'/'f') in this restore."""
    return str(v).strip().lower() in ("t", "true", "1")


def _parse_current_role(raw: str | None) -> dict:
    """opencivicdata_person.current_role is a JSON object for CURRENTLY-serving legislators (null
    once they leave office) — so its presence is our 'active ally' signal. Yields chamber/district/
    title; degrades to {} on any parse miss."""
    if not raw:
        return {}
    try:
        role = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(role, dict):
        return {}
    return {
        "chamber": _CHAMBER.get((role.get("org_classification") or "").lower()),
        "district": role.get("district"),
        "title": role.get("title"),
    }


async def build_champion_roster(dsn: str) -> dict:
    """Roster of legislators sponsoring our advancing CE bills, aggregated by stable person_id.

    Only bills we've classified ce_relevant + policy_stance='advances' are considered — so someone
    carrying a preemption (weakens) bill is NOT counted as an ally. Primary sponsor = champion;
    co-sponsor = supporter. The roster's completeness is bounded by our CE corpus: a champion whose
    bills our keyword filter missed will be under-counted (see module docstring).
    """
    # 1. Our already-classified advancing bills. The dump never reclassifies these — it only looks
    #    up who sponsored them.
    async with AsyncSessionLocal() as db:
        bills = (await db.execute(
            select(
                Bill.id,
                Bill.openstates_id,
                Bill.state,
                Bill.instrument_type,
                Bill.material_categories,
                Bill.status,
                Bill.bill_number,
                Bill.source_url,
            )
            .where(Bill.ce_relevant.is_(True))
            .where(Bill.policy_stance == "advances")
            .where(Bill.openstates_id.isnot(None))
        )).all()
    ce = {b.openstates_id: b for b in bills}
    ids = list(ce)
    if not ids:
        return {"champion_count": 0, "champions": [], "note": "no advancing CE bills with openstates_id"}

    # 2. Sponsorships for exactly those bills, plus each sponsor's party/chamber/active status
    #    straight off the person row (primary_party + current_role).
    engine = _dump_engine(dsn)
    persons: dict = {}
    try:
        async with engine.connect() as conn:
            sp = (await conn.execute(
                text(
                    'SELECT bill_id, person_id, name, "primary" AS is_primary, classification '
                    "FROM opencivicdata_billsponsorship WHERE bill_id = ANY(:ids)"
                ),
                {"ids": ids},
            )).all()
            pids = sorted({s.person_id for s in sp if s.person_id})
            if pids:
                prows = (await conn.execute(
                    text(
                        'SELECT id, name, primary_party, "current_role" '
                        "FROM opencivicdata_person WHERE id = ANY(:pids)"
                    ),
                    {"pids": pids},
                )).all()
                for p in prows:
                    role = _parse_current_role(p.current_role)
                    persons[p.id] = {
                        "name": p.name,
                        "party": p.primary_party or None,
                        "chamber": role.get("chamber"),
                        "district": role.get("district"),
                        "active": bool(p.current_role),  # current_role present ⇒ currently in office
                    }
    finally:
        await engine.dispose()

    # 3. Aggregate by person (fall back to a name key when a sponsorship has no resolved person_id).
    champ: dict[str, dict] = defaultdict(lambda: {
        "primary": 0, "cosponsor": 0, "enacted": 0, "bills": [],
        "instruments": set(), "materials": set(), "states": set(), "fallback_name": None,
    })
    for s in sp:
        bill = ce.get(s.bill_id)
        if bill is None:
            continue
        key = s.person_id or f"name:{(s.name or '').lower().strip()}"
        c = champ[key]
        c["fallback_name"] = s.name
        if _truthy(s.is_primary):
            c["primary"] += 1
        else:
            c["cosponsor"] += 1
        if bill.status == "enacted":
            c["enacted"] += 1
        c["bills"].append({
            "bill_id": bill.id,
            "state": bill.state,
            "bill_number": bill.bill_number,
            "instrument": bill.instrument_type,
            "enacted": bill.status == "enacted",
            "source_url": bill.source_url,  # the credibility link, carried per champion bill
        })
        if bill.instrument_type:
            c["instruments"].add(bill.instrument_type)
        c["materials"].update(bill.material_categories or [])
        if bill.state:
            c["states"].add(bill.state)

    champions = []
    for key, c in champ.items():
        total = c["primary"] + c["cosponsor"]
        p = persons.get(key, {})
        champions.append({
            "person_id": None if key.startswith("name:") else key,
            "name": p.get("name") or c["fallback_name"],
            "party": p.get("party"),
            "chamber": p.get("chamber"),
            "district": p.get("district"),
            "active": p.get("active", False),
            "states": sorted(c["states"]),
            "primary_sponsorships": c["primary"],
            "cosponsorships": c["cosponsor"],
            "total_ce_bills": total,
            "enacted_count": c["enacted"],
            "success_rate": round(c["enacted"] / total, 3) if total else None,
            "instruments": sorted(c["instruments"]),
            "materials": sorted(c["materials"]),
            "bills": c["bills"],
        })
    # Rank by lead-sponsorship first (the real "champion" signal), then total involvement.
    champions.sort(key=lambda x: (x["primary_sponsorships"], x["total_ce_bills"]), reverse=True)
    return {"champion_count": len(champions), "champions": champions}


_ENACTED_ACTIONS_SQL = (
    "SELECT bill_id, min(date) AS enacted_date FROM opencivicdata_billaction "
    "WHERE bill_id = ANY(:ids) "
    "AND (classification LIKE '%executive-signature%' OR classification LIKE '%became-law%') "
    "GROUP BY bill_id"
)


async def reconcile_enacted(dsn: str, relevant_only: bool = True) -> dict:
    """Cross-check our bills.status against the dump's normalized enacting actions.

    Returns the agreement breakdown plus `corrections` — bills the dump shows were signed/became law
    (with the enacting date) but our status missed (the staleness to write back). `only_ours` are bills
    we call enacted that the dump lacks a classified signature action for (older/historical/LegiScan
    enactments) — left alone. Also returns per-state advancing-CE counts (2019+) under the RECONCILED
    flag (status='enacted' OR a dump enacting action) so the gap table can be recomputed honestly.
    """
    async with AsyncSessionLocal() as db:
        q = select(
            Bill.id, Bill.openstates_id, Bill.state, Bill.bill_number,
            Bill.status, Bill.status_date, Bill.policy_stance,
        )
        if relevant_only:
            q = q.where(Bill.ce_relevant.is_(True))
        bills = (await db.execute(q)).all()

    ids = [b.openstates_id for b in bills if b.openstates_id]
    engine = _dump_engine(dsn)
    dump_dates: dict[str, str] = {}
    try:
        async with engine.connect() as conn:
            for r in (await conn.execute(text(_ENACTED_ACTIONS_SQL), {"ids": ids})).all():
                dump_dates[r.bill_id] = r.enacted_date
    finally:
        await engine.dispose()

    counts = {"both": 0, "only_ours": 0, "only_dump": 0, "neither": 0, "no_osid": 0}
    by_year: dict[str, dict] = defaultdict(lambda: {"only_ours": 0, "only_dump": 0})
    corrections: list[dict] = []
    per_state: dict[str, dict] = defaultdict(lambda: {"total": 0, "enacted": 0})

    for b in bills:
        ours = b.status == "enacted"
        dump = bool(b.openstates_id) and b.openstates_id in dump_dates
        yr = b.status_date.year if b.status_date else None
        if not b.openstates_id:
            counts["no_osid"] += 1
        if ours and dump:
            counts["both"] += 1
        elif ours and not dump:
            counts["only_ours"] += 1
            by_year[str(yr)]["only_ours"] += 1
        elif dump and not ours:
            counts["only_dump"] += 1
            by_year[str(yr)]["only_dump"] += 1
            corrections.append({
                "bill_id": b.id, "openstates_id": b.openstates_id, "state": b.state,
                "bill_number": b.bill_number, "old_status": b.status,
                "enacted_date": dump_dates[b.openstates_id],
            })
        else:
            counts["neither"] += 1

        # Reconciled per-state advancing-CE tally, 2019+ window.
        if b.policy_stance == "advances" and yr and yr >= 2019:
            per_state[b.state]["total"] += 1
            if ours or dump:
                per_state[b.state]["enacted"] += 1

    return {
        "counts": counts,
        "by_year": dict(sorted(by_year.items())),
        "per_state_advances_2019plus": dict(per_state),
        "corrections": corrections,
    }


async def apply_enacted_corrections(corrections: list[dict]) -> int:
    """Write the reconciled enactments into bills.status/status_date. Caller gates this (dry-run by
    default) — it mutates the live bills table, so run against local first and review the report."""
    from sqlalchemy import update

    from app.ingestion.coordinator import _parse_date

    async with AsyncSessionLocal() as db:
        for c in corrections:
            await db.execute(
                update(Bill).where(Bill.id == c["bill_id"]).values(
                    status="enacted", status_date=_parse_date(c["enacted_date"])
                )
            )
        await db.commit()
    return len(corrections)


async def run(dsn: str, since_year: int = 2019, states: list[str] | None = None,
              out_dir: str = "data/analysis", baseline: bool = True, roster: bool = True) -> dict:
    """Compute the requested products and write them as JSON. Returns a small summary."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary: dict = {"out_dir": str(out)}

    if baseline:
        b = await compute_baseline(dsn, since_year, states)
        (out / "passage_rate_baseline.json").write_text(json.dumps(b, indent=2), encoding="utf-8")
        summary["baseline_states"] = len(b["per_state"])
        summary["baseline_sessions"] = len(b["per_session"])

    if roster:
        r = await build_champion_roster(dsn)
        # default=str so any stray date/Decimal serializes rather than crashing the whole write.
        (out / "ce_champion_roster.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
        summary["champions"] = r.get("champion_count", 0)

    return summary
