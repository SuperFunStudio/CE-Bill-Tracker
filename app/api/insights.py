"""Insights "Battle of the Bills" endpoints — the per-state passage-rate gap and the CE champion roster.

Both lean on analysis the prod DB can't produce alone:
  - the all-bills passage-rate BASELINE exists only in the OpenStates dump, precomputed to
    data/analysis/passage_rate_baseline.json (shipped into the image). The CE side of the gap is
    queried live, so it tracks the DB; the baseline is the static dump figure.
  - the champion roster is dump-derived sponsor data (prod has no sponsorships), precomputed to
    data/analysis/ce_champion_roster.json.

See app/ingestion/dump_analytics.py + scripts/compute_dump_baseline.py for how those JSONs are built.
"""
import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bill
from app.schemas import ChampionBill, ChampionSummary, StateCycleRow, StateGapRow

router = APIRouter(prefix="/insights", tags=["insights"])

_ANALYSIS_DIR = Path(__file__).resolve().parents[2] / "data" / "analysis"
# States below this many advancing-CE bills are dropped from the gap table — too few to compare
# against a baseline without the rate being noise. Surfaced in the API/UI copy.
GAP_MIN_BILLS = 15


@lru_cache(maxsize=1)
def _baseline() -> dict:
    """All-bills passage rate per state (from the dump). {state: passage_rate}. Cached for process life."""
    try:
        data = json.loads((_ANALYSIS_DIR / "passage_rate_baseline.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {r["state"]: r["passage_rate"] for r in data.get("per_state", [])}


@lru_cache(maxsize=1)
def _baseline_sessions() -> list[dict]:
    """All-bills per-(state, session) rows from the dump baseline — aggregated to bienniums for the
    per-cycle view."""
    try:
        data = json.loads((_ANALYSIS_DIR / "passage_rate_baseline.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    return data.get("per_session", [])


def _biennium_start(year: int) -> int:
    """US legislatures run on odd-year-start bienniums; map any year to its cycle's first (odd) year."""
    return year if year % 2 == 1 else year - 1


@lru_cache(maxsize=1)
def _roster() -> list[dict]:
    try:
        data = json.loads((_ANALYSIS_DIR / "ce_champion_roster.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    return data.get("champions", [])


@router.get("/state-gap", response_model=list[StateGapRow])
async def get_state_gap(db: AsyncSession = Depends(get_db)):
    """Per-state advancing-CE passage rate vs. the all-bills baseline. Sorted by gap (most
    CE-favorable first). Only states with >= GAP_MIN_BILLS advancing CE bills (2019+)."""
    year = func.extract("year", Bill.status_date).cast(Integer)
    q = (
        select(
            Bill.state,
            func.count().label("total"),
            func.count().filter(Bill.status == "enacted").label("enacted"),
        )
        .where(Bill.ce_relevant == True)
        .where(Bill.policy_stance == "advances")
        .where(year >= 2019)
        .group_by(Bill.state)
    )
    rows = (await db.execute(q)).all()
    baseline = _baseline()
    out: list[StateGapRow] = []
    for r in rows:
        if r.total < GAP_MIN_BILLS:
            continue
        ce_rate = round(r.enacted / r.total, 4)
        b = baseline.get(r.state)
        out.append(StateGapRow(
            state=r.state, ce_rate=ce_rate, ce_enacted=r.enacted, ce_total=r.total,
            baseline_rate=b, gap=(round(ce_rate - b, 4) if b is not None else None),
        ))
    out.sort(key=lambda x: (x.gap if x.gap is not None else -9))
    out.reverse()
    return out


@router.get("/state-cycles", response_model=list[StateCycleRow])
async def get_state_cycles(state: str = Query(..., min_length=2, max_length=2), db: AsyncSession = Depends(get_db)):
    """One state's advancing-CE passage rate vs. the all-bills baseline, per legislative biennium —
    the gap as a trend across cycles. Bucketed by biennium (carryover-safe)."""
    st = state.upper()

    # CE side (live): advancing CE bills bucketed by status_date year -> biennium.
    year = func.extract("year", Bill.status_date).cast(Integer)
    q = (
        select(year.label("yr"), func.count().label("total"),
               func.count().filter(Bill.status == "enacted").label("enacted"))
        .where(Bill.ce_relevant == True)
        .where(Bill.policy_stance == "advances")
        .where(Bill.state == st)
        .where(Bill.status_date.isnot(None))
        .group_by("yr")
    )
    ce: dict[int, dict] = {}
    for r in (await db.execute(q)).all():
        if r.yr is None:
            continue
        b = _biennium_start(int(r.yr))
        agg = ce.setdefault(b, {"total": 0, "enacted": 0})
        agg["total"] += r.total
        agg["enacted"] += r.enacted

    # Baseline side (dump JSON): all-bills sessions aggregated to bienniums.
    base: dict[int, dict] = {}
    for s in _baseline_sessions():
        if s.get("state") != st or not s.get("start_date"):
            continue
        try:
            yr = int(str(s["start_date"])[:4])
        except ValueError:
            continue
        b = _biennium_start(yr)
        agg = base.setdefault(b, {"introduced": 0, "enacted": 0})
        agg["introduced"] += s.get("introduced", 0)
        agg["enacted"] += s.get("enacted", 0)

    current_biennium = _biennium_start(date.today().year)
    rows: list[StateCycleRow] = []
    for b in sorted(set(ce) | set(base)):
        # Floor at the 2019 cohort window: pre-2019 we only hold reconstructed enacted laws (no
        # introductions, no baseline), so their rate is 100%-by-construction noise — drop them.
        if b < 2019:
            continue
        c = ce.get(b, {"total": 0, "enacted": 0})
        bl = base.get(b, {"introduced": 0, "enacted": 0})
        ce_rate = round(c["enacted"] / c["total"], 4) if c["total"] else None
        base_rate = round(bl["enacted"] / bl["introduced"], 4) if bl["introduced"] else None
        rows.append(StateCycleRow(
            biennium=f"{b}–{b + 1}", start_year=b,
            ce_total=c["total"], ce_enacted=c["enacted"], ce_rate=ce_rate,
            baseline_introduced=bl["introduced"], baseline_enacted=bl["enacted"], baseline_rate=base_rate,
            gap=(round(ce_rate - base_rate, 4) if ce_rate is not None and base_rate is not None else None),
            in_flight=(b == current_biennium),
        ))
    return rows


_SUMMARY_KEYS = {
    "person_id", "name", "party", "chamber", "district", "active", "states",
    "primary_sponsorships", "cosponsorships", "total_ce_bills", "enacted_count",
    "success_rate", "instruments", "materials",
}


@router.get("/champions", response_model=list[ChampionSummary])
async def get_champions(
    state: str | None = None,
    active_only: bool = True,
    limit: int = Query(default=500, le=3000),
):
    """CE champion roster (slim — no per-bill list). Active (in-office) only by default, sorted by
    lead sponsorships. Filter by `state`. Expand a champion via /champions/{person_id} for their bills."""
    champs = _roster()
    if active_only:
        champs = [c for c in champs if c.get("active")]
    if state:
        st = state.upper()
        champs = [c for c in champs if st in (c.get("states") or [])]
    champs = sorted(
        champs,
        key=lambda c: (c.get("primary_sponsorships", 0), c.get("total_ce_bills", 0)),
        reverse=True,
    )

    def _summary(c: dict) -> ChampionSummary:
        d = {k: c.get(k) for k in _SUMMARY_KEYS if k in c}
        # current_role.district may be numeric in the dump — normalize to string.
        if d.get("district") is not None:
            d["district"] = str(d["district"])
        return ChampionSummary(**d)

    return [_summary(c) for c in champs[:limit]]


@router.get("/champions/{person_id:path}/bills", response_model=list[ChampionBill])
async def get_champion_bills(person_id: str):
    """The bills behind a champion — each with its source_url (the link-to-source rule)."""
    champ = next((c for c in _roster() if c.get("person_id") == person_id), None)
    if champ is None:
        raise HTTPException(status_code=404, detail="champion not found")
    return [ChampionBill(**b) for b in champ.get("bills", [])]
