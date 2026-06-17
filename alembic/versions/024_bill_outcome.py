"""Add bill_outcome — the real-world "what did this law actually do" layer

Revision ID: 024
Revises: 023
Create Date: 2026-06-17

Every other table describes what a law REQUIRES; bill_outcome captures what an enacted law
has been documented to PRODUCE (positive / negative / mixed), always anchored to a citation.
One-to-many on bills via a soft FK (SET NULL) plus denormalized law identity, so an outcome
can describe a famous law we don't yet track as a row. Curated + slug-keyed for idempotent
seeding (scripts/seed_bill_outcomes.py). Powers the Insights "Real-World Impact" spotlight.
See compliance-action-vision + incentives-instrument.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bill_outcome",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
        sa.Column("bill_id", sa.Integer(),
                  sa.ForeignKey("bills.id", ondelete="SET NULL"), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("bill_number", sa.String(length=50), nullable=True),
        sa.Column("law_title", sa.Text(), nullable=True),
        sa.Column("instrument_type", sa.String(length=50), nullable=True),
        sa.Column("material_categories", postgresql.JSONB(), nullable=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("metric_label", sa.Text(), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("metric_unit", sa.String(length=40), nullable=True),
        sa.Column("metric_display", sa.String(length=120), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("attribution", sa.String(length=20), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_bill_outcome_bill_id", "bill_outcome", ["bill_id"])
    op.create_index("idx_bill_outcome_direction", "bill_outcome", ["direction"])


def downgrade() -> None:
    op.drop_index("idx_bill_outcome_direction", table_name="bill_outcome")
    op.drop_index("idx_bill_outcome_bill_id", table_name="bill_outcome")
    op.drop_table("bill_outcome")
