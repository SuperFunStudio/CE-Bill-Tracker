"""
FastAPI webhook endpoint for CourtListener push notifications.

Handles two event types:
- docket.alert: new filings on a tracked case
- search.alert: new cases matching a standing search query

Webhook authenticity is verified via HMAC-SHA256 of the raw request body
using COURTLISTENER_WEBHOOK_SECRET (if configured).
"""
import hashlib
import hmac
from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.ingestion.courtlistener import (
    CourtListenerClient,
    classify_litigation_event,
    extract_docket_id_from_url,
    infer_challenge_type,
    infer_plaintiff_type,
    score_preemption_risk,
)
from app.models import CLAlertSubscription, LitigationCase, LitigationEvent

log = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(body: bytes, signature_header: str | None) -> bool:
    """Verify HMAC-SHA256 webhook signature. Returns True if valid or no secret configured."""
    secret = settings.courtlistener_webhook_secret
    if not secret:
        return True  # No secret configured — accept all
    if not signature_header:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # CourtListener may send as "sha256=<hex>" or just "<hex>"
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


@router.post("/courtlistener")
async def courtlistener_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive push notifications from CourtListener search and docket alerts."""
    body = await request.body()
    signature = request.headers.get("X-CL-Signature")

    if not _verify_signature(body, signature):
        log.warning("cl_webhook_invalid_signature")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = (payload.get("webhook") or {}).get("event_type", "")
    log.info("cl_webhook_received", event_type=event_type)

    if event_type == "docket.alert":
        results = (payload.get("payload") or {}).get("results", [])
        await _process_docket_alert(results, db)

    elif event_type == "search.alert":
        results = (payload.get("payload") or {}).get("results", [])
        await _process_search_alert(results, db)

    else:
        log.warning("cl_webhook_unknown_event_type", event_type=event_type)

    return {"status": "ok"}


async def _process_docket_alert(entries: list[dict], db: AsyncSession) -> None:
    """Process new docket entries for a tracked case."""
    for entry in entries:
        docket_id = entry.get("docket")
        if not docket_id:
            # entry.docket may be a URL
            docket_url = entry.get("docket_url", "")
            docket_id = extract_docket_id_from_url(docket_url)
        if isinstance(docket_id, str) and docket_id.isdigit():
            docket_id = int(docket_id)

        if not docket_id:
            log.warning("cl_webhook_no_docket_id", entry_id=entry.get("id"))
            continue

        # Look up the tracked case
        result = await db.execute(
            select(LitigationCase).where(LitigationCase.courtlistener_id == docket_id)
        )
        case = result.scalar_one_or_none()
        if not case:
            log.info("cl_webhook_docket_not_tracked", docket_id=docket_id)
            continue

        entry_id = entry.get("id")

        # Skip if already stored
        if entry_id:
            existing = await db.execute(
                select(LitigationEvent).where(
                    LitigationEvent.courtlistener_entry_id == entry_id
                )
            )
            if existing.scalar_one_or_none():
                continue

        # Classify the new entry
        classification = await classify_litigation_event(
            entry,
            case_name=case.case_name,
            court_id=case.court_id,
        )

        date_filed_str = entry.get("date_filed")
        date_filed = date.fromisoformat(date_filed_str) if date_filed_str else None

        # Find document URL from recap docs
        doc_url = None
        for recap_doc in (entry.get("recap_documents") or [])[:1]:
            if isinstance(recap_doc, dict) and recap_doc.get("filepath_local"):
                doc_url = f"https://storage.courtlistener.com/{recap_doc['filepath_local']}"

        event = LitigationEvent(
            case_id=case.id,
            courtlistener_entry_id=entry_id,
            event_type=classification["event_type"],
            date_filed=date_filed,
            description=entry.get("description"),
            summary=classification["summary"],
            significance=classification["significance"],
            document_url=doc_url,
        )
        db.add(event)

        # Update case last_activity_date
        if date_filed and (
            case.last_activity_date is None or date_filed > case.last_activity_date
        ):
            case.last_activity_date = date_filed

        # Update case_status for critical rulings
        if classification["event_type"] == "injunction_ruling" and classification["significance"] == "critical":
            summary_lower = (classification.get("summary") or "").lower()
            if "granted" in summary_lower:
                case.case_status = "injunction_granted"
                # Update related law's litigation_risk
                if case.related_law_id:
                    from app.models import Bill
                    bill_result = await db.execute(
                        select(Bill).where(Bill.id == case.related_law_id)
                    )
                    bill = bill_result.scalar_one_or_none()
                    if bill:
                        bill.litigation_risk = "injunction_stayed"
            elif "denied" in summary_lower:
                case.case_status = "injunction_denied"
        elif classification["event_type"] == "appeal":
            case.case_status = "appealed"

        log.info(
            "cl_webhook_event_stored",
            case_id=case.id,
            event_type=classification["event_type"],
            significance=classification["significance"],
        )

    await db.commit()

    # Dispatch alerts for high/critical events (after commit so IDs are stable)
    await _dispatch_litigation_alerts(db)


async def _process_search_alert(results: list[dict], db: AsyncSession) -> None:
    """Process new cases found by a standing search alert."""
    for result in results:
        docket_id = result.get("docket_id") or result.get("id")
        if not docket_id:
            continue

        # Check if already tracked
        existing = await db.execute(
            select(LitigationCase).where(LitigationCase.courtlistener_id == docket_id)
        )
        if existing.scalar_one_or_none():
            continue

        log.info("cl_webhook_new_case_found", docket_id=docket_id)

        # Trigger full case ingestion asynchronously
        try:
            async with CourtListenerClient() as cl:
                docket = await cl.get_docket_details(docket_id)
                parties = await cl.get_parties(docket_id)

                court_url = docket.get("court", "") or ""
                court_id = court_url.rstrip("/").split("/")[-1] if court_url else ""
                case_name = docket.get("case_name") or result.get("caseName", "Unknown Case")
                challenge_type = infer_challenge_type(case_name, docket.get("cause", "") or "")
                plaintiff_type, key_plaintiffs = infer_plaintiff_type(parties)

                date_filed_str = docket.get("date_filed")
                date_filed = date.fromisoformat(date_filed_str) if date_filed_str else None
                cl_path = docket.get("absolute_url", "")
                cl_url = f"https://www.courtlistener.com{cl_path}" if cl_path else None

                entries = await cl.get_docket_entries(docket_id)
                classified_events = []
                for entry in entries[:10]:
                    cls = await classify_litigation_event(entry, case_name=case_name, court_id=court_id)
                    classified_events.append((entry, cls))

                case_dict = {
                    "case_name": case_name,
                    "court_id": court_id,
                    "challenge_type": challenge_type,
                    "key_plaintiffs": key_plaintiffs,
                    "date_filed": date_filed_str,
                }
                preemption_risk = await score_preemption_risk(
                    case_dict,
                    [{"date_filed": e.get("date_filed"), "description": e.get("description")} for e, _ in classified_events],
                )

                new_case = LitigationCase(
                    courtlistener_id=docket_id,
                    case_name=case_name,
                    docket_number=docket.get("docket_number"),
                    court_id=court_id,
                    date_filed=date_filed,
                    assigned_judge=docket.get("assigned_to_str"),
                    case_status="active",
                    challenge_type=challenge_type,
                    plaintiff_type=plaintiff_type,
                    key_plaintiffs=key_plaintiffs,
                    preemption_risk=preemption_risk,
                    cl_url=cl_url,
                    last_activity_date=date_filed,
                )
                db.add(new_case)
                await db.flush()

                for entry, cls in classified_events:
                    date_filed_entry_str = entry.get("date_filed")
                    event = LitigationEvent(
                        case_id=new_case.id,
                        courtlistener_entry_id=entry.get("id"),
                        event_type=cls["event_type"],
                        date_filed=date.fromisoformat(date_filed_entry_str) if date_filed_entry_str else None,
                        description=entry.get("description"),
                        summary=cls["summary"],
                        significance=cls["significance"],
                    )
                    db.add(event)

                # Create docket alert for ongoing monitoring
                try:
                    alert = await cl.create_docket_alert(docket_id)
                    db.add(CLAlertSubscription(
                        alert_type="docket_alert",
                        cl_alert_id=alert.get("id"),
                        docket_id=docket_id,
                        active=True,
                    ))
                except Exception as e:
                    log.warning("cl_webhook_docket_alert_failed", docket_id=docket_id, error=str(e))

                await db.commit()
                log.info("cl_webhook_case_ingested", case_name=case_name, docket_id=docket_id)

        except Exception as e:
            log.error("cl_webhook_case_ingest_failed", docket_id=docket_id, error=str(e))
            await db.rollback()


async def _dispatch_litigation_alerts(db: AsyncSession) -> None:
    """Dispatch SendGrid/Slack alerts for recent high/critical litigation events."""
    from datetime import datetime, timezone, timedelta
    from app.alerts.sendgrid_sender import SendGridSender
    from app.alerts.slack_sender import SlackSender
    from app.models import AlertSubscription

    # Find high/critical events from last hour not yet alerted
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    events_result = await db.execute(
        select(LitigationEvent)
        .where(
            LitigationEvent.significance.in_(["high", "critical"]),
            LitigationEvent.created_at >= cutoff,
        )
    )
    notable_events = events_result.scalars().all()
    if not notable_events:
        return

    # Load active subscriptions with Slack webhooks or emails
    subs_result = await db.execute(
        select(AlertSubscription).where(AlertSubscription.active == True)  # noqa: E712
    )
    subs = subs_result.scalars().all()
    if not subs:
        return

    email_sender = SendGridSender()
    slack_sender = SlackSender()

    for event in notable_events:
        case_result = await db.execute(
            select(LitigationCase).where(LitigationCase.id == event.case_id)
        )
        case = case_result.scalar_one_or_none()
        if not case:
            continue

        sig_emoji = "🚨" if event.significance == "critical" else "⚠️"
        injunction_prefix = ""
        if case.case_status == "injunction_granted":
            injunction_prefix = "🚨 ENFORCEMENT STAYED — "

        subject = f"{injunction_prefix}{sig_emoji} EPR Litigation Update: {case.case_name}"
        body = (
            f"{injunction_prefix}**{event.event_type.replace('_', ' ').title()}** filed in "
            f"*{case.case_name}* ({case.court_id.upper() if case.court_id else 'Federal Court'})\n\n"
            f"**Date**: {event.date_filed or 'Unknown'}\n"
            f"**Significance**: {event.significance.upper()}\n"
            f"**Summary**: {event.summary or event.description or 'No summary available.'}\n"
        )
        if case.cl_url:
            body += f"\n**Case Docket**: {case.cl_url}"
        if event.document_url:
            body += f"\n**Document**: {event.document_url}"

        for sub in subs:
            # Only notify subscribers watching the relevant state (or ALL)
            states = sub.states or []
            if "ALL" not in states and case.related_state and case.related_state not in states:
                continue

            if sub.email and settings.sendgrid_api_key:
                try:
                    await email_sender.send_text_alert(sub.email, subject, body)
                except Exception as e:
                    log.warning("cl_alert_email_failed", error=str(e))

            if sub.slack_webhook:
                try:
                    await slack_sender.send_text_alert(sub.slack_webhook, body)
                except Exception as e:
                    log.warning("cl_alert_slack_failed", error=str(e))
