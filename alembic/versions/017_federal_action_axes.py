"""Add federal_action friction_type / instrument_type — the two classifier axes we were dropping

Revision ID: 017
Revises: 016
Create Date: 2026-06-14

FederalClassifier already computes a friction_type (how a federal action pressures state EPR
programs: preemption | federal_mandate | compliance_burden | comment_opportunity | funding |
study | none) and now also an instrument_type drawn from the SAME vocabulary the state bill
explorer uses (epr | recycled_content | right_to_repair | deposit_return | labeling |
chemical_restriction | preemption | budget | other). Both were thrown away at persistence time
(coordinator only stored epr_relevant / preemption_risk / ai_summary / material_categories).
These two columns give them a home so the Federal Actions page can filter on friction and on the
same instrument facet as bills. material_categories already exists on the table.

Nullable, no backfill here — values are populated by re-running the federal classify cycle.
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("federal_actions", sa.Column("friction_type", sa.String(length=30), nullable=True))
    op.add_column("federal_actions", sa.Column("instrument_type", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("federal_actions", "instrument_type")
    op.drop_column("federal_actions", "friction_type")
