"""Static demo snapshot exporter.

Exports pre-computed demo data to JSON files in data/demo_snapshot/.
Use this as a live demo backup in case of network or database issues.

Exports:
  - oregon_companies_ranked.json  Top-50 companies for SB 582 with scores + costs
  - exposure_briefs.json          Pre-generated briefs for all top-50 companies
  - oregon_bills.json             All Oregon EPR bills with compliance metadata

Usage:
    python scripts/export_demo_snapshot.py
    python scripts/export_demo_snapshot.py --bill "SB 582" --top-n 50
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "demo_snapshot",
)


def _default_serializer(obj):
    """JSON serializer for datetime and UUID objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    import uuid
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


async def export_snapshot(bill_pattern: str, top_n: int) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import AsyncSessionLocal
    from app.models import (
        Bill,
        Company,
        CompanyMaterial,
        CompanyStatePresence,
        ExposureBrief,
        ImpactScore,
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # ----------------------------------------------------------------
        # 1. Oregon EPR bills
        # ----------------------------------------------------------------
        print("Exporting Oregon EPR bills...")
        bills_result = await db.execute(
            select(Bill).where(
                Bill.state == "OR",
                Bill.epr_relevant == True,  # noqa: E712
            )
        )
        bills = bills_result.scalars().all()

        bills_data = [
            {
                "id": bill.id,
                "bill_number": bill.bill_number,
                "title": bill.title,
                "status": bill.status,
                "status_date": bill.status_date.isoformat() if bill.status_date else None,
                "source_url": bill.source_url,
                "epr_relevant": bill.epr_relevant,
                "confidence_score": bill.confidence_score,
                "material_categories": bill.material_categories,
                "compliance_details": bill.compliance_details,
                "ai_summary": bill.ai_summary,
                "urgency": bill.urgency,
            }
            for bill in bills
        ]

        _write(os.path.join(OUTPUT_DIR, "oregon_bills.json"), bills_data)
        print(f"  -> {len(bills_data)} bills exported")

        # ----------------------------------------------------------------
        # 2. Top-N companies ranked by composite score for target bill
        # ----------------------------------------------------------------
        print(f"\nExporting company rankings for '{bill_pattern}'...")
        bill_result = await db.execute(
            select(Bill).where(
                Bill.state == "OR",
                Bill.bill_number.ilike(f"%{bill_pattern}%"),
                Bill.epr_relevant == True,  # noqa: E712
            ).limit(1)
        )
        bill = bill_result.scalar_one_or_none()

        if bill is None:
            print(f"  [WARN] Bill '{bill_pattern}' not found. Skipping ranking export.")
            ranked_data = []
        else:
            scores_result = await db.execute(
                select(ImpactScore)
                .options(
                    selectinload(ImpactScore.company).selectinload(Company.materials),
                    selectinload(ImpactScore.company).selectinload(Company.state_presences),
                )
                .where(ImpactScore.bill_id == bill.id)
                .order_by(ImpactScore.composite_score.desc())
                .limit(top_n)
            )
            scores = scores_result.scalars().all()

            ranked_data = []
            for rank, score in enumerate(scores, 1):
                company = score.company
                if not company:
                    continue
                ranked_data.append({
                    "rank": rank,
                    "company_id": str(company.id),
                    "company_name": company.name,
                    "hq_state": company.hq_state,
                    "naics_codes": company.naics_codes,
                    "composite_score": score.composite_score,
                    "material_score": score.material_score,
                    "geographic_score": score.geographic_score,
                    "severity_score": score.severity_score,
                    "estimated_annual_cost": score.estimated_annual_cost,
                    "cost_confidence": score.cost_confidence,
                    "volume_confidence": score.volume_confidence,
                    "calculated_at": score.calculated_at.isoformat() if score.calculated_at else None,
                    "materials": [
                        {
                            "material_category": m.material_category,
                            "annual_volume_tonnes": m.annual_volume_tonnes,
                            "volume_confidence": m.volume_confidence,
                            "source": m.source,
                        }
                        for m in company.materials
                    ],
                    "state_presences": [
                        {
                            "state": p.state,
                            "presence_type": p.presence_type,
                            "is_primary": p.is_primary,
                        }
                        for p in company.state_presences
                    ],
                })

        _write(os.path.join(OUTPUT_DIR, "oregon_companies_ranked.json"), {
            "bill_number": bill.bill_number if bill else bill_pattern,
            "bill_title": bill.title if bill else None,
            "exported_at": now.isoformat(),
            "companies": ranked_data,
        })
        print(f"  -> {len(ranked_data)} companies exported")

        # ----------------------------------------------------------------
        # 3. Exposure briefs
        # ----------------------------------------------------------------
        print("\nExporting exposure briefs...")
        company_ids = [item["company_id"] for item in ranked_data]

        if bill and company_ids:
            import uuid
            briefs_result = await db.execute(
                select(ExposureBrief).where(
                    ExposureBrief.bill_id == bill.id,
                    ExposureBrief.company_id.in_([uuid.UUID(cid) for cid in company_ids]),
                )
            )
            briefs = briefs_result.scalars().all()

            # Build rank lookup
            rank_map = {item["company_id"]: item["rank"] for item in ranked_data}

            briefs_data = [
                {
                    "rank": rank_map.get(str(b.company_id), 999),
                    "company_id": str(b.company_id),
                    "bill_id": b.bill_id,
                    "brief": b.brief_json,
                    "generated_at": b.generated_at.isoformat() if b.generated_at else None,
                    "ttl_expires_at": b.ttl_expires_at.isoformat() if b.ttl_expires_at else None,
                }
                for b in briefs
            ]
            briefs_data.sort(key=lambda x: x["rank"])
        else:
            briefs_data = []

        _write(os.path.join(OUTPUT_DIR, "exposure_briefs.json"), {
            "exported_at": now.isoformat(),
            "briefs": briefs_data,
        })
        print(f"  -> {len(briefs_data)} briefs exported")

    print(f"\n{'='*55}")
    print(f"  Snapshot saved to: {OUTPUT_DIR}")
    print(f"  Files:")
    for fname in ["oregon_bills.json", "oregon_companies_ranked.json", "exposure_briefs.json"]:
        path = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(path):
            size_kb = os.path.getsize(path) / 1024
            print(f"    {fname:<40} {size_kb:>7.1f} KB")
    print(f"{'='*55}\n")


def _write(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=_default_serializer, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export static demo snapshot to data/demo_snapshot/")
    parser.add_argument("--bill", default="SB 582", help="Bill number pattern (default: SB 582)")
    parser.add_argument("--top-n", type=int, default=50, help="Number of top companies to export (default: 50)")
    args = parser.parse_args()

    asyncio.run(export_snapshot(args.bill, args.top_n))


if __name__ == "__main__":
    main()
