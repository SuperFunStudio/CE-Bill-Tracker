"""Atlas Circular jurisdiction tree + bills.jurisdiction_id

Revision ID: 036
Revises: 035
Create Date: 2026-07-11

Schema only — the tree seed + the bills.jurisdiction_id backfill run in the idempotent
scripts/backfill_jurisdictions.py (keeps migrations frozen; seed reads the live app/geo map). See
docs/ATLAS_A0_A1_SPEC.md. `path` is dotted text (no ltree extension needed — the tree is ~80 rows,
so subtree resolution is a cheap text-prefix match); `aliases` is a lowercased text[] with a GIN
index, the thing that lets "France" resolve to the FR node.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jurisdictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("jurisdictions.id"), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("bill_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_unique_constraint("uq_jurisdictions_code", "jurisdictions", ["code"])
    op.create_index("idx_jurisdictions_path", "jurisdictions", ["path"])
    op.create_index("idx_jurisdictions_aliases", "jurisdictions", ["aliases"], postgresql_using="gin")

    op.add_column("bills", sa.Column("jurisdiction_id", sa.Integer(),
                                     sa.ForeignKey("jurisdictions.id"), nullable=True))
    op.create_index("idx_bills_jurisdiction", "bills", ["jurisdiction_id"])


def downgrade() -> None:
    op.drop_index("idx_bills_jurisdiction", table_name="bills")
    op.drop_column("bills", "jurisdiction_id")
    op.drop_index("idx_jurisdictions_aliases", table_name="jurisdictions")
    op.drop_index("idx_jurisdictions_path", table_name="jurisdictions")
    op.drop_constraint("uq_jurisdictions_code", "jurisdictions", type_="unique")
    op.drop_table("jurisdictions")
