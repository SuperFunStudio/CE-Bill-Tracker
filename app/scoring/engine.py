"""Composite impact scoring engine.

Produces an ImpactScore for each (company, bill) pair using three sub-scores:
  - Material score: volume-weighted overlap between company materials and bill scope
  - Geographic score: company's operational presence in the bill's state
  - Severity score: bill progression likelihood \u00d7 fee-structure impact

Usage:
    engine = make_engine()  # reads weights from settings
    score = engine.compute(company, bill, materials, presences, all_volumes)
    db.add(score)
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog

from app.models import ImpactScore
from app.scoring.cost_estimator import CostEstimator

if TYPE_CHECKING:
    from app.models import Bill, Company, CompanyMaterial, CompanyStatePresence

log = structlog.get_logger()

# Geographic presence weights (v2.0 — operational presence over HQ)
PRESENCE_WEIGHTS: dict[str, float] = {
    "manufacturing": 100.0,
    "distribution": 85.0,
    "headquarters": 80.0,
    "retail": 60.0,
    "registered_agent": 30.0,
    "sales": 20.0,
}

# Bill status \u2192 likelihood sub-score
LIKELIHOOD_MAP: dict[str, float] = {
    "introduced": 20.0,
    "committee": 40.0,
    "in_committee": 40.0,
    "one_chamber": 60.0,
    "passed_chamber": 60.0,
    "both_chambers": 80.0,
    "signed": 100.0,
    "enacted": 100.0,
}


class ScoringEngine:
    def __init__(
        self,
        material_weight: float,
        geographic_weight: float,
        severity_weight: float,
    ) -> None:
        self.material_weight = material_weight
        self.geographic_weight = geographic_weight
        self.severity_weight = severity_weight

    # ------------------------------------------------------------------
    # Sub-score 1: Material
    # ------------------------------------------------------------------

    def score_material(
        self,
        company_materials: list["CompanyMaterial"],
        bill_material_categories: list[str],
        all_companies_volumes: dict[uuid.UUID, float],
        company_id: uuid.UUID,
    ) -> tuple[float, float]:
        """Volume-weighted material overlap score.

        Returns (score 0\u2013100, volume_confidence 0\u20131).
        Falls back to count-based scoring when volume data is absent.
        """
        relevant = [
            m for m in company_materials
            if m.material_category in bill_material_categories
        ]

        if not relevant:
            return 0.0, 0.0

        # Check if we have volume data for any relevant material
        volumes_with_data = [m for m in relevant if m.annual_volume_tonnes is not None]

        if volumes_with_data:
            company_vol = sum(m.annual_volume_tonnes for m in volumes_with_data)  # type: ignore[arg-type]
            # total_vol = sum of all companies' volumes for normalization
            total_vol = sum(all_companies_volumes.values()) if all_companies_volumes else company_vol
            if total_vol > 0:
                score = min(company_vol / total_vol * 100.0, 100.0)
            else:
                score = 0.0

            confidences = [
                m.volume_confidence for m in relevant if m.volume_confidence is not None
            ]
            confidence = sum(confidences) / len(confidences) if confidences else 0.5
            return score, confidence

        # Fallback: count-based, flag as zero confidence
        score = min(len(relevant) / 3.0 * 100.0, 100.0)
        return score, 0.0

    # ------------------------------------------------------------------
    # Sub-score 2: Geographic
    # ------------------------------------------------------------------

    def score_geographic(
        self,
        state_presences: list["CompanyStatePresence"],
        bill_state: str,
    ) -> float:
        """Max presence-type weight for the bill's state."""
        matching = [p for p in state_presences if p.state == bill_state]
        if not matching:
            return 0.0
        return max(PRESENCE_WEIGHTS.get(p.presence_type, 0.0) for p in matching)

    # ------------------------------------------------------------------
    # Sub-score 3: Severity
    # ------------------------------------------------------------------

    def score_severity(self, bill: "Bill") -> float:
        """Split likelihood × 0.4 + impact × 0.6."""
        likelihood = LIKELIHOOD_MAP.get(bill.status or "", 20.0)

        compliance = bill.compliance_details or {}
        fees_block = compliance.get("fees") or {}

        # Derive effective $/tonne from the richer fees_block structure
        fee_per_ton: float | None = None
        if fees_block.get("fee_per_ton") is not None:
            fee_per_ton = float(fees_block["fee_per_ton"])
        elif fees_block.get("fee_per_unit_usd") is not None and fees_block.get("units_per_tonne") is not None:
            fee_per_ton = float(fees_block["fee_per_unit_usd"]) * float(fees_block["units_per_tonne"])

        if fee_per_ton is not None and fee_per_ton > 0:
            # Scale: $500/tonne -> 100 (packaging EPR upper bound); cap at 100
            impact = min(fee_per_ton / 500.0 * 100.0, 100.0)
        elif compliance:
            impact = 50.0
        else:
            impact = 30.0

        return likelihood * 0.4 + impact * 0.6

    # ------------------------------------------------------------------
    # Composite
    # ------------------------------------------------------------------

    def compute(
        self,
        company: "Company",
        bill: "Bill",
        company_materials: list["CompanyMaterial"],
        state_presences: list["CompanyStatePresence"],
        all_companies_volumes: dict[uuid.UUID, float],
    ) -> ImpactScore:
        """Compute composite ImpactScore for (company, bill).

        Returns an ImpactScore ORM instance. The caller is responsible for
        adding it to the session and committing.
        """
        bill_categories: list[str] = bill.material_categories or []

        material_score, volume_confidence = self.score_material(
            company_materials, bill_categories, all_companies_volumes, company.id
        )
        geographic_score = self.score_geographic(state_presences, bill.state)
        severity_score = self.score_severity(bill)

        composite = (
            material_score * self.material_weight
            + geographic_score * self.geographic_weight
            + severity_score * self.severity_weight
        )

        # Cost estimate — filter materials to bill's categories for estimator
        relevant_materials = [
            m for m in company_materials if m.material_category in bill_categories
        ]
        cost_data = CostEstimator().estimate(company, bill, relevant_materials)

        score_breakdown = {
            "material_score": material_score,
            "geographic_score": geographic_score,
            "severity_score": severity_score,
            "material_weight": self.material_weight,
            "geographic_weight": self.geographic_weight,
            "severity_weight": self.severity_weight,
            "volume_confidence": volume_confidence,
            "bill_status": bill.status,
            "bill_state": bill.state,
            "fee_basis": cost_data.get("fee_basis", "unknown"),
            # True when the fee traces to a published schedule / enacted text (not a benchmark guess).
            # The UI shows "grounded in enacted law" vs "estimated" off this. See app/synthesis/fee_citations.
            "fee_grounded": cost_data.get("grounded", False),
        }

        log.info(
            "score_computed",
            company_id=str(company.id),
            bill_id=bill.id,
            composite_score=round(composite, 2),
            material_score=round(material_score, 2),
            geographic_score=round(geographic_score, 2),
            severity_score=round(severity_score, 2),
        )

        return ImpactScore(
            company_id=company.id,
            bill_id=bill.id,
            composite_score=round(composite, 2),
            material_score=round(material_score, 2),
            geographic_score=round(geographic_score, 2),
            severity_score=round(severity_score, 2),
            estimated_annual_cost=cost_data["estimated_annual_cost"],
            cost_confidence=cost_data["cost_confidence"],
            volume_confidence=volume_confidence,
            score_breakdown=score_breakdown,
        )


def make_engine() -> ScoringEngine:
    """Factory: build ScoringEngine from app settings."""
    from app.config import settings

    return ScoringEngine(
        material_weight=settings.scoring_material_weight,
        geographic_weight=settings.scoring_geographic_weight,
        severity_weight=settings.scoring_severity_weight,
    )
