"""Add remediation columns to bill_outcome — the "this law backfired, here's what fixed it" arc

Revision ID: 030
Revises: 029
Create Date: 2026-06-27

Negative/mixed outcomes (a ban that raised plastic tonnage, a deposit that decayed) sometimes get
fixed by a later amendment or follow-on law. That negative->remedied arc is high-value, but only
relevant for the handful of outcomes with direction in ('negative','mixed') — the bad-outcome flag
IS the trigger, so detection is bounded to a tiny set, not a full-corpus scan (scripts/recheck_
remediation.py re-checks just those rows). remediated_by_bill_id is a soft link (clickable when we
track the fixing law); remediation_note carries the human-readable arc even when we don't.
"""
from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bill_outcome", sa.Column("remediation_note", sa.Text(), nullable=True))
    op.add_column(
        "bill_outcome",
        sa.Column(
            "remediated_by_bill_id",
            sa.Integer(),
            sa.ForeignKey("bills.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Denormalized identity of the fixing law, present even when it isn't a tracked bills row.
    op.add_column("bill_outcome", sa.Column("remediation_bill_number", sa.String(length=50), nullable=True))
    # When the remediation was last researched — drives the recurring re-check (NULL = never checked).
    op.add_column(
        "bill_outcome", sa.Column("remediation_checked_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("bill_outcome", "remediation_checked_at")
    op.drop_column("bill_outcome", "remediation_bill_number")
    op.drop_column("bill_outcome", "remediated_by_bill_id")
    op.drop_column("bill_outcome", "remediation_note")
