"""Add compliance_entity + compliance_pathway — the "now what do I do" action layer

Revision ID: 019
Revises: 018
Create Date: 2026-06-15

compliance_entity is the curated directory of bodies a producer interacts with to comply:
PROs (Circular Action Alliance, Call2Recycle, PaintCare, Mattress Recycling Council, …) and
government agencies (CalRecycle, WA Ecology). compliance_pathway is the per-law bridge: one
primary next-action per enacted law (join_pro / file_individual_plan / register_with_state /
pay_into_program / monitor / none), derived from the management_model classification
(bills.compliance_details.management). See compliance-action-vision + management-model-dimension.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compliance_entity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False, unique=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("registration_url", sa.Text(), nullable=True),
        sa.Column("jurisdiction_scope", sa.String(length=20), nullable=True),
        sa.Column("home_state", sa.String(length=2), nullable=True),
        sa.Column("materials", postgresql.JSONB(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_compliance_entity_type", "compliance_entity", ["entity_type"])
    op.create_index("idx_compliance_entity_materials", "compliance_entity",
                    ["materials"], postgresql_using="gin")

    op.create_table(
        "compliance_pathway",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bill_id", sa.Integer(),
                  sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", sa.Integer(),
                  sa.ForeignKey("compliance_entity.id", ondelete="SET NULL"), nullable=True),
        sa.Column("management_model", sa.String(length=30), nullable=True),
        sa.Column("action_type", sa.String(length=30), nullable=True),
        sa.Column("action_summary", sa.Text(), nullable=True),
        sa.Column("registration_url", sa.Text(), nullable=True),
        sa.Column("next_deadline_date", sa.Date(), nullable=True),
        sa.Column("has_fee", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("basis", sa.String(length=30), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("bill_id", name="uq_pathway_bill"),
    )
    op.create_index("idx_pathway_bill_id", "compliance_pathway", ["bill_id"])
    op.create_index("idx_pathway_entity_id", "compliance_pathway", ["entity_id"])
    op.create_index("idx_pathway_management_model", "compliance_pathway", ["management_model"])


def downgrade() -> None:
    op.drop_index("idx_pathway_management_model", table_name="compliance_pathway")
    op.drop_index("idx_pathway_entity_id", table_name="compliance_pathway")
    op.drop_index("idx_pathway_bill_id", table_name="compliance_pathway")
    op.drop_table("compliance_pathway")
    op.drop_index("idx_compliance_entity_materials", table_name="compliance_entity")
    op.drop_index("idx_compliance_entity_type", table_name="compliance_entity")
    op.drop_table("compliance_entity")
