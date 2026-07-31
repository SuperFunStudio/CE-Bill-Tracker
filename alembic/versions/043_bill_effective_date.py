"""Promote extracted effective_date to a real indexable column on bills

Revision ID: 043
Revises: 042
Create Date: 2026-07-31

The Sonnet extraction already produces a headline effective/compliance date, but it lived only inside
the compliance_details JSONB as a string — unindexable, and awkward to range-filter (a ::date cast can
throw on malformed values). The "search by date" feature needs to answer "what obligations take effect
between X and Y", so promote it to a real DATE column with an index.

Backfill pulls the value straight from compliance_details, but ONLY when it is a well-formed
YYYY-MM-DD (regex-guarded, mirroring app/api/bills.py laws-in-force) — so the column is day-precise by
construction; a year-only extracted value stays NULL (year charts keep using status_date). Going
forward app/extract_job.py writes the column at extraction time. See docs/
SCOPE_FACET_AND_MATERIAL_NAVIGATION.md §9.
"""
from alembic import op
import sqlalchemy as sa

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("effective_date", sa.Date(), nullable=True))
    op.create_index("idx_bills_effective_date", "bills", ["effective_date"])
    # Backfill from the JSONB, accepting only a full ISO date so the column stays day-precise.
    op.execute(
        r"""
        UPDATE bills
        SET effective_date = (compliance_details->>'effective_date')::date
        WHERE compliance_details ? 'effective_date'
          AND compliance_details->>'effective_date' ~ '^\d{4}-\d{2}-\d{2}$'
        """
    )


def downgrade() -> None:
    op.drop_index("idx_bills_effective_date", table_name="bills")
    op.drop_column("bills", "effective_date")
