"""CourtListener judicial monitoring schema

Revision ID: 003
Revises: 002
Create Date: 2026-03-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add litigation_risk column to bills
    op.add_column('bills', sa.Column('litigation_risk', sa.Text(), nullable=True,
                                     server_default='unknown'))

    # litigation_cases — one row per federal court case
    op.create_table(
        'litigation_cases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('courtlistener_id', sa.Integer(), nullable=False),
        sa.Column('case_name', sa.Text(), nullable=False),
        sa.Column('docket_number', sa.Text(), nullable=True),
        sa.Column('court_id', sa.String(50), nullable=False),
        sa.Column('court_name', sa.Text(), nullable=True),
        sa.Column('date_filed', sa.Date(), nullable=True),
        sa.Column('date_terminated', sa.Date(), nullable=True),
        sa.Column('assigned_judge', sa.Text(), nullable=True),
        sa.Column('case_status', sa.String(50), nullable=True, server_default='active'),
        sa.Column('challenge_type', sa.String(50), nullable=True),
        sa.Column('plaintiff_type', sa.String(50), nullable=True),
        sa.Column('key_plaintiffs', JSONB(), nullable=True),
        sa.Column('related_law_id', sa.Integer(), nullable=True),
        sa.Column('related_state', sa.String(2), nullable=True),
        sa.Column('related_statute', sa.Text(), nullable=True),
        sa.Column('preemption_risk', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('cl_url', sa.Text(), nullable=True),
        sa.Column('last_activity_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('courtlistener_id'),
        sa.ForeignKeyConstraint(['related_law_id'], ['bills.id'], ondelete='SET NULL'),
    )
    op.create_index('idx_litigation_cases_status', 'litigation_cases', ['case_status'])
    op.create_index('idx_litigation_cases_state', 'litigation_cases', ['related_state'])
    op.create_index('idx_litigation_cases_law_id', 'litigation_cases', ['related_law_id'])

    # litigation_events — one row per docket entry/filing
    op.create_table(
        'litigation_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('courtlistener_entry_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('date_filed', sa.Date(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('significance', sa.String(20), nullable=True, server_default='low'),
        sa.Column('document_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('courtlistener_entry_id'),
        sa.ForeignKeyConstraint(['case_id'], ['litigation_cases.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_litigation_events_case_id', 'litigation_events', ['case_id'])
    op.create_index('idx_litigation_events_significance', 'litigation_events', ['significance'])

    # cl_alert_subscriptions — tracks active CL search and docket alerts
    op.create_table(
        'cl_alert_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('cl_alert_id', sa.Integer(), nullable=True),
        sa.Column('query_string', sa.Text(), nullable=True),
        sa.Column('docket_id', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_cl_subs_active', 'cl_alert_subscriptions', ['active'])


def downgrade() -> None:
    op.drop_table('cl_alert_subscriptions')
    op.drop_table('litigation_events')
    op.drop_table('litigation_cases')
    op.drop_column('bills', 'litigation_risk')
