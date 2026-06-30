"""Multi-value instrument_types (a law is often several instruments at once)

Revision ID: 034
Revises: 033
Create Date: 2026-06-28

`instrument_type` (single String) forced one instrument per law, but a measure is frequently several
at once (e.g. the PPWR is EPR + recycled_content + labeling + reuse). This adds a multi-value
`instrument_types` JSONB alongside it — `instrument_type` stays as the representative "primary" (so
insights group-by and the single-select dropdown keep working), while `instrument_types` carries the
full set for filtering/comparison. Backfills the array from the existing primary. GIN index for
containment filters.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("instrument_types", postgresql.JSONB(), nullable=True))
    op.execute(
        "UPDATE bills SET instrument_types = jsonb_build_array(instrument_type) "
        "WHERE instrument_type IS NOT NULL"
    )
    op.create_index(
        "idx_bills_instrument_types", "bills", ["instrument_types"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("idx_bills_instrument_types", table_name="bills")
    op.drop_column("bills", "instrument_types")
