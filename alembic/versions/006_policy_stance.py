"""Add policy_stance + stance_source to bills

Revision ID: 006
Revises: 005
Create Date: 2026-06-06

A bill tagged with a policy instrument (right_to_repair, epr, deposit_return, ...) can either
*advance* that policy (establish/strengthen/expand it, or repeal a preemption of it) or
*weaken* it (exempt/narrow/repeal/preempt it). The instrument_type alone can't tell the two
apart, so an enacted Right-to-Repair *exemption* (e.g. CO HB-25-1330, "Exempting Quantum
Computing Equipment Right to Repair") looked identical to an enacted Right-to-Repair *grant*.

policy_stance captures that direction; stance_source records whether it came from the Haiku
classifier ("ai") or the cheap text heuristic ("heuristic"), so a provisional heuristic tag is
distinguishable from a real classification and can be safely overwritten by a later AI pass.
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("policy_stance", sa.String(20), nullable=True))
    op.add_column("bills", sa.Column("stance_source", sa.String(20), nullable=True))
    op.create_index("idx_bills_policy_stance", "bills", ["policy_stance"])


def downgrade() -> None:
    op.drop_index("idx_bills_policy_stance", table_name="bills")
    op.drop_column("bills", "stance_source")
    op.drop_column("bills", "policy_stance")
