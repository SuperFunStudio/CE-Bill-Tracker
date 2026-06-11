"""Add reviewed + new_bill_alert_sent flags to bills

Revision ID: 010
Revises: 009
Create Date: 2026-06-10

- `reviewed`: classification transparency. Every relevance call is auto-classified; this flips true
  once a human spot-checks it. Surfaced as the "auto-classified · reviewed" marker on each bill.
- `new_bill_alert_sent`: idempotency for the event-triggered "new bill" alert, so a newly-tracked
  relevant bill is emailed to matching subscribers at most once.

Both default false (server_default so the backfill of existing rows is non-null).
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bills",
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "bills",
        sa.Column(
            "new_bill_alert_sent", sa.Boolean(), nullable=False, server_default="false"
        ),
    )


def downgrade() -> None:
    op.drop_column("bills", "new_bill_alert_sent")
    op.drop_column("bills", "reviewed")
