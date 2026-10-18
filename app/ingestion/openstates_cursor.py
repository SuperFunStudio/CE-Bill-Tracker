"""Resumable sweep order for the nightly OpenStates cycle.

The cycle searches every EPR query against every state (305 queries x 52 states, ~16k calls), but the
OpenStates free tier starts returning 429 after ~250 calls a day. Restarting from query 1 every night
meant only the first five queries were ever searched. This module turns the sweep into a rotation that
picks up where the last run stopped, persisted in the ingestion_cursors row for source "openstates"
(migration 052).

Resuming alone is not enough: the nightly run used to search with updated_since = now - 2 days, so a
query that only comes round every couple of months would see two days of changes and miss everything
in between. So the cursor also records, per query, when its last complete sweep STARTED, and the next
sweep of that query searches from then. A sweep that spans several nights keeps the same `since` for
all of its states, so a state searched on night two does not lose the changes from night one.

Cursor JSON shape:
    {
      "position": {"query": str, "state": str, "page": int,
                   "started_at": iso, "since": iso | null} | null,
      "swept_at": {query: iso, ...}
    }
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterator

SOURCE = "openstates"


@dataclass
class Step:
    query: str
    state: str
    start_page: int
    since: datetime
    started_at: datetime
    last_state_of_query: bool


@dataclass
class SweepCursor:
    position: dict | None = None
    swept_at: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, data: dict | None) -> "SweepCursor":
        data = data or {}
        return cls(position=data.get("position"), swept_at=dict(data.get("swept_at") or {}))

    def dump(self) -> dict:
        return {"position": self.position, "swept_at": self.swept_at}

    def since_for(self, query: str, now: datetime, window_days: int, fallback_days: int) -> datetime:
        """Search window start for a fresh sweep of `query`: from its last sweep start, never
        narrower than the normal nightly window. A query never swept by the rotation (e.g. right after
        this cursor was introduced) looks back `fallback_days`."""
        floor = now - timedelta(days=window_days)
        last = self.swept_at.get(query)
        if last is None:
            return now - timedelta(days=fallback_days)
        return min(datetime.fromisoformat(last), floor)

    def steps(
        self, queries: list[str], states: list[str], now: datetime,
        window_days: int, fallback_days: int,
    ) -> Iterator[Step]:
        """Yield (query, state) steps for at most one full lap, starting at the saved position.

        A position whose query or state no longer exists (keyword list edited) restarts at the top.
        """
        start_qi, start_si, start_page = 0, 0, 1
        resumed: dict | None = None
        pos = self.position
        if pos and pos.get("query") in queries and pos.get("state") in states:
            start_qi = queries.index(pos["query"])
            start_si = states.index(pos["state"])
            start_page = int(pos.get("page") or 1)
            resumed = pos

        n = len(queries)
        for offset in range(n + 1):
            qi = (start_qi + offset) % n
            query = queries[qi]
            # The lap ends where it began: the extra iteration only finishes the states of the
            # resumed query that came before the resume point.
            if offset == n and start_si == 0:
                return
            if offset == 0 and resumed is not None:
                # A sweep already under way keeps the since/started_at it began with.
                since = _parse(resumed.get("since")) or self.since_for(
                    query, now, window_days, fallback_days)
                started_at = _parse(resumed.get("started_at")) or now
                first_si, page = start_si, start_page
            elif offset == n:
                # Back at the resumed query after a full lap: the states before the resume point
                # belong to a new sweep of it.
                since = self.since_for(query, now, window_days, fallback_days)
                started_at = now
                first_si, page = 0, 1
            else:
                since = self.since_for(query, now, window_days, fallback_days)
                started_at = now
                first_si, page = 0, 1
            last_si = len(states) - 1
            if offset == n:
                last_si = start_si - 1
            for si in range(first_si, last_si + 1):
                yield Step(query, states[si], page, since, started_at,
                           last_state_of_query=(si == len(states) - 1))
                page = 1

    def mark_stopped(self, step: Step, page: int) -> None:
        self.position = {
            "query": step.query, "state": step.state, "page": page,
            "started_at": step.started_at.isoformat(), "since": step.since.isoformat(),
        }

    def mark_done(self, step: Step, queries: list[str], states: list[str]) -> None:
        """Record that `step` finished and point the position at the step after it. Completing a
        query's last state stamps its sweep time, and the next query starts fresh (no carried
        since/started_at, so it gets its own window when it begins)."""
        if step.last_state_of_query:
            self.swept_at[step.query] = step.started_at.isoformat()
            next_query = queries[(queries.index(step.query) + 1) % len(queries)]
            self.position = {"query": next_query, "state": states[0], "page": 1,
                             "started_at": None, "since": None}
        else:
            self.position = {
                "query": step.query, "state": states[states.index(step.state) + 1], "page": 1,
                "started_at": step.started_at.isoformat(), "since": step.since.isoformat(),
            }


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
