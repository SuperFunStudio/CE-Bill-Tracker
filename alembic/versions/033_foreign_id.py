"""Generic foreign-source id for multi-country national-law ingestion

Revision ID: 033
Revises: 032
Create Date: 2026-06-28

EUR-Lex got its own `celex_id` column (migration 031/032). Rather than adding a new unique column per
country (jp_id, gb_id, kr_id, …), national-law adapters share one generic `foreign_id`, namespaced by
region+source so ids never collide across jurisdictions (e.g. "JP:egov:424AC0000000057"). This is the
seam for the pluggable multi-country scraper — see app/ingestion/foreign.py + [[eu-integration]].
"""
from alembic import op
import sqlalchemy as sa

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("foreign_id", sa.String(length=120), nullable=True))
    op.create_unique_constraint("uq_bills_foreign_id", "bills", ["foreign_id"])


def downgrade() -> None:
    op.drop_constraint("uq_bills_foreign_id", "bills", type_="unique")
    op.drop_column("bills", "foreign_id")
