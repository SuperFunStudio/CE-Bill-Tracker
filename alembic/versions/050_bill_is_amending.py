"""Add bills.is_amending — marks a row as an act that edits another law rather than standing alone

Revision ID: 050
Revises: 049
Create Date: 2026-08-14

A cumulative "circular-economy laws on the books" count treated every enacted row as a distinct law.
114 of the 1,179 enacted rows are amending instruments — "The End-of-Life Vehicles (Producer
Responsibility) (Amendment) Regulations 2010", "COMMISSION DIRECTIVE (EU) 2015/1127 amending Annex II
to Directive 2008/98/EC" — which edit a law the corpus usually also holds. Counting both the principal
act and its patches overstates the size of the body of law, and overstates it UNEVENLY: the UK (50) and
EU (46) legislate heavily by amendment, so they were inflated against jurisdictions that re-enact
instead. That made the cross-region comparison the Insights momentum chart exists to support unsound.

Nullable BOOLEAN, three-valued on purpose:
  NULL  = not yet assessed (every row starts here; the backfill has not seen it)
  false = assessed, stands on its own
  true  = assessed, amends another instrument
NULL vs false is the distinction that lets a consumer tell "we checked and it's a principal act" from
"we never looked", so a half-finished backfill can never masquerade as a clean corpus.

The classifier is app/ingestion/act_role.py (title heuristic, deliberately conservative, US exempt
because US law is enacted BY amending a code and the title carries no signal). Population is
scripts/backfill_act_role.py, dry-run by default. Column only here; no data change.

Partial index on the true rows: consumers filter `is_amending IS NOT TRUE` to count distinct laws, and
the flagged minority is the small side.
"""
from alembic import op
import sqlalchemy as sa

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("is_amending", sa.Boolean(), nullable=True))
    op.create_index(
        "idx_bills_is_amending",
        "bills",
        ["is_amending"],
        unique=False,
        postgresql_where=sa.text("is_amending IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("idx_bills_is_amending", table_name="bills")
    op.drop_column("bills", "is_amending")
