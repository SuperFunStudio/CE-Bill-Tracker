"""Add bill_design_signal — cited design-lever atoms for the Design-for-EPR synthesis

Revision ID: 011
Revises: 010
Create Date: 2026-06-11

Each row is one design implication derived from a bill's compliance_details (see
app/synthesis/design_levers.py): a lever + obligation direction + the VERBATIM source_excerpt
it was extracted from. Principles are aggregated from these rows, so the source_excerpt is the
chain of custody — a principle can never cite a clause not present on a real bill. ON DELETE
CASCADE so signals disappear with their bill.

`reviewed` mirrors the bills.reviewed transparency flag (auto-extracted until a human checks it).
Cost/fee exposure is intentionally NOT stored here; eco-modulation rates arrive separately from
the Circular Action Alliance schedules and join via a future eco_mod_rate table.
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bill_design_signal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "bill_id", sa.Integer(),
            sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("lever", sa.String(length=40), nullable=False),
        sa.Column("obligation_type", sa.String(length=20), nullable=False),
        sa.Column("design_action", sa.Text(), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("threshold_unit", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("extractor_model", sa.String(length=50), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("idx_design_signal_bill_id", "bill_design_signal", ["bill_id"])
    op.create_index("idx_design_signal_lever", "bill_design_signal", ["lever"])
    op.create_index(
        "idx_design_signal_lever_obligation",
        "bill_design_signal", ["lever", "obligation_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_design_signal_lever_obligation", table_name="bill_design_signal")
    op.drop_index("idx_design_signal_lever", table_name="bill_design_signal")
    op.drop_index("idx_design_signal_bill_id", table_name="bill_design_signal")
    op.drop_table("bill_design_signal")
