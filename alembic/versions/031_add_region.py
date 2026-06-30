"""Add region + celex_id to bills — the lean multi-region seam (EU spike)

Revision ID: 031
Revises: 030
Create Date: 2026-06-27

SignalScout was US-only: every bill's jurisdiction lived in `bills.state` (String(2): "CA",
"OR", or "US" for federal). To add EU coverage from EUR-Lex/CELLAR without the full
region+jurisdiction refactor, we add a lightweight `region` family column (default 'US', so all
existing rows backfill to US) and a `celex_id` for the EU document identifier. EU-wide acts use
region='EU', state='EU' (mirroring the existing 'US' federal sentinel). The broader normalization
across deadlines/entities/subscriptions is deferred — see plan serene-munching-brook.
"""
from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOT NULL with a server_default backfills every existing row to 'US' in one fast metadata
    # operation (Postgres 11+), no table rewrite.
    op.add_column(
        "bills",
        sa.Column("region", sa.String(length=2), nullable=False, server_default="US"),
    )
    op.add_column("bills", sa.Column("celex_id", sa.String(length=40), nullable=True))
    op.create_unique_constraint("uq_bills_celex_id", "bills", ["celex_id"])
    op.create_index("idx_bills_region", "bills", ["region"])


def downgrade() -> None:
    op.drop_index("idx_bills_region", table_name="bills")
    op.drop_constraint("uq_bills_celex_id", "bills", type_="unique")
    op.drop_column("bills", "celex_id")
    op.drop_column("bills", "region")
