"""
CourtListener Initial Seed Script

Backfills known active EPR litigation into litigation_cases.
For each discovered case: fetch docket → get parties → classify initial entries →
score preemption risk → upsert litigation_cases → create docket alert subscription.

Usage:
    ENABLE_COURTLISTENER=true python scripts/seed_courtlistener.py

Constraints:
    - 1-2 second delays between requests (CourtListener rate limiting)
    - Stops at max_cl_cases_per_seed_run (default: 50)
    - Skips if ENABLE_COURTLISTENER=false or no API token
"""
import asyncio
import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import structlog
from datetime import date, timedelta

log = structlog.get_logger()


async def seed():
    from app.config import settings

    if not settings.enable_courtlistener:
        log.info("seed_skipped", reason="ENABLE_COURTLISTENER=false")
        print("Set ENABLE_COURTLISTENER=true to run the seed.")
        return

    if not settings.courtlistener_api_token:
        log.error("seed_aborted", reason="No COURTLISTENER_API_TOKEN set")
        print("Set COURTLISTENER_API_TOKEN in your .env file.")
        return

    from app.database import AsyncSessionLocal
    from app.models import LitigationCase, LitigationEvent, CLAlertSubscription
    from app.ingestion.courtlistener import (
        CourtListenerClient,
        classify_litigation_event,
        score_preemption_risk,
        infer_challenge_type,
        infer_plaintiff_type,
        extract_docket_id_from_url,
        EPR_LITIGATION_QUERIES,
    )
    from app.ingestion.bill_matcher import match_case_to_bill
    from sqlalchemy import select

    import asyncio as _asyncio

    max_cases = settings.max_cl_cases_per_seed_run
    processed = 0
    skipped = 0
    errors = 0

    # Look back 2 years for initial seed
    filed_after = date.today() - timedelta(days=730)

    async with CourtListenerClient() as cl:
        async with AsyncSessionLocal() as db:

            for query_name, query_str in EPR_LITIGATION_QUERIES:
                if processed >= max_cases:
                    log.info("seed_max_reached", max=max_cases)
                    break

                log.info("seed_query", name=query_name, query=query_str)
                try:
                    cases = await cl.search_epr_cases(query_str, filed_after=filed_after)
                except Exception as e:
                    log.error("seed_search_failed", query=query_name, error=str(e))
                    errors += 1
                    continue

                for result in cases:
                    if processed >= max_cases:
                        break

                    # CourtListener search results use different field names depending on type
                    docket_id = result.get("docket_id") or result.get("id")
                    if not docket_id:
                        skipped += 1
                        continue

                    # Check if already tracked
                    existing = await db.execute(
                        select(LitigationCase).where(
                            LitigationCase.courtlistener_id == docket_id
                        )
                    )
                    if existing.scalar_one_or_none():
                        log.info("seed_case_exists", docket_id=docket_id)
                        skipped += 1
                        continue

                    # Throttle: 1.5s between requests
                    await _asyncio.sleep(1.5)

                    try:
                        # Fetch full docket details
                        docket = await cl.get_docket_details(docket_id)
                        await _asyncio.sleep(1.0)

                        # Fetch parties
                        parties = await cl.get_parties(docket_id)
                        await _asyncio.sleep(1.0)

                        # Extract court_id
                        court_url = docket.get("court", "") or ""
                        court_id = court_url.rstrip("/").split("/")[-1] if court_url else result.get("court_id", "")

                        # Infer case attributes
                        case_name = docket.get("case_name") or result.get("caseName", "Unknown Case")
                        challenge_type = infer_challenge_type(case_name, docket.get("cause", "") or "")
                        plaintiff_type, key_plaintiffs = infer_plaintiff_type(parties)

                        # Parse dates
                        date_filed_str = docket.get("date_filed")
                        date_filed = date.fromisoformat(date_filed_str) if date_filed_str else None
                        date_terminated_str = docket.get("date_terminated")
                        date_terminated = date.fromisoformat(date_terminated_str) if date_terminated_str else None

                        # Build CL URL
                        cl_path = docket.get("absolute_url", "")
                        cl_url = f"https://www.courtlistener.com{cl_path}" if cl_path else None

                        # Get initial docket entries for classification
                        entries = await cl.get_docket_entries(docket_id)
                        await _asyncio.sleep(1.0)

                        # Classify entries and build events
                        classified_events = []
                        for entry in entries[:20]:  # Cap at 20 initial entries
                            classification = await classify_litigation_event(
                                entry,
                                case_name=case_name,
                                court_id=court_id,
                            )
                            classified_events.append((entry, classification))

                        # Score preemption risk
                        case_dict = {
                            "case_name": case_name,
                            "court_id": court_id,
                            "challenge_type": challenge_type,
                            "key_plaintiffs": key_plaintiffs,
                            "date_filed": date_filed_str,
                        }
                        events_for_scoring = [
                            {"date_filed": e.get("date_filed"), "description": e.get("description")}
                            for e, _ in classified_events
                        ]
                        preemption_risk = await score_preemption_risk(case_dict, events_for_scoring)

                        # Determine case status
                        case_status = "active"
                        if date_terminated:
                            case_status = "terminated"
                        # Check for injunction signals in events
                        for _, cls in classified_events:
                            if cls["event_type"] == "injunction_ruling" and cls["significance"] == "critical":
                                desc_lower = (cls.get("summary") or "").lower()
                                if "granted" in desc_lower:
                                    case_status = "injunction_granted"
                                elif "denied" in desc_lower:
                                    case_status = "injunction_denied"

                        # Persist litigation_case
                        litigation_case = LitigationCase(
                            courtlistener_id=docket_id,
                            case_name=case_name,
                            docket_number=docket.get("docket_number"),
                            court_id=court_id,
                            court_name=None,  # decoded in dashboard
                            date_filed=date_filed,
                            date_terminated=date_terminated,
                            assigned_judge=docket.get("assigned_to_str"),
                            case_status=case_status,
                            challenge_type=challenge_type,
                            plaintiff_type=plaintiff_type,
                            key_plaintiffs=key_plaintiffs,
                            preemption_risk=preemption_risk,
                            cl_url=cl_url,
                            last_activity_date=date_filed,
                        )
                        db.add(litigation_case)
                        await db.flush()  # Get the auto-generated ID

                        # Match to bill
                        bill_id, inferred_state, confidence = await match_case_to_bill(
                            db, litigation_case, cause=docket.get("cause", "") or ""
                        )
                        litigation_case.related_state = inferred_state
                        litigation_case.related_law_id = bill_id
                        if bill_id:
                            log.info(
                                "seed_bill_matched",
                                case_name=case_name,
                                bill_id=bill_id,
                                confidence=round(confidence, 3),
                            )

                        # Persist litigation_events
                        for entry, cls in classified_events:
                            entry_id = entry.get("id")
                            # Check unique constraint
                            if entry_id:
                                existing_event = await db.execute(
                                    select(LitigationEvent).where(
                                        LitigationEvent.courtlistener_entry_id == entry_id
                                    )
                                )
                                if existing_event.scalar_one_or_none():
                                    continue

                            date_filed_entry_str = entry.get("date_filed")
                            date_filed_entry = (
                                date.fromisoformat(date_filed_entry_str)
                                if date_filed_entry_str
                                else None
                            )

                            # Find first recap document URL if available
                            doc_url = None
                            for recap_doc in (entry.get("recap_documents") or [])[:1]:
                                if isinstance(recap_doc, dict) and recap_doc.get("filepath_local"):
                                    doc_url = f"https://storage.courtlistener.com/{recap_doc['filepath_local']}"

                            event = LitigationEvent(
                                case_id=litigation_case.id,
                                courtlistener_entry_id=entry_id,
                                event_type=cls["event_type"],
                                date_filed=date_filed_entry,
                                description=entry.get("description"),
                                summary=cls["summary"],
                                significance=cls["significance"],
                                document_url=doc_url,
                            )
                            db.add(event)

                            if date_filed_entry and (
                                litigation_case.last_activity_date is None
                                or date_filed_entry > litigation_case.last_activity_date
                            ):
                                litigation_case.last_activity_date = date_filed_entry

                        # Create docket alert subscription
                        try:
                            alert = await cl.create_docket_alert(docket_id)
                            sub = CLAlertSubscription(
                                alert_type="docket_alert",
                                cl_alert_id=alert.get("id"),
                                docket_id=docket_id,
                                active=True,
                            )
                            db.add(sub)
                        except Exception as e:
                            log.warning("seed_docket_alert_failed", docket_id=docket_id, error=str(e))

                        await db.commit()
                        processed += 1
                        log.info(
                            "seed_case_added",
                            case_name=case_name,
                            docket_id=docket_id,
                            preemption_risk=preemption_risk,
                            events=len(classified_events),
                        )

                    except Exception as e:
                        log.error("seed_case_failed", docket_id=docket_id, error=str(e))
                        await db.rollback()
                        errors += 1

    log.info("seed_complete", processed=processed, skipped=skipped, errors=errors)
    print(f"\nSeed complete: {processed} cases added, {skipped} skipped, {errors} errors.")


if __name__ == "__main__":
    asyncio.run(seed())
