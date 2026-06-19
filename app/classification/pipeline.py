from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.classification.haiku_classifier import TRACKED_INSTRUMENTS, HaikuClassifier
from app.classification.keywords import KeywordFilter
from app.classification.sonnet_extractor import SonnetExtractor
from app.config import settings
from app.models import Bill, BillChange, ComplianceDeadline

log = structlog.get_logger()


@dataclass
class PipelineResult:
    total: int = 0
    passed_keyword: int = 0
    classified_haiku: int = 0
    extracted_sonnet: int = 0
    errors: list[str] = field(default_factory=list)


class ClassificationPipeline:
    def __init__(self):
        self.keyword_filter = KeywordFilter()
        self.haiku = HaikuClassifier() if settings.enable_llm_classification else None
        self.sonnet = SonnetExtractor() if settings.enable_sonnet_extraction else None

    async def run(self, db: AsyncSession, bills: list[Bill]) -> PipelineResult:
        result = PipelineResult(total=len(bills))

        # Stage 1: keyword filter
        candidates = [
            b for b in bills
            if self.keyword_filter.passes_threshold(
                b.title or "", b.description or ""
            )
        ]
        result.passed_keyword = len(candidates)
        log.info("keyword_filter_done", total=len(bills), candidates=len(candidates))

        # Mark non-candidates as not relevant (confidence_score = 0)
        non_candidates = set(b.id for b in bills) - set(b.id for b in candidates)
        for bill in bills:
            if bill.id in non_candidates:
                bill.confidence_score = 0.0
                bill.ce_relevant = False

        if not candidates:
            await db.commit()
            return result

        # Stage 2: Haiku classification
        if not settings.enable_llm_classification:
            # Mark as keyword-passed but not LLM-classified
            for bill in candidates:
                bill.confidence_score = -1.0  # sentinel: awaiting LLM
                bill.ce_relevant = True
                kw_score = self.keyword_filter.score(bill.title or "", bill.description or "")
                if kw_score.material_hints:
                    bill.material_categories = kw_score.material_hints
            await db.commit()
            return result

        haiku_inputs = [
            {
                "bill_obj": b,
                "state": b.state,
                "bill_number": b.bill_number or "",
                "title": b.title or "",
                "description": b.description or "",
            }
            for b in candidates
        ]

        haiku_results = await self.haiku.classify_batch(
            haiku_inputs, max_calls=settings.max_haiku_calls_per_run
        )
        result.classified_haiku = len(haiku_results)

        classified_ids = set()
        high_confidence_bills: list[Bill] = []
        for bill_dict, hr in haiku_results:
            bill_obj: Bill = bill_dict["bill_obj"]
            classified_ids.add(bill_obj.id)

            bill_obj.confidence_score = hr.confidence
            # In scope if the classifier judged it EPR-relevant, OR it's tagged with an instrument
            # that's circular-economy policy by definition (right-to-repair, deposit-return, etc.),
            # at decent confidence. labeling/preemption are intentionally NOT in TRACKED_INSTRUMENTS
            # — they're generic and ride in only via is_ce_relevant (see haiku_classifier.py).
            bill_obj.ce_relevant = hr.confidence >= 0.4 and (
                hr.is_ce_relevant or hr.instrument_type in TRACKED_INSTRUMENTS
            )
            bill_obj.material_categories = hr.material_categories
            bill_obj.instrument_type = hr.instrument_type
            bill_obj.urgency = hr.urgency
            bill_obj.ai_summary = hr.reasoning
            bill_obj.policy_stance = hr.stance
            bill_obj.stance_source = "ai"

            if hr.confidence >= 0.7 and hr.is_ce_relevant:
                high_confidence_bills.append(bill_obj)

        # Bills that passed keyword filter but Haiku failed — mark as awaiting LLM
        # so they exit the classification loop and don't block future batches.
        for bill_dict in haiku_inputs:
            bill_obj = bill_dict["bill_obj"]
            if bill_obj.id not in classified_ids:
                bill_obj.confidence_score = -1.0
                bill_obj.ce_relevant = True

        await db.commit()

        # Stage 3: Sonnet extraction for high-confidence bills
        if not settings.enable_sonnet_extraction or not self.sonnet:
            return result

        from app.ingestion.openstates import OpenStatesClient

        async with OpenStatesClient() as os_client:
            for bill in high_confidence_bills[: settings.max_sonnet_calls_per_run]:
                try:
                    # Fetch the latest version's full text from OpenStates.
                    # (LegiScan is dormant — its free tier serves WV data; see migration 004.)
                    # NOTE: these awaits (OpenStates fetch + Sonnet extract) run with NO open DB
                    # transaction — the previous iteration's commit closed it — so the connection sits
                    # plain `idle`, holding no locks, during the slow external calls. Holding a tx
                    # across them is what previously stranded a connection idle-in-transaction on a
                    # bills lock when a call hung (see the per-bill commit below).
                    full_text = ""
                    if bill.openstates_id:
                        full_text = await os_client.get_bill_text(bill.openstates_id)

                    extraction = await self.sonnet.extract(
                        state=bill.state,
                        bill_number=bill.bill_number or "",
                        title=bill.title or "",
                        full_text=full_text,
                    )
                    bill.compliance_details = extraction.raw_json

                    # Create ComplianceDeadline rows from extracted deadlines
                    for dl in extraction.deadlines:
                        deadline_date_str = dl.get("date")
                        if not deadline_date_str:
                            continue
                        try:
                            deadline_date = date.fromisoformat(deadline_date_str[:10])
                        except ValueError:
                            continue
                        cd = ComplianceDeadline(
                            bill_id=bill.id,
                            state=bill.state,
                            deadline_type=dl.get("type", "compliance"),
                            deadline_date=deadline_date,
                            description=dl.get("description", ""),
                        )
                        db.add(cd)

                    # Commit per bill: bounds the write transaction to a single bill and ensures the
                    # NEXT iteration's external calls run outside any transaction (no held locks).
                    await db.commit()
                    result.extracted_sonnet += 1
                except Exception as e:
                    # Discard this bill's partial work so the session is clean for the next iteration.
                    await db.rollback()
                    log.error("sonnet_extraction_failed", bill_id=bill.id, error=str(e))
                    result.errors.append(str(e))

        return result
