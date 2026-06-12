"""Add bill_product_coverage — per-bill covered-product detail for the product-coverage grid

Revision ID: 012
Revises: 011
Create Date: 2026-06-12

Each row is one (product, obligation) a bill scopes: a product_slug from the controlled taxonomy
in app/synthesis/product_taxonomy.py, a relationship_type (stewarded | repairable | disposal_banned
| deposit_return — Phase 0 found electronics bills split ~half EPR / half right-to-repair), a status
(covered | exempt | conditional), and the VERBATIM source_excerpt it was extracted from. Products
absent from a bill's rows are "not mentioned"; only covered/exempt/conditional products get a row.

`defined_by_reference` flags products covered only by pointing at an existing statute. `reviewed`
mirrors bills.reviewed (auto-extracted until a human checks it). ON DELETE CASCADE so coverage rows
disappear with their bill. The unique (bill_id, product_slug, relationship_type) keeps re-runs
idempotent — see scripts/build_product_coverage.py (Phase 2).
"""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bill_product_coverage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "bill_id", sa.Integer(),
            sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("product_slug", sa.String(length=60), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("relationship_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "defined_by_reference", sa.Boolean(), nullable=False, server_default="false",
        ),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("threshold_unit", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("extractor_model", sa.String(length=50), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "bill_id", "product_slug", "relationship_type",
            name="uq_coverage_bill_product_rel",
        ),
    )
    op.create_index("idx_product_coverage_bill_id", "bill_product_coverage", ["bill_id"])
    op.create_index(
        "idx_product_coverage_category_slug", "bill_product_coverage", ["category", "product_slug"]
    )
    op.create_index("idx_product_coverage_slug", "bill_product_coverage", ["product_slug"])


def downgrade() -> None:
    op.drop_index("idx_product_coverage_slug", table_name="bill_product_coverage")
    op.drop_index("idx_product_coverage_category_slug", table_name="bill_product_coverage")
    op.drop_index("idx_product_coverage_bill_id", table_name="bill_product_coverage")
    op.drop_table("bill_product_coverage")
