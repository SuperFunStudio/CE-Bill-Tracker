"""Classification audit log + needs_review flag

Reclassify (app/reclassify.py) overwrites ce_relevant / confidence_score / instrument_type in place
and only re-examines bills that are currently in scope, so a run that judges on thin input (e.g. a
bill with no stored text and an empty description) can only DROP bills — and silently, with no record
of what fell out or why. This adds:

  * `classification_changes` — an audit log mirroring bill_changes, one row per bill whose relevance
    or instrument changed on a run, holding the full old/new classification snapshot + a run_id tag,
    so a run is diffable and a bad run is recoverable.
  * `bills.needs_review` — set when the classifier would have dropped a bill but a near-certain
    keyword signal in the title rescued it into scope; marks rows for a human spot-check.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bills",
        sa.Column(
            "needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_index("idx_bills_needs_review", "bills", ["needs_review"])

    op.create_table(
        "classification_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "bill_id",
            sa.Integer(),
            sa.ForeignKey("bills.id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=120), nullable=True),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_classification_changes_bill_id", "classification_changes", ["bill_id"]
    )
    op.create_index(
        "idx_classification_changes_run_id", "classification_changes", ["run_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_classification_changes_run_id", table_name="classification_changes")
    op.drop_index("idx_classification_changes_bill_id", table_name="classification_changes")
    op.drop_table("classification_changes")
    op.drop_index("idx_bills_needs_review", table_name="bills")
    op.drop_column("bills", "needs_review")
