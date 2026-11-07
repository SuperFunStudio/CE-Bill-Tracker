"""Daily status sync for tracked US state bills, from LegiScan master lists.

Why this exists: OpenStates is our discovery source, but its free tier allows ~250 calls/day, so
the nightly rotation takes ~2 months to come back round to any one query. A bill's status only
refreshed when one of its queries came back round, so signings went unnoticed for weeks: CA AB-864
was chaptered 2026-09-30, caught up 2026-11-07, and the "status changed" email went out 38 days
late. On 2026-11-07, 219 of 287 open, in-scope US bills hadn't been re-fetched in 90+ days.

LegiScan's `getMasterList` returns EVERY bill in a session with its status code, status date and
last action, in one call. So one `getSessionList` plus one or two `getMasterList` calls per state
(~150 calls/day, well inside the free tier's 30k/month) re-check the status of every tracked bill
daily. Status only — this module never ingests new bills or classifies anything.

(The old "free tier returns WV data for every state" note in config.py/legiscan.py turned out to be
the master-list index bug fixed in 337fdf9; verified 2026-11-07 that CA, RI and US return their
own sessions.)

Safety rules, because a wrong match would put another bill's status on ours:
  * bill numbers are matched within a session whose years contain the bill's last action (CO/DC
    numbers that carry a 2-digit year must match the session year exactly);
  * the titles must overlap (strongly so when the bill's last action falls in the year before
    the session starts, i.e. a prefile);
  * status only moves forward (introduced < committee < passed one chamber < passed/enrolled <
    enacted), or to vetoed/failed from a non-final status — never backwards, and never off enacted;
  * we only take LegiScan's word when its last action is at least as recent as ours.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BillChange

log = structlog.get_logger()

# LegiScan's numeric status codes (https://legiscan.com/gaits/documentation/legiscan).
LEGISCAN_STATUS = {
    1: "introduced",
    2: "passed_chamber",  # "Engrossed": passed its chamber of origin
    3: "enrolled",        # passed both chambers
    4: "enacted",         # "Passed": signed / chaptered / became law
    5: "vetoed",
    6: "failed",
}

# Forward order of our status vocabulary (see coordinator._infer_openstates_status).
_RANK = {
    "introduced": 0,
    "in_committee": 1,
    "passed_chamber": 2,
    "passed": 3,
    "enrolled": 3,
    "enacted": 4,
    "signed": 4,
}
FINAL = {"enacted", "signed", "vetoed", "failed"}

_NUM_RE = re.compile(r"^([A-Z]+)(?:(\d{2})-)?0*(\d+)$")
_WORD_RE = re.compile(r"[a-z]{4,}")


def parse_number(num: str | None) -> tuple[str, int | None, int] | None:
    """`HB-25-1059` -> ("HB", 25, 1059); `H.B.-27` -> ("HB", None, 27); `AB864` -> ("AB", None, 864).

    Our numbers come from OpenStates (`AB-864`, CO `HB-25-1059`, DC `B-24-0534`, UT `H.B.-27`);
    LegiScan's are compact (`AB864`, `HB1059`, DC `B24-0534`). Dots and spaces are dropped; the
    first hyphen after the prefix is dropped too so the optional `yy-` group can be told apart.
    """
    if not num:
        return None
    raw = num.upper().replace(".", "").replace(" ", "")
    raw = re.sub(r"^([A-Z]+)-", r"\1", raw)
    m = _NUM_RE.match(raw)
    if not m:
        return None
    prefix, yy, n = m.groups()
    return prefix, (int(yy) if yy else None), int(n)


def is_resolution(prefix: str) -> bool:
    """HR, SR, HCR, SCR, HJR, SJR, AJR, HRES, LR... State bills never end in R (HB, SB, AB, HF, LD,
    LB, A, S, H, B), so a trailing R / RES marks a resolution. Joint resolutions can carry the force
    of law in a few states, but calling them "passed" rather than "enacted" errs on the safe side."""
    return prefix.endswith("R") or prefix.endswith("RES")


def _words(title: str | None) -> set[str]:
    return set(_WORD_RE.findall((title or "").lower()))


def title_overlap(a: str | None, b: str | None) -> float | None:
    """Share of the shorter title's words found in the other. None when either has no words."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return None
    return len(wa & wb) / min(len(wa), len(wb))


TITLE_MIN = 0.5          # session year matches
TITLE_MIN_PREFILE = 0.8  # bill's last action is the year before the session starts


@dataclass
class TrackedBill:
    id: int
    state: str
    bill_number: str
    title: str | None
    status: str | None
    last_action_date: date | None
    legiscan_bill_id: int | None


@dataclass
class StatusUpdate:
    bill: TrackedBill
    legiscan_bill_id: int
    new_status: str | None       # None = status unchanged, only dates / id refreshed
    status_date: date | None
    last_action_date: date | None
    last_action: str | None


def _parse_date(s) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def should_move(old: str | None, new: str) -> bool:
    """Forward-only status rule. See module docstring."""
    old = old or "introduced"
    if old == new or old in ("enacted", "signed"):
        return False
    if new in ("vetoed", "failed"):
        return old not in FINAL
    if old in FINAL:  # vetoed/failed -> enacted can happen (override); otherwise stay put
        return new == "enacted" and old == "vetoed"
    return _RANK.get(new, -1) > _RANK.get(old, -1)


def plan_updates(
    bills: list[TrackedBill], master: dict, session: dict
) -> tuple[list[StatusUpdate], dict]:
    """Match tracked bills against one LegiScan session master list. Pure; no I/O.

    `master` is getMasterList's dict minus the "session" key; `session` is that key's value.
    Returns (updates, counters).
    """
    start, end = session.get("year_start"), session.get("year_end")
    counts = {"matched": 0, "year_mismatch": 0, "title_mismatch": 0, "older_than_ours": 0}
    if not start or not end:
        return [], counts
    start, end = int(start), int(end)

    by_key: dict[tuple[str, int], list[dict]] = {}
    for item in master.values():
        if not isinstance(item, dict):
            continue
        p = parse_number(item.get("number"))
        if p:
            by_key.setdefault((p[0], p[2]), []).append(item)

    updates: list[StatusUpdate] = []
    for b in bills:
        p = parse_number(b.bill_number)
        if not p or b.last_action_date is None:
            continue
        prefix, yy, n = p
        cands = by_key.get((prefix, n))
        if not cands:
            continue
        year = b.last_action_date.year
        if yy is not None:
            if not (start <= 2000 + yy <= end):
                counts["year_mismatch"] += 1
                continue
            need = TITLE_MIN
        elif start <= year <= end + 1:  # +1: signed/chaptered after the session closed
            need = TITLE_MIN
        elif year == start - 1:
            need = TITLE_MIN_PREFILE
        else:
            counts["year_mismatch"] += 1
            continue

        item = None
        for c in cands:
            # LegiScan's `title` and `description` are worded differently per state; our title
            # (from OpenStates) may echo either, so take the better overlap.
            ovs = [o for o in (title_overlap(b.title, c.get("title")),
                               title_overlap(b.title, c.get("description"))) if o is not None]
            ov = max(ovs) if ovs else None
            if ov is None or ov >= need:
                item = c
                break
        if item is None:
            counts["title_mismatch"] += 1
            continue
        counts["matched"] += 1

        ls_last = _parse_date(item.get("last_action_date"))
        if b.last_action_date and ls_last and ls_last < b.last_action_date:
            counts["older_than_ours"] += 1
            continue

        mapped = LEGISCAN_STATUS.get(item.get("status"))
        if mapped == "enacted" and is_resolution(prefix):
            mapped = "passed"  # an adopted resolution isn't a law; matches the OpenStates mapping
        new_status = mapped if mapped and should_move(b.status, mapped) else None
        newer_dates = ls_last is not None and ls_last != b.last_action_date
        try:
            lid = int(item.get("bill_id"))
        except (TypeError, ValueError):
            continue
        if new_status or newer_dates or b.legiscan_bill_id is None:
            updates.append(StatusUpdate(
                bill=b,
                legiscan_bill_id=lid,
                new_status=new_status,
                status_date=_parse_date(item.get("status_date")) if new_status else None,
                last_action_date=ls_last if newer_dates else None,
                last_action=item.get("last_action"),
            ))
    return updates, counts


_SELECT_TRACKED = text(
    "select id, state, bill_number, title, status, last_action_date, legiscan_bill_id "
    "from bills where region = 'US' and ce_relevant = true and state ~ '^[A-Z]{2}$' "
    "and state <> 'US' and coalesce(status, 'introduced') not in ('enacted','signed','vetoed','failed') "
    "and last_action_date >= :since"
)


async def run_legiscan_status_sync(
    db: AsyncSession,
    client,
    states: list[str] | None = None,
    dry_run: bool = False,
    lookback_days: int = 800,
) -> dict:
    """Refresh the status of every open, in-scope US state bill from LegiScan master lists.

    Emits a `status_change` BillChange per forward move (picked up by run_alert_dispatch, which
    still applies the 45-day stale-action gate). Stores the LegiScan bill id on matched rows,
    which also gives the text-refresh ladder a trusted id to fetch text with.
    """
    since = date.fromordinal(date.today().toordinal() - lookback_days)
    rows = (await db.execute(_SELECT_TRACKED, {"since": since})).all()
    tracked: dict[str, list[TrackedBill]] = {}
    for r in rows:
        if states and r.state not in states:
            continue
        tracked.setdefault(r.state, []).append(TrackedBill(*r))

    used_ids = {
        x for (x,) in (await db.execute(
            text("select legiscan_bill_id from bills where legiscan_bill_id is not null")
        )).all()
    }

    summary = {"states": 0, "api_calls": 0, "tracked": len(rows), "status_changes": 0,
               "dates_refreshed": 0, "ids_stored": 0, "errors": 0,
               "matched": 0, "year_mismatch": 0, "title_mismatch": 0, "older_than_ours": 0}
    planned: list[dict] = []
    now = datetime.now(timezone.utc)

    for state, bills in sorted(tracked.items()):
        years = {b.last_action_date.year for b in bills if b.last_action_date}
        try:
            sessions = await client.get_session_list(state)
            summary["api_calls"] += 1
        except Exception as e:  # noqa: BLE001 — one state must not stop the others
            summary["errors"] += 1
            log.warning("legiscan_status_sessions_failed", state=state, error=str(e))
            continue
        wanted = [
            s for s in sessions
            if s.get("year_start") and s.get("year_end")
            and any(int(s["year_start"]) - 1 <= y <= int(s["year_end"]) + 1 for y in years)
        ]
        wanted.sort(key=lambda s: (-int(s["year_end"]), int(s.get("special") or 0)))
        summary["states"] += 1
        remaining = list(bills)
        for sess in wanted[:3]:
            if not remaining:
                break
            try:
                master = await client.get_master_list(state, session_id=sess.get("session_id"))
                summary["api_calls"] += 1
            except Exception as e:  # noqa: BLE001
                summary["errors"] += 1
                log.warning("legiscan_status_masterlist_failed", state=state,
                            session_id=sess.get("session_id"), error=str(e))
                continue
            updates, counts = plan_updates(remaining, master, sess)
            for k, v in counts.items():
                summary[k] += v
            done = {u.bill.id for u in updates}
            remaining = [b for b in remaining if b.id not in done]
            for u in updates:
                b = u.bill
                store_id = b.legiscan_bill_id is None and u.legiscan_bill_id not in used_ids
                if u.new_status:
                    summary["status_changes"] += 1
                if u.last_action_date:
                    summary["dates_refreshed"] += 1
                if store_id:
                    summary["ids_stored"] += 1
                    used_ids.add(u.legiscan_bill_id)
                if u.new_status:
                    planned.append({"state": state, "bill": b.bill_number, "old": b.status,
                                    "new": u.new_status, "status_date": str(u.status_date),
                                    "last_action": u.last_action})
                if dry_run:
                    continue
                sets, params = [], {"id": b.id}
                if u.new_status:
                    sets += ["status = :status"]
                    params["status"] = u.new_status
                    if u.status_date:
                        sets += ["status_date = :sd"]
                        params["sd"] = u.status_date
                if u.last_action_date:
                    sets += ["last_action_date = :lad"]
                    params["lad"] = u.last_action_date
                if store_id:
                    sets += ["legiscan_bill_id = :lid"]
                    params["lid"] = u.legiscan_bill_id
                if sets:
                    await db.execute(text(f"update bills set {', '.join(sets)} where id = :id"), params)
                if u.new_status:
                    db.add(BillChange(
                        bill_id=b.id,
                        change_type="status_change",
                        old_value={"status": b.status},
                        new_value={"status": u.new_status, "source": "legiscan",
                                   "last_action": u.last_action},
                        detected_at=now,
                    ))
        if not dry_run:
            await db.commit()

    log.info("legiscan_status_sync_complete", dry_run=dry_run, **summary)
    summary["planned_changes"] = planned
    return summary
