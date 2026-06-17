"""Add `founding` flag to entitlements — marks founding-member seats for the badge

Revision ID: 020
Revises: 019
Create Date: 2026-06-16

Stamped True at checkout when the founding launch coupon was applied (app/api/billing.py). Drives the
"Founding Member" badge on the account page. Defaulted false, no backfill — existing rows keep
founding = false.
"""
from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entitlements",
        sa.Column("founding", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("entitlements", "founding")
