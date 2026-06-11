"""Add organization to alert_subscriptions

Revision ID: 008
Revises: 007
Create Date: 2026-06-07

The public "get free updates" sign-up lets a reader optionally tell us what organization they're
with, so we can understand who's following which topics. Nullable free text — no behavioural effect
on alert matching, purely informational.
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_subscriptions",
        sa.Column("organization", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_subscriptions", "organization")
