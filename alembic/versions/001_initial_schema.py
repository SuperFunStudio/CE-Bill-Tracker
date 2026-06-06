"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'bills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('legiscan_bill_id', sa.Integer(), nullable=True),
        sa.Column('openstates_id', sa.String(100), nullable=True),
        sa.Column('state', sa.String(2), nullable=False),
        sa.Column('bill_number', sa.String(50), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('status_date', sa.Date(), nullable=True),
        sa.Column('last_action_date', sa.Date(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('change_hash', sa.String(64), nullable=True),
        sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('epr_relevant', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('material_categories', JSONB(), nullable=True),
        sa.Column('instrument_type', sa.String(50), nullable=True),
        sa.Column('urgency', sa.String(10), nullable=True),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('compliance_details', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('legiscan_bill_id'),
        sa.UniqueConstraint('openstates_id'),
    )
    op.create_index('idx_bills_state_status', 'bills', ['state', 'status'])
    op.create_index('idx_bills_last_action', 'bills', ['last_action_date'])
    op.create_index('idx_bills_relevant', 'bills', ['epr_relevant'])
    op.create_index('idx_bills_material_categories', 'bills', ['material_categories'],
                    postgresql_using='gin')

    op.create_table(
        'bill_changes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('change_type', sa.String(50), nullable=False),
        sa.Column('old_value', JSONB(), nullable=True),
        sa.Column('new_value', JSONB(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('alert_sent', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_bill_changes_bill_id', 'bill_changes', ['bill_id'])

    op.create_table(
        'alert_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('slack_webhook', sa.Text(), nullable=True),
        sa.Column('states', JSONB(), nullable=True),
        sa.Column('material_categories', JSONB(), nullable=True),
        sa.Column('min_confidence', sa.Float(), nullable=False, server_default='0.7'),
        sa.Column('alert_on', JSONB(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'federal_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('federal_register_document_number', sa.String(100), nullable=True),
        sa.Column('agency', sa.String(200), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('action_type', sa.String(50), nullable=True),
        sa.Column('material_categories', JSONB(), nullable=True),
        sa.Column('published_date', sa.Date(), nullable=True),
        sa.Column('comment_deadline', sa.Date(), nullable=True),
        sa.Column('effective_date', sa.Date(), nullable=True),
        sa.Column('document_url', sa.Text(), nullable=True),
        sa.Column('epr_relevant', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('preemption_risk', sa.String(10), nullable=True),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('raw_data', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('federal_register_document_number'),
    )
    op.create_index('idx_federal_published', 'federal_actions', ['published_date'])

    op.create_table(
        'compliance_deadlines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=True),
        sa.Column('federal_action_id', sa.Integer(), nullable=True),
        sa.Column('state', sa.String(2), nullable=False),
        sa.Column('deadline_type', sa.String(50), nullable=False),
        sa.Column('deadline_date', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('who_affected', sa.Text(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('reminder_sent', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id']),
        sa.ForeignKeyConstraint(['federal_action_id'], ['federal_actions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_deadlines_date', 'compliance_deadlines', ['deadline_date'])
    op.create_index('idx_deadlines_state', 'compliance_deadlines', ['state'])


def downgrade() -> None:
    op.drop_table('compliance_deadlines')
    op.drop_table('federal_actions')
    op.drop_table('alert_subscriptions')
    op.drop_table('bill_changes')
    op.drop_table('bills')
