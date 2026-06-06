"""Compliance cost estimator.

Resolves fee structures per bill from compliance_details.fees, with category-level
benchmarks for bills that have no published fee data. The old OR SB 582 universal
fallback has been removed — that rate only applies to OR SB 582 itself (now stored
in its seed data as a published_range_midpoint).

Fee basis hierarchy (highest to lowest data quality):
  *_published          — real published fee schedule (no confidence cap)
  published_range_midpoint — real range, using midpoint (cap 0.70)
  industry_benchmark   — comparable enacted programs (cap 0.50)
  category_benchmark   — per-material-category fallback (cap 0.35)
  no_fee_data          — no data; estimator returns None
  no_monetary_fee      — bill has no producer monetary fee; returns None

All methods are synchronous — pure arithmetic, no DB or async needed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Bill, Company, CompanyMaterial

# Confidence caps by fee data quality
_FEE_CONFIDENCE_CAPS: dict[str, float] = {
    "calrecycle_published": 1.0,
    "paintcare_published": 1.0,
    "mrc_published": 1.0,
    "published_range_midpoint": 0.70,
    "industry_benchmark": 0.50,
    "category_benchmark": 0.35,
}

# Fallback benchmarks for bill categories that have no bill-level fee data at all.
# Only applies when fees.fee_structure_source == "no_fee_data" and material_categories
# matches a key here.
CATEGORY_BENCHMARKS: dict[str, dict] = {
    "batteries": {
        "fee_per_ton": 120.0,
        "registration_fee_usd": 500.0,
        "fee_structure_source": "category_benchmark",
    },
    "pharmaceuticals": {
        "fee_per_ton": 90.0,
        "registration_fee_usd": 250.0,
        "fee_structure_source": "category_benchmark",
    },
    "textiles": {
        "fee_per_ton": 80.0,
        "registration_fee_usd": 500.0,
        "fee_structure_source": "category_benchmark",
    },
    "solar_panels": {
        "fee_per_ton": 200.0,
        "registration_fee_usd": 1000.0,
        "fee_structure_source": "category_benchmark",
    },
}


class CostEstimator:
    """Estimates annual compliance cost for a (company, bill) pair."""

    def estimate(
        self,
        company: "Company",
        bill: "Bill",
        relevant_materials: list["CompanyMaterial"],
    ) -> dict:
        """Return estimated annual compliance cost and confidence band.

        Args:
            company: The Company ORM instance.
            bill: The Bill ORM instance.
            relevant_materials: CompanyMaterial rows already filtered to the
                bill's material categories — caller is responsible for filtering.

        Returns:
            {
                "estimated_annual_cost": float | None,
                "cost_confidence": float,
                "fee_basis": str,
            }
        """
        compliance = bill.compliance_details or {}
        fees_block = compliance.get("fees") or {}

        # Resolve fee structure
        fee_structure_source = fees_block.get("fee_structure_source") or "unknown"

        # Bills with no producer monetary fee (R2R, deposit bills, content mandates)
        if fees_block.get("fee_structure") == "no_monetary_fee":
            return {"estimated_annual_cost": None, "cost_confidence": 0.0, "fee_basis": "no_monetary_fee"}

        # Per-unit path: fee_per_unit_usd * units_per_tonne → effective $/tonne
        fee_per_unit = fees_block.get("fee_per_unit_usd")
        units_per_tonne = fees_block.get("units_per_tonne")
        registration_fee = float(fees_block.get("registration_fee_usd") or 0.0)

        if fee_per_unit is not None and units_per_tonne is not None:
            effective_per_ton = float(fee_per_unit) * float(units_per_tonne)

        # Direct per-ton path
        elif fees_block.get("fee_per_ton") is not None:
            effective_per_ton = float(fees_block["fee_per_ton"])

        # Category benchmark fallback
        else:
            benchmark = None
            for cat in (bill.material_categories or []):
                if cat in CATEGORY_BENCHMARKS:
                    benchmark = CATEGORY_BENCHMARKS[cat]
                    break
            if benchmark is None:
                return {"estimated_annual_cost": None, "cost_confidence": 0.0, "fee_basis": "no_fee_data"}
            effective_per_ton = benchmark["fee_per_ton"]
            registration_fee = benchmark["registration_fee_usd"]
            fee_structure_source = benchmark["fee_structure_source"]

        # Sum relevant material volumes
        volumes = [
            m.annual_volume_tonnes
            for m in relevant_materials
            if m.annual_volume_tonnes is not None
        ]

        if not volumes:
            return {"estimated_annual_cost": None, "cost_confidence": 0.0, "fee_basis": fee_structure_source}

        total_volume = sum(volumes)
        # +5% penalty risk multiplier
        annual_cost = registration_fee + (total_volume * effective_per_ton * 1.05)

        # Confidence = min(volume confidences) capped by fee data quality
        confidences = [
            m.volume_confidence
            for m in relevant_materials
            if m.volume_confidence is not None
        ]
        volume_confidence = min(confidences) if confidences else 0.5
        fee_cap = _FEE_CONFIDENCE_CAPS.get(fee_structure_source, 0.25)
        cost_confidence = min(volume_confidence, fee_cap)

        return {
            "estimated_annual_cost": round(annual_cost, 2),
            "cost_confidence": cost_confidence,
            "fee_basis": fee_structure_source,
        }
