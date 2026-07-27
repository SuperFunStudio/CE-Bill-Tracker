"""Approval status on access_requests (gate Researcher checkout on human review)

Revision ID: 042
Revises: 041
Create Date: 2026-07-26

The Researcher tier is now approval-gated: a visitor submits a written request (email + org +
message) via RequestAccessModal, and the team approves it in /admin before that person can pay.
`_research_checkout` (app/api/billing.py) 403s until an approved research request exists for the
email, so the block holds even against a direct API call. This adds the review state the guard
reads: `status` ('pending' | 'approved' | 'denied') plus an audit trail of who reviewed it and when.
Existing rows default to 'pending' (they predate the gate and were pure lead-capture).
"""
from alembic import op
import sqlalchemy as sa

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "access_requests",
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.add_column("access_requests", sa.Column("reviewed_by", sa.String(255), nullable=True))
    op.add_column(
        "access_requests",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_access_requests_status", "access_requests", ["status"])


def downgrade() -> None:
    op.drop_index("idx_access_requests_status", table_name="access_requests")
    op.drop_column("access_requests", "reviewed_at")
    op.drop_column("access_requests", "reviewed_by")
    op.drop_column("access_requests", "status")
