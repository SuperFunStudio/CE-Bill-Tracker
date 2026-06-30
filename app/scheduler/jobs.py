import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

log = structlog.get_logger()


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Main ingestion + classification — daily at 2am UTC
    scheduler.add_job(
        run_ingestion_cycle,
        "cron",
        hour=2,
        minute=0,
        id="daily_ingestion",
        replace_existing=True,
    )

    # Federal Register — every N hours
    scheduler.add_job(
        run_federal_cycle,
        "interval",
        hours=settings.federal_register_poll_interval_hours,
        id="federal_register_poll",
        replace_existing=True,
    )

    # Alert dispatch — every 30 min during business hours UTC
    scheduler.add_job(
        run_alert_dispatch,
        "cron",
        hour="8-18",
        minute="*/30",
        id="alert_dispatch",
        replace_existing=True,
    )

    # Company impact scoring — daily at 3am UTC
    scheduler.add_job(
        run_scoring_cycle,
        "cron",
        hour=3,
        minute=0,
        id="daily_scoring",
        replace_existing=True,
    )

    # Company data refresh — weekly Sunday at 4am UTC
    scheduler.add_job(
        run_company_refresh,
        "cron",
        day_of_week="sun",
        hour=4,
        minute=0,
        id="weekly_company_refresh",
        replace_existing=True,
    )

    # Exposure brief generation — daily at 4am UTC (runs after scoring at 3am)
    scheduler.add_job(
        run_interpretation_cycle,
        "cron",
        hour=4,
        minute=0,
        id="daily_interpretation",
        replace_existing=True,
    )

    # CourtListener: weekly new case scan — Monday 6am UTC
    # Avoids CL maintenance window (Thu 21:00–23:59 PT = Fri 05:00–07:59 UTC)
    scheduler.add_job(
        poll_courtlistener_new_cases,
        "cron",
        day_of_week="mon",
        hour=6,
        minute=0,
        id="cl_new_cases",
        replace_existing=True,
    )

    # CourtListener: daily active case refresh — 7:30am UTC
    scheduler.add_job(
        refresh_active_cases,
        "cron",
        hour=7,
        minute=30,
        id="cl_refresh_cases",
        replace_existing=True,
    )

    # Bill-to-litigation matching reconciliation — nightly at 8am UTC
    # Catches cases that had no bill match at ingest time (bill added later, or confidence improved)
    scheduler.add_job(
        reconcile_bill_matches,
        "cron",
        hour=8,
        minute=0,
        id="cl_bill_match_reconcile",
        replace_existing=True,
    )

    # Monthly subscriber digest — 1st of month, 13:00 UTC (morning US). Dormant unless enabled,
    # so previews via scripts/send_digest.py can be reviewed before any real send.
    if settings.enable_digest:
        scheduler.add_job(
            run_digest_cycle,
            "cron",
            day=1,
            hour=13,
            minute=0,
            id="monthly_digest",
            replace_existing=True,
        )

    # Weekly subscriber digest — Monday 13:00 UTC. The habit-cadence half of the alert loop.
    if settings.enable_weekly_digest:
        scheduler.add_job(
            run_weekly_digest_cycle,
            "cron",
            day_of_week="mon",
            hour=13,
            minute=0,
            id="weekly_digest",
            replace_existing=True,
        )

    # Event-triggered deadline reminders — daily 12:00 UTC. The loss-triggered half of the alert loop.
    if settings.enable_deadline_alerts:
        scheduler.add_job(
            run_deadline_alert_cycle,
            "cron",
            hour=12,
            minute=0,
            id="deadline_alerts",
            replace_existing=True,
        )

    # Event-triggered "new bill" alerts — daily 11:30 UTC. The "something moved" trigger.
    if settings.enable_new_bill_alerts:
        scheduler.add_job(
            run_new_bill_alert_cycle,
            "cron",
            hour=11,
            minute=30,
            id="new_bill_alerts",
            replace_existing=True,
        )

    # Trial-ending reminders — daily 13:30 UTC. Conversion nudge for no-card comp trials about to lapse.
    if settings.enable_trial_reminders:
        scheduler.add_job(
            run_trial_reminder_cycle,
            "cron",
            hour=13,
            minute=30,
            id="trial_reminders",
            replace_existing=True,
        )

    # Watch-list onboarding — every 20 min. Sends the one-time "here's how your alerts work" email
    # ~1h after a user's first star (debounced so a burst of stars batches into one email). Gated on
    # the shared welcome-email flag. Idempotent via onboarding_email_sent_at, so frequent ticks are
    # cheap — most find nothing to do.
    if settings.enable_welcome_email:
        scheduler.add_job(
            run_watchlist_onboarding_cycle,
            "interval",
            minutes=20,
            id="watchlist_onboarding",
            replace_existing=True,
        )

    # Watch-list recap — every 20 min. When an already-onboarded user adds more bills, a 30-min
    # debounce batches the burst into one "you added N bills" recap pointing to My Portfolio.
    # Idempotent via watchlist_recap_sent_at, so frequent ticks are cheap. Dormant unless enabled.
    if settings.enable_watchlist_recap:
        scheduler.add_job(
            run_watchlist_recap_cycle,
            "interval",
            minutes=20,
            id="watchlist_recap",
            replace_existing=True,
        )

    # Source-link health audit — weekly Saturday 5am UTC (a quiet slot). Re-checks the most-stale
    # batch of bill "View Source" links so the UI's fallback (redirect fix / LegiScan backup) stays
    # current. Dormant unless enabled; preview via scripts/audit_bill_source_links.py --dry-run.
    if settings.enable_link_audit:
        scheduler.add_job(
            run_source_link_audit_cycle,
            "cron",
            day_of_week="sat",
            hour=5,
            minute=0,
            id="source_link_audit",
            replace_existing=True,
        )

    # Full-text index refresh — daily 6:30am UTC (a quiet slot, after the 2am ingestion settles).
    # Re-fetches text for bills that changed (change_hash moved) or were never indexed, bounded per
    # run so it sweeps the corpus over several days rather than flooding LegiScan in one pass.
    # Dormant unless enabled; the one-time corpus load is scripts/backfill_bill_text.py.
    if settings.enable_bill_text_refresh:
        scheduler.add_job(
            run_bill_text_refresh_cycle,
            "cron",
            hour=6,
            minute=30,
            id="bill_text_refresh",
            replace_existing=True,
        )

    # EU-central law refresh — weekly Tuesday 5:30am UTC. Re-runs the EUR-Lex/CELLAR SPARQL sweep and
    # ingests newly-published in-force acts (only_new), classifying them region-aware. EU law changes
    # slowly so weekly is ample. Dormant unless enabled; the one-time bulk load is
    # scripts/ingest_eurlex.py --bulk.
    if settings.enable_eurlex_ingestion:
        scheduler.add_job(
            run_eurlex_cycle,
            "cron",
            day_of_week="tue",
            hour=5,
            minute=30,
            id="eurlex_refresh",
            replace_existing=True,
        )

    return scheduler


async def run_ingestion_cycle(state_filter: str | None = None) -> None:
    """Main ingestion + classification cycle."""
    from app.database import AsyncSessionLocal
    from app.ingestion.coordinator import IngestionCoordinator

    log.info("ingestion_cycle_start", state_filter=state_filter)
    if settings.enable_legiscan_ingestion:
        async with AsyncSessionLocal() as db:
            coordinator = IngestionCoordinator()
            summary = await coordinator.run_full_cycle(db, state_filter=state_filter)
            log.info("legiscan_cycle_complete", **summary)
    else:
        log.info("legiscan_ingestion_skipped", reason="enable_legiscan_ingestion=false")

    if settings.enable_openstates_ingestion:
        from datetime import datetime, timedelta, timezone
        updated_since = datetime.now(timezone.utc) - timedelta(
            days=settings.openstates_recent_window_days
        )
        async with AsyncSessionLocal() as db:
            coordinator = IngestionCoordinator()
            os_summary = await coordinator.run_openstates_cycle(
                db,
                state_filter=state_filter,
                updated_since=updated_since,
            )
            log.info("openstates_cycle_complete", **os_summary)

    await run_classification_cycle()


async def run_seed() -> None:
    """DISABLED. The hand-curated seed (known_epr_laws.json) had wrong source URLs and was
    replaced by the OpenStates v3 sync (migration 005 purged the seed rows). Kept as a no-op
    so callers/imports don't break. To repopulate the dataset use run_openstates_full_sync().
    """
    log.info("seed_disabled", reason="seed replaced by OpenStates sync; see migration 005")
    return


async def _run_seed_legacy_disabled() -> None:
    """Original seed loader, retained for reference only — not called. See run_seed()."""
    import json
    from datetime import date
    from pathlib import Path

    from sqlalchemy import select, update
    from app.database import AsyncSessionLocal
    from app.models import Bill, ComplianceDeadline

    seed_path = Path(__file__).parent.parent.parent / "data" / "seed" / "known_epr_laws.json"
    with open(seed_path) as f:
        laws = json.load(f)

    def _parse_date(val: str | None) -> date | None:
        if not val:
            return None
        try:
            return date.fromisoformat(val[:10])
        except ValueError:
            return None

    async with AsyncSessionLocal() as db:
        seeded = updated = 0
        for law in laws:
            existing = (await db.execute(
                select(Bill).where(
                    Bill.state == law["state"],
                    Bill.bill_number == law.get("bill_number"),
                )
            )).scalar_one_or_none()

            if existing:
                await db.execute(
                    update(Bill).where(Bill.id == existing.id).values(
                        status=law.get("status"),
                        compliance_details=law.get("compliance_details"),
                        ai_summary=law.get("ai_summary"),
                        confidence_score=1.0,
                        ce_relevant=True,
                        material_categories=law.get("material_categories", []),
                        source_url=law.get("source_url"),
                        urgency=law.get("urgency"),
                        instrument_type=law.get("instrument_type"),
                        title=law.get("title"),
                    )
                )
                bill_obj = existing
                updated += 1
            else:
                bill_obj = Bill(
                    state=law["state"],
                    bill_number=law.get("bill_number"),
                    title=law.get("title"),
                    description=law.get("ai_summary"),
                    status=law.get("status"),
                    status_date=_parse_date(law.get("enacted_date")),
                    last_action_date=_parse_date(law.get("enacted_date")),
                    source_url=law.get("source_url"),
                    ce_relevant=True,
                    confidence_score=1.0,
                    material_categories=law.get("material_categories", []),
                    instrument_type=law.get("instrument_type"),
                    urgency=law.get("urgency"),
                    ai_summary=law.get("ai_summary"),
                    compliance_details=law.get("compliance_details"),
                )
                db.add(bill_obj)
                await db.flush()
                seeded += 1

            compliance = law.get("compliance_details") or {}
            for dl in compliance.get("deadlines", []):
                dl_date = _parse_date(dl.get("date"))
                if not dl_date or not bill_obj.id:
                    continue
                from sqlalchemy import and_
                existing_dl = (await db.execute(
                    select(ComplianceDeadline).where(
                        and_(
                            ComplianceDeadline.bill_id == bill_obj.id,
                            ComplianceDeadline.deadline_date == dl_date,
                            ComplianceDeadline.deadline_type == dl.get("type", "compliance"),
                        )
                    )
                )).scalar_one_or_none()
                if not existing_dl:
                    db.add(ComplianceDeadline(
                        bill_id=bill_obj.id,
                        state=law["state"],
                        deadline_type=dl.get("type", "compliance"),
                        deadline_date=dl_date,
                        description=dl.get("description"),
                    ))

        await db.commit()
        log.info("seed_complete", seeded=seeded, updated=updated, total=len(laws))


async def run_openstates_full_sync(state_filter: str | None = None) -> None:
    """Full historical OpenStates sync — no updated_since filter."""
    from app.database import AsyncSessionLocal
    from app.ingestion.coordinator import IngestionCoordinator

    log.info("openstates_full_sync_start", state_filter=state_filter)
    async with AsyncSessionLocal() as db:
        coordinator = IngestionCoordinator()
        summary = await coordinator.run_openstates_cycle(db, state_filter=state_filter)
        log.info("openstates_full_sync_complete", **summary)

    from app.classification.pipeline import ClassificationPipeline
    from app.database import AsyncSessionLocal
    from sqlalchemy import select
    from app.models import Bill

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Bill).where(Bill.confidence_score.is_(None)).limit(500)
        )
        unclassified = result.scalars().all()
        if unclassified:
            pipeline = ClassificationPipeline()
            await pipeline.run(db, unclassified)
            log.info("classification_complete", bill_count=len(unclassified))


async def run_classification_cycle() -> None:
    """Classify all unclassified bills already in the database.

    Processes in batches of 500 until none remain.
    Safe to call independently — makes no LegiScan API calls.
    """
    from app.classification.pipeline import ClassificationPipeline
    from app.database import AsyncSessionLocal
    from sqlalchemy import select
    from app.models import Bill

    pipeline = ClassificationPipeline()
    total_classified = 0
    last_ids: tuple = ()
    stall_count = 0
    MAX_STALL_ITERATIONS = 3

    while True:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Bill)
                .where(
                    (Bill.confidence_score.is_(None)) |
                    (Bill.confidence_score == -1.0)
                )
                .limit(500)
            )
            unclassified = result.scalars().all()
            if not unclassified:
                break

            # Genuine stall = the SAME bills come back unprocessed (e.g. persistent API
            # failures). Compare bill identities, not the batch length: the batch stays
            # capped at 500 while >500 remain, so a length check force-resolves real progress
            # after 3 batches. A successful batch sets confidence on those bills, so the next
            # query returns different ids and stall_count resets.
            current_ids = tuple(b.id for b in unclassified)
            if current_ids == last_ids:
                stall_count += 1
                if stall_count >= MAX_STALL_ITERATIONS:
                    # Force-resolve genuinely stuck bills as not relevant so they exit the loop.
                    for bill in unclassified:
                        if bill.confidence_score is None or bill.confidence_score == -1.0:
                            bill.confidence_score = 0.0
                            bill.ce_relevant = False
                    await db.commit()
                    log.warning("classification_cycle_stalled_resolved",
                                force_resolved=len(unclassified))
                    break
            else:
                stall_count = 0
            last_ids = current_ids

            await pipeline.run(db, unclassified)
            total_classified += len(unclassified)
            log.info("classification_batch_complete", batch=len(unclassified), total=total_classified)

    log.info("classification_cycle_complete", total_classified=total_classified)


async def run_federal_cycle() -> None:
    """Fetch new Federal Register documents."""
    from app.database import AsyncSessionLocal
    from app.ingestion.coordinator import IngestionCoordinator

    log.info("federal_cycle_start")
    async with AsyncSessionLocal() as db:
        coordinator = IngestionCoordinator()
        summary = await coordinator.run_federal_cycle(db)
        log.info("federal_cycle_complete", **summary)


async def run_scoring_cycle() -> None:
    """Compute impact scores for all (company, EPR-relevant bill) pairs.

    Detects composite_score deltas >= 10 points vs the previous run and
    persists BillChange records for significant changes.
    """
    from sqlalchemy import delete, select
    from sqlalchemy.orm import selectinload

    from app.alerts.detector import ChangeDetector
    from app.database import AsyncSessionLocal
    from app.models import Bill, BillChange, Company, ImpactScore
    from app.scoring.engine import make_engine

    log.info("scoring_cycle_start")
    engine = make_engine()
    detector = ChangeDetector()

    async with AsyncSessionLocal() as db:
        # Load all companies with their materials and state presences
        companies_result = await db.execute(
            select(Company).options(
                selectinload(Company.materials),
                selectinload(Company.state_presences),
            )
        )
        all_companies = companies_result.scalars().all()

        # Load all EPR-relevant bills
        bills_result = await db.execute(
            select(Bill).where(Bill.ce_relevant == True)  # noqa: E712
        )
        all_bills = bills_result.scalars().all()

        if not all_companies or not all_bills:
            log.info("scoring_cycle_skipped", reason="no companies or bills")
            return

        # Pre-compute total volume per bill category across all companies
        # Used for volume-weighted material scoring normalization
        import uuid as _uuid

        all_companies_volumes: dict[_uuid.UUID, float] = {}
        for company in all_companies:
            total = sum(
                m.annual_volume_tonnes
                for m in company.materials
                if m.annual_volume_tonnes is not None
            )
            if total > 0:
                all_companies_volumes[company.id] = total

        # Load previous scores as a lookup for delta detection
        prev_result = await db.execute(
            select(ImpactScore.company_id, ImpactScore.bill_id,
                   ImpactScore.composite_score, ImpactScore.estimated_annual_cost)
        )
        prev_scores: dict[tuple, tuple] = {
            (row.company_id, row.bill_id): (row.composite_score, row.estimated_annual_cost)
            for row in prev_result
        }

        scored = 0
        delta_changes: list[BillChange] = []

        for company in all_companies:
            for bill in all_bills:
                # Capture old score before deleting
                old = prev_scores.get((company.id, bill.id))

                await db.execute(
                    delete(ImpactScore).where(
                        ImpactScore.company_id == company.id,
                        ImpactScore.bill_id == bill.id,
                    )
                )
                new_score = engine.compute(
                    company,
                    bill,
                    company.materials,
                    company.state_presences,
                    all_companies_volumes,
                )
                db.add(new_score)
                scored += 1

                # Detect significant score change
                if old is not None:
                    change = detector.detect_score_changes(
                        company_id=company.id,
                        bill_id=bill.id,
                        old_score=old[0],
                        new_score=new_score.composite_score,
                        old_cost=old[1],
                        new_cost=new_score.estimated_annual_cost,
                    )
                    if change is not None:
                        delta_changes.append(change)

        for change in delta_changes:
            db.add(change)

        await db.commit()
        log.info("scoring_cycle_complete", scored=scored, score_deltas=len(delta_changes))


async def run_interpretation_cycle() -> None:
    """Generate Exposure Briefs for top (company, bill) pairs that lack a valid brief.

    Gated by ENABLE_INTERPRETATION=true. Processes up to max_interpretation_calls_per_run
    pairs per run, prioritising highest composite scores.
    """
    from datetime import datetime, timezone

    from sqlalchemy import and_, desc, or_, select
    from sqlalchemy.orm import selectinload

    from app.database import AsyncSessionLocal
    from app.models import Bill, Company, ExposureBrief, ImpactScore
    from app.scoring.interpreter import ExposureBriefGenerator

    if not settings.enable_interpretation:
        log.info("interpretation_cycle_skipped", reason="enable_interpretation=false")
        return

    log.info("interpretation_cycle_start", limit=settings.max_interpretation_calls_per_run)
    generator = ExposureBriefGenerator()
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # Load top scores that have no valid (non-expired) brief
        scores_result = await db.execute(
            select(ImpactScore)
            .outerjoin(
                ExposureBrief,
                and_(
                    ExposureBrief.company_id == ImpactScore.company_id,
                    ExposureBrief.bill_id == ImpactScore.bill_id,
                ),
            )
            .where(
                or_(
                    ExposureBrief.id.is_(None),
                    ExposureBrief.ttl_expires_at < now,
                )
            )
            .options(
                selectinload(ImpactScore.company).selectinload(Company.materials),
                selectinload(ImpactScore.company).selectinload(Company.state_presences),
                selectinload(ImpactScore.bill),
            )
            .order_by(desc(ImpactScore.composite_score))
            .limit(settings.max_interpretation_calls_per_run)
        )
        scores_to_process = scores_result.scalars().all()

        if not scores_to_process:
            log.info("interpretation_cycle_skipped", reason="all briefs are current")
            return

        generated = 0
        errors = 0

        for impact_score in scores_to_process:
            company = impact_score.company
            bill = impact_score.bill
            if company is None or bill is None:
                continue

            try:
                brief_json = await generator.generate(
                    company_name=company.name,
                    hq_state=company.hq_state,
                    materials=[
                        {
                            "material_category": m.material_category,
                            "annual_volume_tonnes": m.annual_volume_tonnes,
                            "volume_confidence": m.volume_confidence,
                        }
                        for m in company.materials
                    ],
                    state_presences=[
                        {
                            "state": p.state,
                            "presence_type": p.presence_type,
                            "is_primary": p.is_primary,
                        }
                        for p in company.state_presences
                    ],
                    bill_title=bill.title,
                    bill_state=bill.state,
                    bill_number=bill.bill_number,
                    bill_status=bill.status,
                    compliance_details=bill.compliance_details,
                    composite_score=impact_score.composite_score,
                    estimated_annual_cost=impact_score.estimated_annual_cost,
                )

                # Upsert: remove any stale/expired entry, insert fresh one
                from sqlalchemy import delete as sql_delete
                await db.execute(
                    sql_delete(ExposureBrief).where(
                        ExposureBrief.company_id == company.id,
                        ExposureBrief.bill_id == bill.id,
                    )
                )
                brief = ExposureBrief(
                    company_id=company.id,
                    bill_id=bill.id,
                    brief_json=brief_json,
                    ttl_expires_at=generator.ttl_timestamp(),
                )
                db.add(brief)
                await db.commit()
                generated += 1

            except Exception as exc:
                log.error(
                    "interpretation_cycle_error",
                    company=company.name,
                    bill_id=bill.id,
                    error=str(exc),
                )
                await db.rollback()
                errors += 1

    log.info("interpretation_cycle_complete", generated=generated, errors=errors)


async def run_company_refresh() -> None:
    """Refresh company data from EPA FRS, CAA registry, and SEC EDGAR."""
    from app.company_intel.coordinator import CompanyIntelCoordinator
    from app.database import AsyncSessionLocal

    log.info("company_refresh_start")
    async with AsyncSessionLocal() as db:
        coordinator = CompanyIntelCoordinator()
        stats = await coordinator.refresh_all(db)
        await db.commit()
    log.info("company_refresh_complete", **{k: v for k, v in stats.items() if not isinstance(v, dict)})


async def run_alert_dispatch() -> None:
    """Dispatch pending alerts for unsent BillChanges."""
    from app.database import AsyncSessionLocal
    from app.alerts.dispatcher import AlertDispatcher
    from sqlalchemy import select
    from app.models import BillChange

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(BillChange).where(BillChange.alert_sent == False).limit(200)
        )
        pending = result.scalars().all()
        if pending:
            dispatcher = AlertDispatcher()
            await dispatcher.dispatch_changes(db, pending)
            log.info("alerts_dispatched", count=len(pending))


async def run_digest_cycle(
    window_days: int | None = None, period_label: str = "monthly"
) -> None:
    """Email each active subscriber a roundup of recent movement over a window.

    Scoped per subscriber to the topics (instrument_types) + jurisdictions (states) they signed up
    for. Subscribers with no matching movement get no email. The monthly job calls this with the
    defaults; the weekly job passes window_days=7, period_label="weekly" (build/render are already
    window- and label-parameterized, so there's one code path for both cadences).
    """
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.alerts.digest import build_digests, render_digest_html, render_digest_subject
    from app.alerts.sendgrid_sender import SendGridSender
    from app.alerts.unsubscribe import unsubscribe_url
    from app.database import AsyncSessionLocal

    if not settings.sendgrid_api_key:
        log.warning("digest_skipped_no_sendgrid_key", period=period_label)
        return

    days = window_days if window_days is not None else settings.digest_window_days
    sender = SendGridSender()
    async with AsyncSessionLocal() as db:
        now = (await db.execute(select(func.now()))).scalar_one()
        since = now - timedelta(days=days)
        digests = await build_digests(db, since)

    sent = 0
    for sub, content in digests:
        subject = render_digest_subject(content, period_label)
        html = render_digest_html(sub, content, period_label)
        if await sender.send_html(sub.email, subject, html, list_unsubscribe_url=unsubscribe_url(sub.id)):
            sent += 1
    log.info("digest_cycle_complete", period=period_label, recipients=len(digests), sent=sent)


async def run_weekly_digest_cycle() -> None:
    """Weekly cadence wrapper around run_digest_cycle (7-day window). Gated by enable_weekly_digest."""
    await run_digest_cycle(
        window_days=settings.weekly_digest_window_days, period_label="weekly"
    )


async def run_deadline_alert_cycle() -> None:
    """Daily: email subscribers when a compliance deadline they follow comes within the lead window.

    Gated by settings.enable_deadline_alerts. Marks reminder_sent only on the deadlines actually
    emailed, so an unmatched deadline stays eligible if someone subscribes before it passes.
    """
    from sqlalchemy import func, select, update

    from app.alerts.deadline_alerts import (
        build_deadline_alerts,
        render_deadline_alert_html,
        render_deadline_alert_subject,
    )
    from app.alerts.sendgrid_sender import SendGridSender
    from app.alerts.unsubscribe import unsubscribe_url
    from app.database import AsyncSessionLocal
    from app.models import ComplianceDeadline

    if not settings.sendgrid_api_key:
        log.warning("deadline_alerts_skipped_no_sendgrid_key")
        return

    lead_days = max(settings.deadline_reminder_days) if settings.deadline_reminder_days else 30
    sender = SendGridSender()
    async with AsyncSessionLocal() as db:
        today = (await db.execute(select(func.current_date()))).scalar_one()
        alerts = await build_deadline_alerts(db, today, lead_days)

        sent = 0
        sent_deadline_ids: set[int] = set()
        for sub, content in alerts:
            subject = render_deadline_alert_subject(content)
            html = render_deadline_alert_html(sub, content)
            if await sender.send_html(sub.email, subject, html, list_unsubscribe_url=unsubscribe_url(sub.id)):
                sent += 1
                sent_deadline_ids.update(it.deadline.id for it in content.items)

        if sent_deadline_ids:
            await db.execute(
                update(ComplianceDeadline)
                .where(ComplianceDeadline.id.in_(sent_deadline_ids))
                .values(reminder_sent=True)
            )
            await db.commit()
    log.info(
        "deadline_alert_cycle_complete",
        recipients=len(alerts),
        sent=sent,
        marked=len(sent_deadline_ids),
    )


async def run_trial_reminder_cycle() -> None:
    """Daily: email accounts whose no-card comp trial (signup 7d / referral 30d) expires within the
    lead window. Gated by settings.enable_trial_reminders. Marks trial_reminder_sent_for on each
    account emailed, so it sends once per trial expiry."""
    from datetime import datetime, timezone

    from app.alerts.sendgrid_sender import SendGridSender
    from app.alerts.trial_reminders import (
        build_trial_reminders,
        render_trial_reminder_html,
        render_trial_reminder_subject,
    )
    from app.database import AsyncSessionLocal

    if not settings.sendgrid_api_key:
        log.warning("trial_reminders_skipped_no_sendgrid_key")
        return

    sender = SendGridSender()
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        items = await build_trial_reminders(db, now, settings.trial_reminder_lead_days)
        sent = 0
        for item in items:
            subject = render_trial_reminder_subject(item)
            html = render_trial_reminder_html(item)
            if await sender.send_html(item.entitlement.email, subject, html):
                sent += 1
                item.entitlement.trial_reminder_sent_for = item.entitlement.current_period_end
        if sent:
            await db.commit()
    log.info("trial_reminder_cycle_complete", candidates=len(items), sent=sent)


async def run_watchlist_onboarding_cycle() -> None:
    """Every 20 min: send the one-time watch-list onboarding email to accounts whose first star is
    past the debounce window (so a burst of stars batches into one email) but still recent. Stamps
    onboarding_email_sent_at on each account's watchlist subscription so it sends exactly once.
    Gated by settings.enable_welcome_email. See app/alerts/watchlist_onboarding.py."""
    from datetime import datetime, timezone

    from app.alerts.sendgrid_sender import SendGridSender
    from app.alerts.unsubscribe import unsubscribe_url
    from app.alerts.watchlist_onboarding import (
        build_watchlist_onboarding,
        render_onboarding_html,
        render_onboarding_subject,
        render_onboarding_text,
    )
    from app.database import AsyncSessionLocal

    if not settings.sendgrid_api_key:
        log.warning("watchlist_onboarding_skipped_no_sendgrid_key")
        return

    sender = SendGridSender()
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        items = await build_watchlist_onboarding(db, now)
        sent = 0
        for content in items:
            ok = await sender.send_html(
                content.sub.email,
                render_onboarding_subject(content),
                render_onboarding_html(content),
                list_unsubscribe_url=unsubscribe_url(content.sub.id),
                text=render_onboarding_text(content),
            )
            if ok:
                sent += 1
                content.sub.onboarding_email_sent_at = now
        if sent:
            await db.commit()
    log.info("watchlist_onboarding_cycle_complete", candidates=len(items), sent=sent)


async def run_watchlist_recap_cycle() -> None:
    """Every 20 min: email already-onboarded users a recap when they add more bills. A 30-min debounce
    batches a burst of stars into one "you added N bills" email pointing to My Portfolio, and stamps
    watchlist_recap_sent_at so the same adds aren't re-sent. Gated by settings.enable_watchlist_recap.
    See app/alerts/watchlist_recap.py."""
    from datetime import datetime, timezone

    from app.alerts.sendgrid_sender import SendGridSender
    from app.alerts.unsubscribe import unsubscribe_url
    from app.alerts.watchlist_recap import (
        build_watchlist_recap,
        render_recap_html,
        render_recap_subject,
        render_recap_text,
    )
    from app.database import AsyncSessionLocal

    if not settings.enable_watchlist_recap:
        log.info("watchlist_recap_skipped", reason="enable_watchlist_recap=false")
        return
    if not settings.sendgrid_api_key:
        log.warning("watchlist_recap_skipped_no_sendgrid_key")
        return

    sender = SendGridSender()
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        items = await build_watchlist_recap(db, now)
        sent = 0
        for content in items:
            ok = await sender.send_html(
                content.sub.email,
                render_recap_subject(content),
                render_recap_html(content),
                list_unsubscribe_url=unsubscribe_url(content.sub.id),
                text=render_recap_text(content),
            )
            if ok:
                sent += 1
                content.sub.watchlist_recap_sent_at = now
        if sent:
            await db.commit()
    log.info("watchlist_recap_cycle_complete", candidates=len(items), sent=sent)


async def run_new_bill_alert_cycle() -> None:
    """Daily: email subscribers when a newly-tracked relevant bill matches their topics + states.

    Gated by settings.enable_new_bill_alerts. Marks new_bill_alert_sent only on bills actually
    emailed, so an unmatched new bill stays eligible until it ages out of the window.
    """
    from sqlalchemy import func, select, update

    from app.alerts.new_bill_alerts import (
        build_new_bill_alerts,
        render_new_bill_alert_html,
        render_new_bill_alert_subject,
    )
    from app.alerts.sendgrid_sender import SendGridSender
    from app.alerts.unsubscribe import unsubscribe_url
    from app.database import AsyncSessionLocal
    from app.models import Bill

    if not settings.sendgrid_api_key:
        log.warning("new_bill_alerts_skipped_no_sendgrid_key")
        return

    sender = SendGridSender()
    async with AsyncSessionLocal() as db:
        today = (await db.execute(select(func.current_date()))).scalar_one()
        alerts = await build_new_bill_alerts(db, today, settings.new_bill_alert_window_days)

        sent = 0
        sent_bill_ids: set[int] = set()
        for sub, content in alerts:
            subject = render_new_bill_alert_subject(content)
            html = render_new_bill_alert_html(sub, content)
            if await sender.send_html(sub.email, subject, html, list_unsubscribe_url=unsubscribe_url(sub.id)):
                sent += 1
                sent_bill_ids.update(b.id for b in content.bills)

        if sent_bill_ids:
            await db.execute(
                update(Bill).where(Bill.id.in_(sent_bill_ids)).values(new_bill_alert_sent=True)
            )
            await db.commit()
    log.info(
        "new_bill_alert_cycle_complete",
        recipients=len(alerts),
        sent=sent,
        marked=len(sent_bill_ids),
    )


async def poll_courtlistener_new_cases() -> None:
    """Weekly: search for new EPR-related federal cases filed in the last 7 days.

    For each new case: fetch docket, get parties, classify initial filings,
    score preemption risk, store in litigation_cases, create docket alert.
    """
    from datetime import date, timedelta

    from sqlalchemy import select

    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.ingestion.courtlistener import (
        CourtListenerClient,
        EPR_LITIGATION_QUERIES,
        classify_litigation_event,
        infer_challenge_type,
        infer_plaintiff_type,
        score_preemption_risk,
    )
    from app.ingestion.bill_matcher import match_case_to_bill
    from app.models import CLAlertSubscription, LitigationCase, LitigationEvent

    if not settings.enable_courtlistener:
        log.info("cl_new_cases_skipped", reason="enable_courtlistener=false")
        return

    log.info("cl_new_cases_start")
    filed_after = date.today() - timedelta(days=7)
    added = 0
    errors = 0

    import asyncio as _asyncio

    async with CourtListenerClient() as cl:
        async with AsyncSessionLocal() as db:
            for _qi, (query_name, query_str) in enumerate(EPR_LITIGATION_QUERIES):
                # Space the /search/ calls — firing the seed queries back-to-back trips 429.
                if _qi > 0 and settings.courtlistener_request_delay_seconds > 0:
                    await _asyncio.sleep(settings.courtlistener_request_delay_seconds)
                try:
                    cases = await cl.search_epr_cases(query_str, filed_after=filed_after)
                except Exception as e:
                    log.warning("cl_search_failed", query=query_name, error=str(e))
                    errors += 1
                    continue

                for result in cases:
                    docket_id = result.get("docket_id") or result.get("id")
                    if not docket_id:
                        continue

                    existing = await db.execute(
                        select(LitigationCase).where(
                            LitigationCase.courtlistener_id == docket_id
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue

                    await _asyncio.sleep(1.5)

                    try:
                        docket = await cl.get_docket_details(docket_id)
                        await _asyncio.sleep(1.0)
                        parties = await cl.get_parties(docket_id)
                        await _asyncio.sleep(1.0)

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
                        await _asyncio.sleep(1.0)

                        classified_events = []
                        for entry in entries[:10]:
                            cls = await classify_litigation_event(
                                entry, case_name=case_name, court_id=court_id
                            )
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

                        # Match to bill
                        bill_id, inferred_state, _ = await match_case_to_bill(
                            db, new_case, cause=docket.get("cause", "") or ""
                        )
                        new_case.related_state = inferred_state
                        new_case.related_law_id = bill_id

                        for entry, cls in classified_events:
                            date_filed_entry_str = entry.get("date_filed")
                            db.add(LitigationEvent(
                                case_id=new_case.id,
                                courtlistener_entry_id=entry.get("id"),
                                event_type=cls["event_type"],
                                date_filed=date.fromisoformat(date_filed_entry_str) if date_filed_entry_str else None,
                                description=entry.get("description"),
                                summary=cls["summary"],
                                significance=cls["significance"],
                            ))

                        try:
                            alert = await cl.create_docket_alert(docket_id)
                            db.add(CLAlertSubscription(
                                alert_type="docket_alert",
                                cl_alert_id=alert.get("id"),
                                docket_id=docket_id,
                                active=True,
                            ))
                        except Exception as e:
                            log.warning("cl_docket_alert_failed", docket_id=docket_id, error=str(e))

                        await db.commit()
                        added += 1
                        log.info("cl_case_added", case_name=case_name, docket_id=docket_id)

                    except Exception as e:
                        log.error("cl_case_ingest_failed", docket_id=docket_id, error=str(e))
                        await db.rollback()
                        errors += 1

    log.info("cl_new_cases_complete", added=added, errors=errors)


async def refresh_active_cases() -> None:
    """Daily: refresh all active litigation cases with new docket entries.

    For each active case: fetch entries since last_activity_date, classify,
    update case_status, re-score preemption_risk, update bills.litigation_risk.
    Dispatches alerts for high/critical events.
    """
    from datetime import date, timedelta

    from sqlalchemy import select

    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.ingestion.courtlistener import (
        CourtListenerClient,
        classify_litigation_event,
        score_preemption_risk,
    )
    from app.models import Bill, LitigationCase, LitigationEvent
    from app.alerts.sendgrid_sender import SendGridSender
    from app.alerts.slack_sender import SlackSender
    from app.models import AlertSubscription

    if not settings.enable_courtlistener:
        log.info("cl_refresh_skipped", reason="enable_courtlistener=false")
        return

    log.info("cl_refresh_start")
    refreshed = 0
    new_events = 0
    errors = 0

    import asyncio as _asyncio

    async with CourtListenerClient() as cl:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(LitigationCase).where(LitigationCase.case_status == "active")
            )
            active_cases = result.scalars().all()

            email_sender = SendGridSender()
            slack_sender = SlackSender()

            # Load subscriptions once
            subs_result = await db.execute(
                select(AlertSubscription).where(AlertSubscription.active == True)  # noqa: E712
            )
            subs = subs_result.scalars().all()

            for case in active_cases:
                try:
                    after_date = case.last_activity_date or (date.today() - timedelta(days=30))
                    entries = await cl.get_docket_entries(case.courtlistener_id, after_date=after_date)
                    await _asyncio.sleep(1.0)

                    case_events_for_scoring = []
                    notable_events_for_alert = []

                    for entry in entries:
                        entry_id = entry.get("id")
                        if entry_id:
                            existing = await db.execute(
                                select(LitigationEvent).where(
                                    LitigationEvent.courtlistener_entry_id == entry_id
                                )
                            )
                            if existing.scalar_one_or_none():
                                continue

                        cls = await classify_litigation_event(
                            entry, case_name=case.case_name, court_id=case.court_id
                        )

                        date_filed_str = entry.get("date_filed")
                        date_filed = date.fromisoformat(date_filed_str) if date_filed_str else None

                        event = LitigationEvent(
                            case_id=case.id,
                            courtlistener_entry_id=entry_id,
                            event_type=cls["event_type"],
                            date_filed=date_filed,
                            description=entry.get("description"),
                            summary=cls["summary"],
                            significance=cls["significance"],
                        )
                        db.add(event)
                        new_events += 1

                        if date_filed and (
                            case.last_activity_date is None or date_filed > case.last_activity_date
                        ):
                            case.last_activity_date = date_filed

                        case_events_for_scoring.append(
                            {"date_filed": date_filed_str, "description": entry.get("description")}
                        )

                        # Detect injunctions/dismissals
                        if cls["event_type"] == "injunction_ruling" and cls["significance"] == "critical":
                            summary_lower = (cls.get("summary") or "").lower()
                            if "granted" in summary_lower:
                                case.case_status = "injunction_granted"
                                if case.related_law_id:
                                    bill_res = await db.execute(
                                        select(Bill).where(Bill.id == case.related_law_id)
                                    )
                                    bill = bill_res.scalar_one_or_none()
                                    if bill:
                                        bill.litigation_risk = "injunction_stayed"
                            elif "denied" in summary_lower:
                                case.case_status = "injunction_denied"
                        elif cls["event_type"] == "appeal":
                            case.case_status = "appealed"

                        if cls["significance"] in ("high", "critical"):
                            notable_events_for_alert.append((case, event, cls))

                    # Re-score preemption risk if there were new entries
                    if case_events_for_scoring:
                        case_dict = {
                            "case_name": case.case_name,
                            "court_id": case.court_id,
                            "challenge_type": case.challenge_type,
                            "key_plaintiffs": case.key_plaintiffs or [],
                            "date_filed": case.date_filed.isoformat() if case.date_filed else None,
                        }
                        new_risk = await score_preemption_risk(case_dict, case_events_for_scoring)
                        case.preemption_risk = new_risk
                        if case.related_law_id and case.case_status == "active":
                            bill_res = await db.execute(select(Bill).where(Bill.id == case.related_law_id))
                            linked_bill = bill_res.scalar_one_or_none()
                            if linked_bill and linked_bill.litigation_risk != "injunction_stayed":
                                linked_bill.litigation_risk = (
                                    "high" if new_risk >= 60 else "medium" if new_risk >= 30 else "low"
                                )

                    refreshed += 1

                    # Dispatch alerts for notable events
                    for notif_case, notif_event, notif_cls in notable_events_for_alert:
                        sig_emoji = "🚨" if notif_cls["significance"] == "critical" else "⚠️"
                        inj_prefix = "🚨 ENFORCEMENT STAYED — " if notif_case.case_status == "injunction_granted" else ""
                        subject = f"{inj_prefix}{sig_emoji} EPR Litigation: {notif_case.case_name}"
                        body = (
                            f"{inj_prefix}*{notif_event.event_type.replace('_', ' ').title()}* in "
                            f"_{notif_case.case_name}_\n"
                            f"Significance: {notif_cls['significance'].upper()}\n"
                            f"Summary: {notif_cls['summary'] or notif_event.description or '—'}\n"
                        )
                        if notif_case.cl_url:
                            body += f"\nDocket: {notif_case.cl_url}"

                        for sub in subs:
                            states = sub.states or []
                            if "ALL" not in states and notif_case.related_state and notif_case.related_state not in states:
                                continue
                            if sub.email and settings.sendgrid_api_key:
                                try:
                                    await email_sender.send_text_alert(sub.email, subject, body)
                                except Exception as e:
                                    log.warning("cl_refresh_email_failed", error=str(e))
                            if sub.slack_webhook:
                                try:
                                    await slack_sender.send_text_alert(sub.slack_webhook, body)
                                except Exception as e:
                                    log.warning("cl_refresh_slack_failed", error=str(e))

                    await db.commit()

                except Exception as e:
                    log.error("cl_refresh_case_failed", case_id=case.id, error=str(e))
                    await db.rollback()
                    errors += 1

    log.info("cl_refresh_complete", refreshed=refreshed, new_events=new_events, errors=errors)


async def reconcile_bill_matches() -> None:
    """Nightly: re-run bill matching for all unlinked litigation cases.

    Handles the case where a bill was ingested after the litigation case was
    first discovered, or where the initial seed ran before bills were classified.
    Also backfills related_state for cases that had court_id but no state yet.
    """
    from app.database import AsyncSessionLocal
    from app.ingestion.bill_matcher import run_bill_matching_pass

    log.info("cl_bill_match_reconcile_start")
    try:
        async with AsyncSessionLocal() as db:
            stats = await run_bill_matching_pass(db)
        log.info("cl_bill_match_reconcile_complete", **stats)
    except Exception as e:
        log.error("cl_bill_match_reconcile_failed", error=str(e))


async def run_source_link_audit_cycle() -> None:
    """Weekly: re-check the most-stale batch of bill "View Source" links and persist each verdict.

    Pings each distinct bills.source_url with the shared link-health classifier (app/links/health.py)
    and writes source_url_status / source_url_final / source_url_checked_at back onto every bill on
    that URL. The frontend (resolveSourceLink) then degrades gracefully: redirected -> the resolved
    URL, dead -> a LegiScan backup. "blocked" (WAF/timeout) is treated as could-not-verify, NOT
    broken, so a flaky government site never downgrades a good link.

    Bounded to settings.link_audit_batch_size distinct URLs per run, oldest-checked first, so the
    whole table is swept over several weeks rather than hammered in one pass.
    """
    import asyncio
    from datetime import datetime, timezone

    import httpx
    from sqlalchemy import text

    from app.database import AsyncSessionLocal
    from app.links.health import classify_async, normalize

    if not settings.enable_link_audit:
        log.info("source_link_audit_skipped", reason="enable_link_audit=false")
        return

    batch = settings.link_audit_batch_size
    # Pick the most-stale distinct URLs (never-checked first), then gather the bills on each.
    async with AsyncSessionLocal() as db:
        url_rows = (await db.execute(text(
            "select source_url from bills "
            "where source_url is not null and source_url <> '' "
            "group by source_url order by min(source_url_checked_at) asc nulls first "
            "limit :batch"
        ), {"batch": batch})).all()
        urls = [r[0] for r in url_rows]
        if not urls:
            log.info("source_link_audit_skipped", reason="no source links")
            return
        bill_rows = (await db.execute(text(
            "select id, source_url from bills where source_url = any(:urls)"
        ), {"urls": urls})).all()

    bills_by_url: dict[str, list[int]] = {}
    for bid, url in bill_rows:
        bills_by_url.setdefault(url, []).append(bid)

    log.info("source_link_audit_start", urls=len(urls), bills=len(bill_rows))

    # Distinct state hosts, so modest concurrency is polite; the semaphore just caps the burst.
    sem = asyncio.Semaphore(10)
    verdicts: dict[str, tuple[str, str | None]] = {}  # url -> (status, final_or_none)

    async with httpx.AsyncClient() as client:
        async def check(u: str) -> None:
            async with sem:
                res = await classify_async(u, client)
            final = res.final_url if (
                res.bucket == "redirected" and res.final_url
                and normalize(res.final_url) != normalize(u)
            ) else None
            verdicts[u] = (res.bucket, final)

        await asyncio.gather(*(check(u) for u in urls))

    counts: dict[str, int] = {}
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        for url, (status, final) in verdicts.items():
            counts[status] = counts.get(status, 0) + 1
            await db.execute(text(
                "update bills set source_url_status = :status, source_url_final = :final, "
                "source_url_checked_at = :ts where id = any(:ids)"
            ), {"status": status, "final": final, "ts": now, "ids": bills_by_url[url]})
        await db.commit()

    log.info("source_link_audit_complete", urls=len(urls), bills=len(bill_rows), **counts)


async def run_bill_text_refresh_cycle() -> None:
    """Daily: keep the full-text search index (bill_texts) current — Layer B Step 6.

    Selects the next bounded batch of bills that have no bill_texts row yet, or whose change_hash has
    moved since they were last indexed (so an amended bill gets re-fetched), fetches the cleaned text
    via the shared ladder (app/ingestion/bill_text.fetch_clean_text) and upserts it. The generated
    text_tsv column + GIN index (migration 028) are maintained by Postgres, so a refreshed row is
    immediately searchable. Bounded to settings.bill_text_refresh_batch_size per run, oldest-fetched
    first, so the corpus is swept over several days rather than hammering LegiScan in one pass — the
    one-time bulk load is scripts/backfill_bill_text.py.
    """
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.database import AsyncSessionLocal
    from app.ingestion.bill_text import SOURCE_NONE, fetch_clean_text
    from app.ingestion.legiscan import LegiScanClient
    from app.ingestion.openstates import OpenStatesClient

    if not settings.enable_bill_text_refresh:
        log.info("bill_text_refresh_skipped", reason="enable_bill_text_refresh=false")
        return

    batch = settings.bill_text_refresh_batch_size
    # Normally only in-scope bills are indexed; the all-bills sweep (a one-time corpus backfill)
    # drops that filter so out-of-scope bills get text too — see bill_text_refresh_all_bills.
    relevance_filter = "" if settings.bill_text_refresh_all_bills else "b.ce_relevant = true and "
    async with AsyncSessionLocal() as db:
        # Fetchable bills missing/stale text, never-indexed first, then oldest fetch. NULL-safe via
        # IS DISTINCT FROM so a NULL change_hash with an existing row is correctly treated as current.
        rows = (await db.execute(text(
            "select b.id, b.state, b.bill_number, b.openstates_id, b.legiscan_bill_id, "
            "b.source_url, b.change_hash "
            "from bills b left join bill_texts t on t.bill_id = b.id "
            f"where {relevance_filter}"
            "(b.legiscan_bill_id is not null or (b.openstates_id is not null "
            "and b.openstates_id not like 'hist:%') or b.source_url is not null) "
            "and (t.bill_id is null or t.indexed_change_hash is distinct from b.change_hash) "
            "order by t.fetched_at asc nulls first limit :batch"
        ), {"batch": batch})).all()

    if not rows:
        log.info("bill_text_refresh_skipped", reason="nothing stale")
        return

    log.info("bill_text_refresh_start", candidates=len(rows))
    upsert = text(
        "insert into bill_texts (bill_id, text, char_len, source, indexed_change_hash, fetched_at) "
        "values (:id, :text, :clen, :src, :hash, now()) "
        "on conflict (bill_id) do update set text = excluded.text, char_len = excluded.char_len, "
        "source = excluded.source, indexed_change_hash = excluded.indexed_change_hash, "
        "fetched_at = excluded.fetched_at"
    )

    wrote = no_text = 0
    by_source: dict[str, int] = {}
    async with LegiScanClient() as ls_client, OpenStatesClient() as os_client:
        async with AsyncSessionLocal() as db:
            for b in rows:
                try:
                    full_text, src = await fetch_clean_text(
                        ls_client, os_client, b, settings.openstates_request_delay_seconds
                    )
                except Exception as e:  # noqa: BLE001
                    log.warning("bill_text_refresh_fetch_failed", bill_id=b.id, error=str(e))
                    continue
                if not full_text or src == SOURCE_NONE:
                    no_text += 1
                    continue
                try:
                    await db.execute(upsert, {"id": b.id, "text": full_text, "clen": len(full_text),
                                              "src": src, "hash": b.change_hash})
                    await db.commit()
                    by_source[src] = by_source.get(src, 0) + 1
                    wrote += 1
                except Exception as e:  # noqa: BLE001 — one unstorable row must not abort the sweep
                    await db.rollback()
                    log.warning("bill_text_refresh_write_failed", bill_id=b.id, error=str(e))

    log.info("bill_text_refresh_complete", wrote=wrote, no_text=no_text, **by_source)


async def run_eurlex_cycle() -> None:
    """Weekly: keep EU-central law current. Re-runs the EUR-Lex/CELLAR SPARQL discovery and ingests
    only newly-published in-force acts (only_new), classifying them with the region-aware pipeline.
    Idempotent (upsert by celex_id) and bounded by settings.max_eurlex_acts_per_run. Dormant unless
    enable_eurlex_ingestion; the one-time bulk backfill is scripts/ingest_eurlex.py --bulk.
    """
    from app.ingestion.eurlex import sync_eurlex

    if not settings.enable_eurlex_ingestion:
        log.info("eurlex_cycle_skipped", reason="enable_eurlex_ingestion=false")
        return

    summary = await sync_eurlex(
        in_force_only=settings.eurlex_in_force_only,
        classify=True,
        only_new=True,
        max_acts=settings.max_eurlex_acts_per_run,
    )
    log.info("eurlex_cycle_complete", **summary)
