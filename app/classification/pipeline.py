import os
from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.classification.haiku_classifier import TRACKED_INSTRUMENTS, HaikuClassifier
from app.classification.keywords import KeywordFilter
from app.classification.materials import normalize_materials
from app.classification.sonnet_extractor import SonnetExtractor
from app.config import settings
from app.models import (
    Bill,
    BillChange,
    BillText,
    ClassificationChange,
    ComplianceDeadline,
)

log = structlog.get_logger()


def _classification_snapshot(bill: Bill) -> dict:
    """The classification fields the audit log tracks, as a JSON-able dict."""
    return {
        "ce_relevant": bill.ce_relevant,
        "confidence_score": bill.confidence_score,
        "instrument_type": bill.instrument_type,
        "instrument_types": bill.instrument_types,
        "needs_review": bool(getattr(bill, "needs_review", False)),
    }


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

    async def run(
        self,
        db: AsyncSession,
        bills: list[Bill],
        skip_keyword_filter: bool = False,
        source: str = "classify",
    ) -> PipelineResult:
        result = PipelineResult(total=len(bills))
        # Tag every audit row from this invocation with the Cloud Run execution name (set on job
        # runs) so a whole reclassify run's drops can be queried together; fall back to the caller's
        # source tag for local/API runs. See ClassificationChange.
        run_id = os.environ.get("CLOUD_RUN_EXECUTION") or source

        # Stage 1: keyword filter. The keyword set (data/seed/epr_keywords.json) is tuned to US bill
        # language, so a curated, definitionally in-scope source (e.g. EU-central acts from EUR-Lex)
        # passes skip_keyword_filter=True to send every bill straight to the LLM rather than being
        # gated by US keywords. See scripts/ingest_eurlex.py.
        if skip_keyword_filter:
            candidates = list(bills)
        else:
            candidates = [
                b for b in bills
                if self.keyword_filter.passes_threshold(
                    b.title or "", b.description or ""
                )
            ]
        result.passed_keyword = len(candidates)
        log.info(
            "keyword_filter_done",
            total=len(bills),
            candidates=len(candidates),
            skipped=skip_keyword_filter,
        )

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
                    bill.material_categories = normalize_materials(kw_score.material_hints)
            await db.commit()
            return result

        # Feed the classifier any persisted full text. Without this Haiku judges on title +
        # (often empty) description alone and bails to is_ce_relevant=false on thin input — which
        # silently dropped clearly-relevant bills in past reclassify runs. We pass the stored text
        # where we have it; bills with none fall back to title/description + the keyword rescue net
        # below (we don't fetch live text here — that's a heavier, separate backfill).
        text_by_id: dict[int, str] = {}
        cand_ids = [b.id for b in candidates if b.id is not None]
        if cand_ids:
            rows = await db.execute(
                select(BillText.bill_id, BillText.text).where(BillText.bill_id.in_(cand_ids))
            )
            text_by_id = {bid: (txt or "") for bid, txt in rows.all()}

        haiku_inputs = [
            {
                "bill_obj": b,
                "state": b.state,
                "region": b.region,
                "bill_number": b.bill_number or "",
                "title": b.title or "",
                "description": b.description or "",
                "text_excerpt": text_by_id.get(b.id, ""),
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

            old_snapshot = _classification_snapshot(bill_obj)

            bill_obj.confidence_score = hr.confidence
            # In scope if the classifier judged it EPR-relevant, OR it's tagged with an instrument
            # that's circular-economy policy by definition (right-to-repair, deposit-return, etc.),
            # at decent confidence. labeling/preemption are intentionally NOT in TRACKED_INSTRUMENTS
            # — they're generic and ride in only via is_ce_relevant (see haiku_classifier.py).
            haiku_in_scope = hr.confidence >= 0.4 and (
                hr.is_ce_relevant or any(it in TRACKED_INSTRUMENTS for it in hr.instrument_types)
            )
            # Rescue net: if Haiku would drop the bill but the title/description carries a
            # near-certain (Tier-1) keyword signal, keep it in scope and flag for review rather than
            # silently shedding it. This catches bills Haiku bailed on for lack of text (e.g. titles
            # like "...Producer Responsibility..." / "...Packaging Reduction Act"). See
            # KeywordFilter.strong_signal and the reclassify post-mortem.
            rescued = False
            if not haiku_in_scope and self.keyword_filter.strong_signal(
                bill_dict.get("title", ""),
                bill_dict.get("description", ""),
                bill_dict.get("text_excerpt", ""),
            ):
                rescued = True

            bill_obj.ce_relevant = haiku_in_scope or rescued
            bill_obj.needs_review = rescued
            bill_obj.material_categories = normalize_materials(hr.material_categories)
            bill_obj.instrument_type = hr.instrument_type
            bill_obj.instrument_types = hr.instrument_types
            bill_obj.urgency = hr.urgency
            bill_obj.ai_summary = hr.reasoning
            bill_obj.policy_stance = hr.stance
            bill_obj.stance_source = "ai"

            if hr.confidence >= 0.7 and hr.is_ce_relevant:
                high_confidence_bills.append(bill_obj)

            # Audit: record a row whenever the relevance decision or the primary instrument moved, so
            # the run is diffable and a regression (e.g. a starved run shedding bills) is recoverable.
            new_snapshot = _classification_snapshot(bill_obj)
            if (
                old_snapshot["ce_relevant"] != new_snapshot["ce_relevant"]
                or old_snapshot["instrument_type"] != new_snapshot["instrument_type"]
            ):
                db.add(
                    ClassificationChange(
                        bill_id=bill_obj.id,
                        run_id=run_id,
                        old_value=old_snapshot,
                        new_value=new_snapshot,
                    )
                )

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

        from sqlalchemy import select as _select

        from app.ingestion.openstates import OpenStatesClient

        async with OpenStatesClient() as os_client:
            for bill in high_confidence_bills[: settings.max_sonnet_calls_per_run]:
                try:
                    # Fetch the latest version's full text. US bills re-fetch from OpenStates (the
                    # authoritative live source); other regions (e.g. EU from EUR-Lex) have no
                    # per-version text API, so their text was persisted to bill_texts at ingest —
                    # read it from there.
                    # NOTE: these awaits (text fetch + Sonnet extract) run with NO open DB
                    # transaction — the previous iteration's commit closed it — so the connection sits
                    # plain `idle`, holding no locks, during the slow external calls. Holding a tx
                    # across them is what previously stranded a connection idle-in-transaction on a
                    # bills lock when a call hung (see the per-bill commit below).
                    full_text = ""
                    if bill.region == "US" and bill.openstates_id:
                        full_text = await os_client.get_bill_text(bill.openstates_id)
                    else:
                        full_text = (
                            await db.execute(
                                _select(BillText.text).where(BillText.bill_id == bill.id)
                            )
                        ).scalar_one_or_none() or ""

                    extraction = await self.sonnet.extract(
                        state=bill.state,
                        bill_number=bill.bill_number or "",
                        title=bill.title or "",
                        full_text=full_text,
                        region=bill.region,
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
                            region=bill.region,
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
