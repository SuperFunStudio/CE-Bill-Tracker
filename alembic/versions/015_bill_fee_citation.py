"""Add bill_fee_citation — cited provenance for the fee / threshold facts behind cost estimates

Revision ID: 015
Revises: 014
Create Date: 2026-06-12

Each row pins one numeric fact (fact_type: fee_per_ton | fee_per_unit_usd | registration_fee_usd |
producer_revenue_threshold | producer_tonnage_threshold | eco_modulation) to a basis:

  enacted_text       — value stated in the bill; source_excerpt is the VERBATIM clause, validated as a
                       substring of the bill's compliance_details (same chain-of-custody as
                       bill_design_signal — a fabricated quote is dropped, never stored).
  published_schedule — value set by an agency / PRO fee schedule (CalRecycle, PaintCare, MRC, …) rather
                       than the statute; source_url points at that schedule. This is the honest home for
                       EPR fees, which are usually fixed by post-enactment rulemaking.
  benchmark          — no published value; an industry/category estimate. NOT grounded.

A fee estimate is "grounded" when its driving fact has an enacted_text or published_schedule citation,
which the UI surfaces so a published fee never reads as a guess. The unique (bill_id, fact_type, basis)
keeps re-runs idempotent. ON DELETE CASCADE so citations disappear with their bill. `reviewed` mirrors
bills.reviewed (auto-extracted until a human checks it). See app/synthesis/fee_citations.py and
scripts/extract_fee_citations.py.
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bill_fee_citation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "bill_id", sa.Integer(),
            sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("fact_type", sa.String(length=40), nullable=False),
        sa.Column("basis", sa.String(length=20), nullable=False),
        sa.Column("extracted_value", sa.Float(), nullable=True),
        sa.Column("value_unit", sa.String(length=40), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("extractor_model", sa.String(length=50), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "bill_id", "fact_type", "basis", name="uq_fee_citation_bill_fact_basis"
        ),
    )
    op.create_index("idx_fee_citation_bill_id", "bill_fee_citation", ["bill_id"])
    op.create_index("idx_fee_citation_fact_type", "bill_fee_citation", ["fact_type"])


def downgrade() -> None:
    op.drop_index("idx_fee_citation_fact_type", table_name="bill_fee_citation")
    op.drop_index("idx_fee_citation_bill_id", table_name="bill_fee_citation")
    op.drop_table("bill_fee_citation")
