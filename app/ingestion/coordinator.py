import asyncio
import hashlib
import re
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import DateTime, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ingestion.docket import is_docket_shell
from app.ingestion.federal_register import FederalRegisterClient
from app.ingestion.legiscan import ALL_STATES, LegiScanClient, compute_bill_hash
from app.ingestion.openstates import OpenStatesClient
from app.models import Bill, BillChange, FederalAction

log = structlog.get_logger()


def _legiscan_status_map(status_id: int) -> str:
    """Map LegiScan numeric status to human-readable string."""
    return {
        1: "introduced",
        2: "in_committee",
        3: "passed_chamber",
        4: "passed",
        5: "enacted",
        6: "vetoed",
        7: "failed",
    }.get(status_id, "unknown")


def _parse_date(val: str | None) -> date | None:
    if not val or val == "0000-00-00":
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


def _build_openstates_queries() -> list[str]:
    """Derive Open States search queries from epr_keywords.json.

    Pulls multi-word phrases from high-signal categories. Single words and
    short acronyms are skipped — they're too noisy for full-text legislative
    search and the keyword filter handles fine-grained matching post-ingest.
    """
    import json
    from pathlib import Path

    kw_path = Path(__file__).parent.parent.parent / "data" / "seed" / "epr_keywords.json"
    with open(kw_path) as f:
        kw = json.load(f)

    # These categories produce good legislative search terms.
    # Excluded: policy_mechanism (too broad), exclusion_keywords, federal_preemption,
    # procurement_and_incentives (too generic), resale_and_secondhand (too noisy).
    search_categories = [
        "primary_keywords",
        "material_keywords",
        "recycled_content_keywords",
        "deposit_return_keywords",
        "right_to_repair_keywords",
        "pfas_and_chemicals_keywords",
        "reuse_and_refill_keywords",
        "remanufacturing_keywords",
        "buy_clean_and_embodied_carbon_keywords",
        "repairability_and_durability_keywords",
        # Biological cycle of the circular economy — multi-word phrases are specific enough
        # to make good legislative search terms (e.g. "regenerative agriculture", "biopolymer").
        "biomaterials_keywords",
        "soil_health_and_regenerative_ag_keywords",
        # Adjacent subjects (water leakage / biodiversity) — multi-word phrases only ("marine
        # debris", "water reuse", "ecosystem restoration") make good legislative search terms.
        "water_and_waterways_keywords",
        "biodiversity_keywords",
    ]

    seen: set[str] = set()
    queries: list[str] = []
    for cat in search_categories:
        for term in kw.get(cat, []):
            # Multi-word phrases only — single words are too noisy for search
            if len(term.split()) >= 2 and term.lower() not in seen:
                seen.add(term.lower())
                queries.append(term)

    return queries


OPENSTATES_EPR_QUERIES = _build_openstates_queries()


# US Congress master-list prefilter.
#
# Every other jurisdiction in ALL_STATES is a state legislature whose current-session master list
# runs a few hundred bills, so the loop below fetches them all and lets HaikuClassifier judge.
# Congress does not fit that shape: the 119th Congress master list is ~18,500 bills, and at one
# getBill call each a single federal run would blow max_legiscan_calls_per_run (5000) nearly 4x
# over and starve every state behind it. So federal bills are gated on the master-list summary —
# which already carries title + description — before any call is spent.
#
# This net is deliberately NOT classification.keywords.KeywordFilter. That filter is tuned for
# state bills, where a long description gives multi-word phrases ("battery recycling", "recycling
# infrastructure") room to land; its vocabulary contains no bare "recycling"/"compost"/"battery"
# on purpose, because single words would swamp a rich state corpus. Against a one-line federal
# summary those phrases almost never hit: KeywordFilter passes only 165 of 18,470 and drops the
# Recycling Infrastructure and Accessibility Act, the COMPOST Act and the CIRCLE Act at score 0.00.
#
# The gate is therefore broad and single-word by design — it is a CHEAP recall net, not a
# precision layer. HaikuClassifier still judges everything that passes, so a false positive costs
# one classification while a false negative costs a bill we never learn about. Exclusion terms are
# deliberately not applied here for the same reason (they reject e.g. the USA Batteries Act on a
# passing "Superfund" mention). Measured on the 119th Congress: 195 of 18,470 pass (1.1%), with no
# bill carrying obvious circular-economy vocabulary left behind.
#
# The leading \b is load-bearing. Terms match as PREFIXES so that "recycl" catches
# recycling/recyclable, but without a word boundary "tire" also matches reTIREd and
# reTIREes, "litter" matches glitter, and "scrap" matches scrapbook. Unanchored, the net
# passed 426 bills including the Equal COLA Act and the Retired Pay Restoration Act;
# anchored the same terms pass 182 — 244 false positives dropped, zero real ones — and the
# repair phrases below add the 13 that bring the total to 195.
FEDERAL_PREFILTER = re.compile(
    r"\b(?:"
    r"recycl|compost|circular econom|extended producer|product stewardship|e-waste"
    r"|electronic waste|single.use|plastic|packaging|batter|right to repair|repairab"
    r"|refurbish|remanufactur|landfill|deposit return|bottle bill|textile|food waste"
    r"|organic waste|scrap|salvage|reuse|re-use|refill|take.back|takeback|pfas"
    r"|microplastic|critical mineral|solid waste|municipal waste|litter|marine debris"
    r"|biodegradab|compostab|end.of.life|second.hand|secondhand|tire|mattress|carpet"
    r"|solar panel|waste diversion|waste reduction|zero waste|recovered material"
    r"|recycled content|producer responsib"
    # Right-to-repair arrives titled as an ACT rather than as the phrase the state
    # vocabulary expects, so "repairab" alone misses the Fair Repair Act, the REPAIR Act
    # and the Farm Freedom to Repair Act. Bare "repair" would catch them but drags in 46
    # bridge/ship/levee/credit-repair bills; these phrase forms cost 13 and miss none.
    r"|fair repair|repair act|repair of consumer|repairing consumer"
    r")",
    re.IGNORECASE,
)

# Jurisdictions whose master list is prefiltered before spending a getBill call. Only US Congress
# today — state lists are small enough to ingest wholesale.
PREFILTERED_STATES = {"US"}


def _passes_federal_prefilter(summary: dict) -> bool:
    blob = f"{summary.get('title') or ''} {summary.get('description') or ''}"
    return bool(FEDERAL_PREFILTER.search(blob))

_STATE_NAME_TO_CODE = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "District of Columbia": "DC",
}


def _normalize_bill_number(identifier: str) -> str:
    if not identifier:
        return ""
    parts = identifier.strip().split(" ", 1)
    if len(parts) == 2:
        return f"{parts[0].upper()}-{parts[1].strip()}"
    return identifier.strip().upper()


def _normalize_legiscan_number(number: str) -> str:
    """LegiScan writes bill numbers UNSPACED ("HB4001"); OpenStates writes them spaced
    ("HB 4001"), which _normalize_bill_number turns into the dashed "HB-4001" the corpus
    stores. Split the alpha prefix off the digits so both sources land on ONE form —
    without this the two feeds can never recognize each other's rows and every overlapping
    bill is stored twice.
    """
    if not number:
        return ""
    n = number.strip().upper().replace(" ", "")
    m = re.match(r"^([A-Z]+)[-\s]?(\d.*)$", n)
    if not m:
        return n
    return f"{m.group(1)}-{m.group(2)}"


def _jurisdiction_to_state_code(jurisdiction: dict) -> str | None:
    jid = jurisdiction.get("id", "")
    m = re.search(r"/state:([a-z]{2})/", jid)
    if m:
        return m.group(1).upper()
    name = jurisdiction.get("name", "").strip()
    return _STATE_NAME_TO_CODE.get(name)


def _infer_openstates_status(bill_data: dict) -> str:
    # Enactment is detected from OpenStates' NORMALIZED action classifications, not the free-text
    # latest_action_description: every state phrases a signing differently ("Governor signed" in CO,
    # "Filed, Chapter ..." etc.), so text alone missed signatures and left signed bills stuck at an
    # upstream status — the daily-incremental staleness we had to backfill. The search cycle now
    # requests include=["actions"]; the dump-import path passes none and falls back to the text below.
    # NB: bill_data["classification"] is the BILL TYPE (['bill']/['resolution']) — never an action
    # signal — so we read each action's own `classification` list instead.
    action_classes = {
        c.lower()
        for a in (bill_data.get("actions") or [])
        for c in (a.get("classification") or [])
    }
    action = (bill_data.get("latest_action_description") or "").lower()

    if {"executive-signature", "became-law"} & action_classes or any(
        k in action for k in ("signed by governor", "chaptered", "became law")
    ):
        return "enacted"
    if "executive-veto" in action_classes or "vetoed" in action:
        return "vetoed"
    # Upstream stages keep the text heuristic (the bill-type classification checks here were always
    # no-ops, so this preserves prior behavior for non-enacted/non-vetoed bills).
    if any(k in action for k in ("failed", "died", "tabled")):
        return "failed"
    if any(k in action for k in ("passed", "adopted")):
        return "passed"
    if any(k in action for k in ("committee", "referred", "hearing")):
        return "in_committee"
    if any(k in action for k in ("concurred", "second reading", "third reading")):
        return "passed_chamber"
    return "introduced"


def _pick_source_url(sources: list[dict]) -> str | None:
    """Choose the most user-friendly source URL for the 'View Source' link.

    OpenStates lists multiple sources per bill in varying quality. Some states (e.g. TX)
    list an FTP link to a raw XML file first, which is useless to a human. Prefer an
    https/http web page; de-prioritise ftp:// and raw .xml/.json document links.
    """
    best: str | None = None
    best_rank = -1
    for src in sources:
        url = (src.get("url") or "").strip()
        if not url:
            continue
        low = url.lower()
        if low.startswith("https://") or low.startswith("http://"):
            rank = 1 if low.endswith((".xml", ".json", ".pdf")) else 2
        else:  # ftp:// and anything else
            rank = 0
        if rank > best_rank:
            best, best_rank = url, rank
    return best


def _compute_openstates_change_hash(bill_data: dict) -> str:
    key = (
        f"{bill_data.get('updated_at', '')}"
        f"-{bill_data.get('latest_action_date', '')}"
        f"-{bill_data.get('latest_action_description', '')}"
    )
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class IngestionCoordinator:
    async def run_full_cycle(
        self,
        db: AsyncSession,
        state_filter: str | None = None,
        max_api_calls: int | None = None,
    ) -> dict:
        from app.config import settings as _settings
        call_limit = max_api_calls if max_api_calls is not None else _settings.max_legiscan_calls_per_run
        api_calls = 0
        quota_exhausted = False
        stopped_at_state: str | None = None

        states = [state_filter.upper()] if state_filter else ALL_STATES
        total_new = total_updated = total_unchanged = total_filtered = 0

        async with LegiScanClient() as legiscan:
            for state in states:
                if api_calls >= call_limit:
                    quota_exhausted = True
                    stopped_at_state = state
                    log.warning(
                        "legiscan_quota_exhausted",
                        calls_made=api_calls,
                        limit=call_limit,
                        stopped_at_state=state,
                        remaining_states=states[states.index(state):],
                    )
                    break

                try:
                    # Get current session only — avoids fetching stale bills
                    # from prior sessions that the free tier can't serve
                    sessions = await legiscan.get_session_list(state)
                    api_calls += 1
                    current = next(
                        (s for s in sessions if s.get("special", 0) == 0
                         and s.get("year_end", s.get("year_start", 0)) >= date.today().year),
                        sessions[0] if sessions else None,
                    )
                    session_id = current["session_id"] if current else None
                    log.debug("session_selected", state=state, session_id=session_id,
                              session_name=current.get("session_name") if current else None)
                    master = await legiscan.get_master_list(state, session_id=session_id)
                    api_calls += 1
                except Exception as e:
                    log.error("master_list_failed", state=state, error=str(e))
                    continue

                # Fetch stored change hashes for this state
                result = await db.execute(
                    select(Bill.legiscan_bill_id, Bill.change_hash).where(
                        Bill.state == state,
                        Bill.legiscan_bill_id.isnot(None),
                    )
                )
                stored_hashes: dict[int, str] = {
                    row.legiscan_bill_id: row.change_hash or ""
                    for row in result.all()
                }

                for summary in master.values():
                    # LegiScan keys getMasterList by a 0-based INDEX, not by bill_id — the
                    # real id lives in summary["bill_id"]. Using the key fed getBill(0),
                    # getBill(1), ... which every time failed "Unknown bill id", so no
                    # master-list bill was ever actually ingested.
                    if not isinstance(summary, dict):
                        continue
                    bill_id = summary.get("bill_id")
                    if not bill_id:
                        continue
                    bill_id = int(bill_id)

                    # Congress is too large to fetch wholesale — gate on the master-list
                    # summary before spending a getBill call. See FEDERAL_PREFILTER.
                    if state in PREFILTERED_STATES and not _passes_federal_prefilter(summary):
                        total_filtered += 1
                        continue

                    incoming_hash = summary.get("change_hash", "")

                    if stored_hashes.get(bill_id) == incoming_hash:
                        total_unchanged += 1
                        continue

                    if api_calls >= call_limit:
                        quota_exhausted = True
                        stopped_at_state = state
                        log.warning(
                            "legiscan_quota_exhausted_mid_state",
                            calls_made=api_calls,
                            limit=call_limit,
                            stopped_at_state=state,
                        )
                        break

                    # Fetch full bill details
                    try:
                        bill_data = await legiscan.get_bill(bill_id)
                        api_calls += 1
                    except Exception as e:
                        err = str(e)
                        if "Unknown bill id" in err or "Invalid bill id" in err:
                            # Persist a stub row so future runs see this bill_id
                            # as "unchanged" and skip the API call entirely.
                            # This avoids burning through free-tier quota on IDs
                            # LegiScan won't serve (prior-session or paywalled bills).
                            stub = insert(Bill).values(
                                legiscan_bill_id=bill_id,
                                state=state,
                                bill_number=f"UNAVAILABLE-{bill_id}",
                                title="[unavailable on free tier]",
                                change_hash=incoming_hash,
                                last_fetched_at=datetime.now(timezone.utc),
                            )
                            stub = stub.on_conflict_do_update(
                                index_elements=["legiscan_bill_id"],
                                set_={"change_hash": stub.excluded.change_hash,
                                      "last_fetched_at": stub.excluded.last_fetched_at},
                            )
                            await db.execute(stub)
                            log.debug("get_bill_skipped", bill_id=bill_id)
                        else:
                            log.warning("get_bill_failed", bill_id=bill_id, error=err)
                        continue

                    is_new = bill_id not in stored_hashes
                    await self._upsert_legiscan_bill(db, bill_data, state)
                    if is_new:
                        total_new += 1
                    else:
                        total_updated += 1

                await db.commit()
                log.info("state_ingested", state=state, new=total_new, updated=total_updated,
                         filtered=total_filtered,
                         api_calls=api_calls, quota_remaining=call_limit - api_calls)

                if quota_exhausted:
                    break

        return {
            "new": total_new,
            "updated": total_updated,
            "unchanged": total_unchanged,
            "filtered": total_filtered,
            "api_calls": api_calls,
            "quota_exhausted": quota_exhausted,
            "stopped_at_state": stopped_at_state,
        }

    async def _upsert_legiscan_bill(
        self, db: AsyncSession, bill_data: dict, state: str
    ) -> None:
        bill_id = bill_data.get("bill_id")
        if not bill_id:
            return

        status_id = bill_data.get("status", 0)
        status_str = _legiscan_status_map(status_id)
        bill_number = _normalize_legiscan_number(bill_data.get("bill_number") or "")

        # Build URLs from texts list
        source_url: str | None = None
        texts = bill_data.get("texts", [])
        if texts:
            source_url = texts[-1].get("state_link") or texts[-1].get("url")

        # Dedup (mirror of the cross-reference in _upsert_openstates_bill): an Open States or
        # historical-seed row may already describe this bill with legiscan_bill_id NULL. The
        # ON CONFLICT below keys on legiscan_bill_id, so that row would NOT conflict and we
        # would insert a second copy. Adopt the existing row instead.
        #
        # The match MUST be session-scoped: states reuse bill numbers every session, so
        # (state, bill_number) is not unique — MD SB-901 legitimately names 7 different bills
        # across 2020-2026. Restrict to rows whose reference date falls in this bill's session
        # year range, the same guard scripts/refresh_status_legiscan.py uses.
        adopted = False
        session = bill_data.get("session") or {}
        year_start = session.get("year_start")
        year_end = session.get("year_end") or year_start
        if bill_number and year_start:
            ref_date = func.coalesce(Bill.status_date, Bill.last_action_date)
            existing = (await db.execute(
                select(Bill).where(
                    Bill.state == state,
                    Bill.bill_number == bill_number,
                    Bill.legiscan_bill_id.is_(None),
                    ref_date.isnot(None),
                    func.extract("year", ref_date).between(int(year_start), int(year_end)),
                ).order_by(ref_date.desc()).limit(1)
            )).scalar_one_or_none()
            if existing is not None:
                existing.legiscan_bill_id = bill_id
                existing.change_hash = bill_data.get("change_hash")
                existing.last_fetched_at = datetime.now(timezone.utc)
                # Only fill gaps — do not clobber an enriched row with thinner LegiScan data.
                if not existing.source_url:
                    existing.source_url = source_url
                if not existing.description:
                    existing.description = bill_data.get("description")
                adopted = True
                log.debug("legiscan_cross_referenced", state=state, bill_number=bill_number,
                          legiscan_bill_id=bill_id, bill_row_id=existing.id)
        if adopted:
            return

        stmt = insert(Bill).values(
            legiscan_bill_id=bill_id,
            state=state,
            bill_number=bill_number,
            title=bill_data.get("title"),
            description=bill_data.get("description"),
            status=status_str,
            status_date=_parse_date(bill_data.get("status_date")),
            last_action_date=_parse_date(bill_data.get("last_action_date")),
            change_hash=bill_data.get("change_hash"),
            source_url=source_url,
            last_fetched_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["legiscan_bill_id"],
            set_={
                "state": stmt.excluded.state,
                "bill_number": stmt.excluded.bill_number,
                "title": stmt.excluded.title,
                "status": stmt.excluded.status,
                "status_date": stmt.excluded.status_date,
                "last_action_date": stmt.excluded.last_action_date,
                "change_hash": stmt.excluded.change_hash,
                "source_url": stmt.excluded.source_url,
                "last_fetched_at": stmt.excluded.last_fetched_at,
            },
        )
        await db.execute(stmt)

    async def _upsert_openstates_bill(
        self, db: AsyncSession, bill_data: dict, state: str
    ) -> str:
        try:
            openstates_id = bill_data.get("id")
            if not openstates_id:
                log.warning("openstates_bill_missing_id")
                return "skipped"

            raw_identifier = bill_data.get("identifier", "")
            bill_number = _normalize_bill_number(raw_identifier)
            if not bill_number:
                log.warning("openstates_bill_missing_identifier", openstates_id=openstates_id)
                return "skipped"

            # Dedup: if LegiScan already owns this (state, bill_number), cross-reference only.
            #
            # Session-scoped, for two reasons. (1) States reuse bill numbers every session, so
            # (state, bill_number) names several DIFFERENT bills — matching on the pair alone
            # would staple this bill's openstates_id onto an unrelated row from another year.
            # (2) scalar_one_or_none() RAISES on multiple matches, so the unscoped query becomes
            # a hard error the moment LegiScan holds two sessions of the same number.
            # Pick the single closest row by reference date, within a 1-year window (sessions
            # commonly span two calendar years, e.g. a 2025-2026 regular session).
            ref_year = _parse_date(bill_data.get("latest_action_date"))
            existing = None
            if ref_year is not None:
                cand_ref = func.coalesce(Bill.status_date, Bill.last_action_date)
                distance = func.abs(
                    func.extract("epoch", func.cast(cand_ref, DateTime))
                    - func.extract("epoch", func.cast(ref_year, DateTime))
                )
                existing = (await db.execute(
                    select(Bill).where(
                        Bill.state == state,
                        Bill.bill_number == bill_number,
                        Bill.legiscan_bill_id.isnot(None),
                        cand_ref.isnot(None),
                        distance <= 366 * 24 * 3600,
                    ).order_by(distance.asc()).limit(1)
                )).scalar_one_or_none()
            if existing is not None:
                if existing.openstates_id == openstates_id:
                    return "cross_referenced"
                existing.openstates_id = openstates_id
                existing.last_fetched_at = datetime.now(timezone.utc)
                log.debug("openstates_cross_referenced",
                          state=state, bill_number=bill_number,
                          legiscan_bill_id=existing.legiscan_bill_id)
                return "cross_referenced"

            # Hash check for idempotency on Open States-owned bills.
            # Also re-process when the stored row is missing source_url so the
            # backfill (now that search requests include=sources) can self-heal
            # rows ingested before the source link was captured.
            new_hash = _compute_openstates_change_hash(bill_data)
            hash_result = await db.execute(
                select(
                    Bill.id, Bill.status, Bill.ce_relevant,
                    Bill.change_hash, Bill.source_url,
                ).where(Bill.openstates_id == openstates_id)
            )
            stored_row = hash_result.one_or_none()
            if stored_row and stored_row.change_hash == new_hash and stored_row.source_url:
                return "skipped"

            # Extract fields
            abstracts = bill_data.get("abstracts", [])
            description = abstracts[0].get("abstract") if abstracts else None
            sources = bill_data.get("sources", [])
            source_url = _pick_source_url(sources)
            last_action_date = _parse_date(bill_data.get("latest_action_date"))
            status = _infer_openstates_status(bill_data)

            # A pre-filing docket shell (MA HD-/SD-, KY BR- with no action yet) is the same text as
            # the bill we already track under its filed number — storing it double-counts the bill
            # and, being action-less, leaves a permanently dateless row. Skipped at the door rather
            # than ingested-then-hidden; it lands normally once it picks up an action. See
            # app/ingestion/docket.py.
            if is_docket_shell(state, bill_number, last_action_date):
                log.debug("openstates_docket_shell_skipped",
                          state=state, bill_number=bill_number, openstates_id=openstates_id)
                return "skipped"

            stmt = insert(Bill).values(
                openstates_id=openstates_id,
                state=state,
                bill_number=bill_number,
                title=bill_data.get("title"),
                description=description,
                status=status,
                status_date=last_action_date,
                last_action_date=last_action_date,
                source_url=source_url,
                change_hash=new_hash,
                last_fetched_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["openstates_id"],
                set_={
                    "status": stmt.excluded.status,
                    "status_date": stmt.excluded.status_date,
                    "last_action_date": stmt.excluded.last_action_date,
                    "source_url": stmt.excluded.source_url,
                    "change_hash": stmt.excluded.change_hash,
                    "last_fetched_at": stmt.excluded.last_fetched_at,
                },
            )
            await db.execute(stmt)

            # Emit a status-change event for an already-tracked, relevant bill that just advanced, so
            # run_alert_dispatch can notify matching subscribers (subscription_matches_bill: states +
            # topics + materials + confidence floor, or a starred bill). Gated to:
            #   - existing rows only — a brand-new bill is the new-bill alert's job, not a status change;
            #   - ce_relevant only — don't alert on bills the classifier ruled out (NULL/False skips);
            #   - an actual status move — stored status differs from the freshly inferred one.
            # Every _infer_openstates_status value is in detector.SIGNIFICANT_STATUSES, so is_alert_worthy
            # accepts these. We deliberately do NOT emit a text_update here: the OpenStates change_hash is
            # an action-metadata hash (updated_at + latest action), not a bill-text hash, so it moves on
            # every action and would double each status alert with a misleading "text changed".
            if (
                stored_row is not None
                and stored_row.ce_relevant
                and stored_row.status != status
            ):
                db.add(
                    BillChange(
                        bill_id=stored_row.id,
                        change_type="status_change",
                        old_value={"status": stored_row.status},
                        new_value={"status": status},
                    )
                )

            return "upserted"

        except Exception as e:
            log.error("openstates_upsert_failed",
                      openstates_id=bill_data.get("id"),
                      state=state,
                      error=str(e))
            return "skipped"

    async def run_openstates_cycle(
        self,
        db: AsyncSession,
        state_filter: str | None = None,
        updated_since: datetime | None = None,
        max_api_calls: int | None = None,
    ) -> dict:
        from app.config import settings as _settings

        call_limit = (
            max_api_calls if max_api_calls is not None
            else _settings.max_openstates_calls_per_run
        )
        delay = _settings.openstates_request_delay_seconds

        states = [state_filter.upper()] if state_filter else ALL_STATES
        new = cross_referenced = skipped = errors = 0
        api_calls = 0
        quota_exhausted = False
        throttled = False
        consecutive_429 = 0
        # OpenStates free tier throttles hard; once it starts returning 429 it tends to
        # keep doing so. Stop the run after this many consecutive 429s rather than grinding
        # through the whole query set getting rejected (the run stays resumable via stopped_at).
        THROTTLE_STOP = 3
        stopped_at: dict | None = None

        async with OpenStatesClient() as client:
            for query in OPENSTATES_EPR_QUERIES:
                if quota_exhausted:
                    break
                for state in states:
                    if api_calls >= call_limit:
                        quota_exhausted = True
                        stopped_at = {"query": query, "state": state, "page": 1}
                        log.warning(
                            "openstates_quota_exhausted",
                            calls_made=api_calls,
                            limit=call_limit,
                            stopped_at=stopped_at,
                        )
                        break

                    page = 1
                    while True:
                        if api_calls >= call_limit:
                            quota_exhausted = True
                            stopped_at = {"query": query, "state": state, "page": page}
                            log.warning(
                                "openstates_quota_exhausted",
                                calls_made=api_calls,
                                limit=call_limit,
                                stopped_at=stopped_at,
                            )
                            break
                        try:
                            response = await client.search_bills(
                                query=query,
                                jurisdiction=state.lower(),
                                updated_since=updated_since,
                                page=page,
                                per_page=20,
                            )
                            api_calls += 1
                            consecutive_429 = 0
                        except Exception as e:
                            errors += 1
                            status = getattr(getattr(e, "response", None), "status_code", None)
                            if status == 429:
                                consecutive_429 += 1
                                log.warning("openstates_throttled_429",
                                            query=query, state=state, page=page,
                                            consecutive=consecutive_429)
                                if consecutive_429 >= THROTTLE_STOP:
                                    quota_exhausted = True
                                    throttled = True
                                    stopped_at = {"query": query, "state": state,
                                                  "page": page, "reason": "rate_limited"}
                                    log.error("openstates_stopped_rate_limited",
                                              consecutive=consecutive_429,
                                              calls_made=api_calls, stopped_at=stopped_at)
                            else:
                                log.error("openstates_search_failed",
                                          query=query, state=state, page=page, error=str(e))
                            break

                        results = response.get("results", [])
                        pagination = response.get("pagination", {})

                        if not results:
                            break

                        for bill_summary in results:
                            outcome = await self._upsert_openstates_bill(db, bill_summary, state)
                            if outcome == "upserted":
                                new += 1
                            elif outcome == "cross_referenced":
                                cross_referenced += 1
                            else:
                                skipped += 1

                        current_page = pagination.get("page", page)
                        max_page = pagination.get("max_page", 1)
                        if current_page >= max_page:
                            break
                        page += 1
                        # Inter-page pacing: pages within a query were previously fetched
                        # back-to-back with no delay, which burst past the rate limit.
                        await asyncio.sleep(delay)

                    await db.commit()
                    log.debug("openstates_query_state_done",
                              query=query, state=state,
                              new=new, cross_referenced=cross_referenced)
                    if quota_exhausted:
                        break
                    await asyncio.sleep(delay)

        return {
            "openstates_new": new,
            "openstates_cross_referenced": cross_referenced,
            "openstates_skipped": skipped,
            "openstates_errors": errors,
            "openstates_api_calls": api_calls,
            "openstates_quota_exhausted": quota_exhausted,
            "openstates_throttled": throttled,
            "openstates_stopped_at": stopped_at,
        }

    async def run_federal_cycle(self, db: AsyncSession) -> dict:
        new_count = 0
        new_actions: list[FederalAction] = []
        async with FederalRegisterClient() as fr:
            docs = await fr.search_all_epr_terms()

        for doc in docs:
            doc_num = doc.get("document_number")
            if not doc_num:
                continue
            # Check if already stored
            existing = await db.execute(
                select(FederalAction).where(
                    FederalAction.federal_register_document_number == doc_num
                )
            )
            if existing.scalar_one_or_none():
                continue

            agencies = doc.get("agencies", [])
            agency_name = agencies[0].get("name", "") if agencies else ""

            action = FederalAction(
                federal_register_document_number=doc_num,
                agency=agency_name,
                title=doc.get("title"),
                action_type=doc.get("type", "").lower().replace(" ", "_"),
                published_date=_parse_date(doc.get("publication_date")),
                comment_deadline=_parse_date(doc.get("comments_close_on")),
                effective_date=_parse_date(doc.get("effective_on")),
                document_url=doc.get("html_url"),
                raw_data=doc,
            )
            db.add(action)
            new_actions.append(action)
            new_count += 1

        # Enrich the new actions: filter feed noise and score federal friction
        # (preemption_risk). Gated by the same flag as bill classification so dev
        # without an API key still ingests raw rows.
        classified = 0
        if new_actions and settings.enable_llm_classification:
            classified = await self._classify_federal_actions(new_actions)

        await db.commit()
        return {"new_federal_actions": new_count, "classified_federal_actions": classified}

    async def _classify_federal_actions(self, actions: list[FederalAction]) -> int:
        """Populate ce_relevant / preemption_risk / friction_type / instrument_type /
        ai_summary / material_categories on newly-ingested federal actions. Returns the
        number classified."""
        from app.classification.federal_classifier import FederalClassifier

        classifier = FederalClassifier()
        classified = 0
        for action in actions[: settings.max_haiku_calls_per_run]:
            try:
                abstract = (action.raw_data or {}).get("abstract", "") if action.raw_data else ""
                fr = await classifier.classify(
                    title=action.title or "",
                    agency=action.agency or "",
                    action_type=action.action_type or "",
                    abstract=abstract,
                )
            except Exception as e:
                log.error("federal_classify_failed", doc=action.federal_register_document_number,
                          error=str(e), error_type=type(e).__name__)
                continue
            # in_scope applies the confidence floor (mirrors the state-bill relevance gate);
            # a low-confidence is_relevant guess no longer counts as relevant.
            action.ce_relevant = fr.in_scope
            action.preemption_risk = fr.preemption_risk
            action.friction_type = fr.friction_type
            action.instrument_type = fr.instrument_type
            action.ai_summary = fr.summary
            action.material_categories = fr.material_categories
            classified += 1
        log.info("federal_classify_done", total=len(actions), classified=classified)
        return classified
