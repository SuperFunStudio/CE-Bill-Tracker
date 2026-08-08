"""Add the relevance verdict to litigation_cases (ce_relevant + provenance)

Revision ID: 046
Revises: 045
Create Date: 2026-08-07

Until now a row in litigation_cases meant "CourtListener's search returned this", not "this is a
circular-economy case" — there was no gate between the two, and no column in which to record one.
Production ended up with 34 tracked cases of which one was on topic, and subscribers received
"EPR Litigation Update: United States v. State of Maryland" about a DOJ constitutional suit.

Four columns, mirroring how bills carry their classification:

  ce_relevant         NULL = never screened (every pre-046 row), true/false = the gate's verdict.
                      Deliberately nullable so the backfill is visible as work-to-do rather than
                      defaulting the existing junk into either bucket.
  relevance_reason    Why — in one sentence, quoting the term or law that decided it.
  relevance_source    'keyword' | 'no_signal' | 'llm' | 'llm_unavailable' | 'manual'.
  relevance_checked_at When, so a re-screen after a gate change is identifiable.

Screening is a *display and alert* gate, not a delete: an excluded case keeps its row and its events
so a wrong call can be reversed by flipping one boolean. See app/ingestion/litigation_relevance.py
for the gate and scripts/prune_litigation_cases.py for the backfill over existing rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("litigation_cases", sa.Column("ce_relevant", sa.Boolean(), nullable=True))
    op.add_column("litigation_cases", sa.Column("relevance_reason", sa.Text(), nullable=True))
    op.add_column(
        "litigation_cases", sa.Column("relevance_source", sa.String(length=24), nullable=True)
    )
    op.add_column(
        "litigation_cases",
        sa.Column("relevance_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    # The public list query filters on this, and the unscreened/excluded rows are the minority we
    # ever query by tag — but the index is unconditional here because `ce_relevant IS NOT TRUE`
    # (the exclusion predicate) can't use a partial index defined on the true side.
    op.create_index(
        "idx_litigation_cases_ce_relevant", "litigation_cases", ["ce_relevant"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_litigation_cases_ce_relevant", table_name="litigation_cases")
    op.drop_column("litigation_cases", "relevance_checked_at")
    op.drop_column("litigation_cases", "relevance_source")
    op.drop_column("litigation_cases", "relevance_reason")
    op.drop_column("litigation_cases", "ce_relevant")
