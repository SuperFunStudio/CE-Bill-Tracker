"""Purge all LegiScan-sourced bills (free tier serves WV session 1 data for all states)

Revision ID: 004
Revises: 003
Create Date: 2026-05-04

All bills ingested via the LegiScan free tier are West Virginia session 1 bills
stored under wrong state codes. The free tier getMasterList returns WV bill IDs
1–11534 regardless of which state is queried. This migration removes all
LegiScan-sourced rows and leaves seed data and Open States rows intact.
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Delete ImpactScore rows referencing LegiScan bills first (FK constraint)
    op.execute("""
        DELETE FROM impact_score
        WHERE bill_id IN (
            SELECT id FROM bills WHERE legiscan_bill_id IS NOT NULL
        )
    """)

    # Delete BillChange rows referencing LegiScan bills
    op.execute("""
        DELETE FROM bill_changes
        WHERE bill_id IN (
            SELECT id FROM bills WHERE legiscan_bill_id IS NOT NULL
        )
    """)

    # Delete ComplianceDeadline rows referencing LegiScan bills
    op.execute("""
        DELETE FROM compliance_deadlines
        WHERE bill_id IN (
            SELECT id FROM bills WHERE legiscan_bill_id IS NOT NULL
        )
    """)

    # Delete ExposureBrief rows referencing LegiScan bills
    op.execute("""
        DELETE FROM exposure_brief
        WHERE bill_id IN (
            SELECT id FROM bills WHERE legiscan_bill_id IS NOT NULL
        )
    """)

    # Delete litigation_cases related_law_id refs (nullable FK, null them out)
    op.execute("""
        UPDATE litigation_cases
        SET related_law_id = NULL
        WHERE related_law_id IN (
            SELECT id FROM bills WHERE legiscan_bill_id IS NOT NULL
        )
    """)

    # Finally delete the LegiScan bills themselves
    op.execute("""
        DELETE FROM bills WHERE legiscan_bill_id IS NOT NULL
    """)


def downgrade() -> None:
    # Data deletion is not reversible
    pass
