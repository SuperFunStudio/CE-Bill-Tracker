"""Add instrument_types to alert_subscriptions

Revision ID: 007
Revises: 006
Create Date: 2026-06-07

The public "get free updates" sign-up on the About page lets a reader follow specific *policy
topics* (EPR, right-to-repair, deposit-return, recycled-content, labeling) in specific
jurisdictions. Jurisdictions already map onto alert_subscriptions.states; topics map onto the
classifier's instrument_type enum, which had no home on the subscription. instrument_types stores
that selection (["ALL"] = every topic), mirroring the existing states / material_categories shape.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_subscriptions",
        sa.Column(
            "instrument_types",
            JSONB,
            nullable=False,
            server_default=sa.text("'[\"ALL\"]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("alert_subscriptions", "instrument_types")
