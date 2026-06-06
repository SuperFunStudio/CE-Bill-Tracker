"""company impact scoring schema

Revision ID: 002
Revises: 001
Create Date: 2026-03-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pg_trgm for fuzzy name matching in entity resolution
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 1. company — no FKs into new tables
    op.create_table(
        'company',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('duns_number', sa.String(9), nullable=True, unique=True),
        sa.Column('cik', sa.String(10), nullable=True, unique=True),
        sa.Column('epa_registry_id', sa.String(50), nullable=True, unique=True),
        sa.Column('hq_state', sa.String(2), nullable=True),
        sa.Column('naics_codes', JSONB, nullable=True),
        sa.Column('operating_states', JSONB, nullable=True),
        sa.Column('total_annual_volume_tonnes', sa.Float(), nullable=True),
        sa.Column('volume_source', sa.String(200), nullable=True),
        sa.Column('volume_confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_company_name', 'company', ['name'])
    op.create_index('idx_company_hq_state', 'company', ['hq_state'])

    # 2. company_alias — FK to company
    op.create_table(
        'company_alias',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('company.id'), nullable=False),
        sa.Column('alias_name', sa.String(500), nullable=False),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('match_confidence', sa.Float(), nullable=True),
        sa.Column('verified', sa.Boolean(), server_default='false'),
        sa.Column('verified_by', sa.String(200), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('alias_name', 'source', name='uq_alias_source'),
    )
    op.create_index('idx_alias_company_id', 'company_alias', ['company_id'])
    # GIN index for pg_trgm fuzzy matching
    op.create_index(
        'idx_alias_name_trgm',
        'company_alias',
        ['alias_name'],
        postgresql_using='gin',
        postgresql_ops={'alias_name': 'gin_trgm_ops'},
    )

    # 3. company_material — FK to company
    op.create_table(
        'company_material',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('company.id'), nullable=False),
        sa.Column('material_category', sa.String(100), nullable=False),
        sa.Column('annual_volume_tonnes', sa.Float(), nullable=True),
        sa.Column('volume_confidence', sa.Float(), nullable=True),
        sa.Column('source', sa.String(200), nullable=True),
    )
    op.create_index('idx_company_material_company_id', 'company_material', ['company_id'])

    # 4. company_state_presence — FK to company
    op.create_table(
        'company_state_presence',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('company.id'), nullable=False),
        sa.Column('state', sa.String(2), nullable=False),
        sa.Column('presence_type', sa.String(50), nullable=False),
        sa.Column('is_primary', sa.Boolean(), server_default='false'),
    )
    op.create_index('idx_presence_company_state', 'company_state_presence', ['company_id', 'state'])

    # 5. impact_score — FKs to company and bills
    op.create_table(
        'impact_score',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('company.id'), nullable=False),
        sa.Column('bill_id', sa.Integer(), sa.ForeignKey('bills.id'), nullable=False),
        sa.Column('composite_score', sa.Float(), nullable=False),
        sa.Column('material_score', sa.Float(), nullable=True),
        sa.Column('geographic_score', sa.Float(), nullable=True),
        sa.Column('severity_score', sa.Float(), nullable=True),
        sa.Column('estimated_annual_cost', sa.Float(), nullable=True),
        sa.Column('cost_confidence', sa.Float(), nullable=True),
        sa.Column('volume_confidence', sa.Float(), nullable=True),
        sa.Column('score_breakdown', JSONB, nullable=True),
        sa.Column('calculated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_impact_company_bill', 'impact_score', ['company_id', 'bill_id'])
    op.create_index('idx_impact_composite', 'impact_score', ['composite_score'])

    # 6. entity_match_queue — FK to company (nullable)
    op.create_table(
        'entity_match_queue',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('candidate_name', sa.String(500), nullable=False),
        sa.Column('source', sa.String(200), nullable=True),
        sa.Column('suggested_company_id', UUID(as_uuid=True), sa.ForeignKey('company.id'), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('resolved', sa.Boolean(), server_default='false'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_emq_resolved', 'entity_match_queue', ['resolved'])

    # 7. exposure_brief — FKs to company and bills
    op.create_table(
        'exposure_brief',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('company.id'), nullable=False),
        sa.Column('bill_id', sa.Integer(), sa.ForeignKey('bills.id'), nullable=False),
        sa.Column('brief_json', JSONB, nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('ttl_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('company_id', 'bill_id', name='uq_exposure_brief_company_bill'),
    )
    op.create_index('idx_exposure_brief_ttl', 'exposure_brief', ['ttl_expires_at'])


def downgrade() -> None:
    # Drop in reverse FK dependency order
    op.drop_table('exposure_brief')
    op.drop_table('entity_match_queue')
    op.drop_table('impact_score')
    op.drop_table('company_state_presence')
    op.drop_table('company_material')
    op.drop_table('company_alias')
    op.drop_table('company')
    # Do NOT drop pg_trgm — other schemas may use it
