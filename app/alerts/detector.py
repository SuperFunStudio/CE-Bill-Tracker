import uuid

from app.models import Bill, BillChange

SIGNIFICANT_STATUSES = {
    "introduced", "in_committee", "passed_chamber",
    "passed", "enrolled", "enacted", "signed", "vetoed", "failed",
}

# Minimum composite score shift (0–100 scale) that triggers an impact_score_change alert
SCORE_DELTA_THRESHOLD = 10.0


class ChangeDetector:
    def detect_changes(self, bill: Bill, new_data: dict) -> list[BillChange]:
        """Compare stored bill state against fresh API data. Return list of BillChange objects."""
        changes: list[BillChange] = []

        new_status = new_data.get("status")
        if new_status and bill.status != new_status:
            changes.append(
                BillChange(
                    bill_id=bill.id,
                    change_type="status_change",
                    old_value={"status": bill.status},
                    new_value={"status": new_status},
                )
            )

        new_hash = new_data.get("change_hash")
        if new_hash and bill.change_hash and bill.change_hash != new_hash:
            changes.append(
                BillChange(
                    bill_id=bill.id,
                    change_type="text_update",
                    old_value={"change_hash": bill.change_hash},
                    new_value={"change_hash": new_hash},
                )
            )

        return changes

    def detect_score_changes(
        self,
        company_id: uuid.UUID,
        bill_id: int,
        old_score: float,
        new_score: float,
        old_cost: float | None,
        new_cost: float | None,
    ) -> BillChange | None:
        """Return a BillChange if composite_score shifted by >= SCORE_DELTA_THRESHOLD points.

        Called from run_scoring_cycle() after each (company, bill) recomputation.
        The resulting BillChange is persisted alongside the new ImpactScore and
        picked up by the alert dispatcher in the next alert_dispatch run.
        """
        delta = abs(new_score - old_score)
        if delta < SCORE_DELTA_THRESHOLD:
            return None
        return BillChange(
            bill_id=bill_id,
            change_type="impact_score_change",
            old_value={
                "company_id": str(company_id),
                "composite_score": old_score,
                "estimated_annual_cost": old_cost,
            },
            new_value={
                "company_id": str(company_id),
                "composite_score": new_score,
                "estimated_annual_cost": new_cost,
            },
        )

    def is_alert_worthy(self, change: BillChange, bill: Bill) -> bool:
        if change.change_type == "status_change":
            new_status = (change.new_value or {}).get("status", "")
            return new_status in SIGNIFICANT_STATUSES
        if change.change_type == "text_update":
            # Only alert on text changes for high-confidence bills
            return (bill.confidence_score or 0) >= 0.7
        if change.change_type == "impact_score_change":
            delta = abs(
                (change.new_value or {}).get("composite_score", 0)
                - (change.old_value or {}).get("composite_score", 0)
            )
            return delta >= SCORE_DELTA_THRESHOLD
        return False
