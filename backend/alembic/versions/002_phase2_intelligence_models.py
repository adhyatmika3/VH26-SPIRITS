"""Create incidents and canonical_alerts tables

Revision ID: 002_phase2_intelligence_models
Revises: 001_initial_raw_alerts
Create Date: 2026-09-04 11:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_phase2_intelligence_models'
down_revision: Union[str, None] = '001_initial_raw_alerts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create incidents table
    op.create_table(
        'incidents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('incident_number', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('service', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='OPEN'),
        sa.Column('priority', sa.String(length=50), nullable=False, server_default='MEDIUM'),
        sa.Column('alert_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('unique_alerts_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_storm', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_incidents_id'), 'incidents', ['id'], unique=False)
    op.create_index(op.f('ix_incidents_incident_number'), 'incidents', ['incident_number'], unique=True)
    op.create_index(op.f('ix_incidents_service'), 'incidents', ['service'], unique=False)
    op.create_index(op.f('ix_incidents_status'), 'incidents', ['status'], unique=False)
    op.create_index(op.f('ix_incidents_priority'), 'incidents', ['priority'], unique=False)
    op.create_index(op.f('ix_incidents_last_seen'), 'incidents', ['last_seen'], unique=False)
    op.create_index(op.f('ix_incidents_is_storm'), 'incidents', ['is_storm'], unique=False)

    # 2. Create canonical_alerts table
    op.create_table(
        'canonical_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('raw_alert_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('incident_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('alert_name', sa.String(length=255), nullable=False),
        sa.Column('service', sa.String(length=255), nullable=False),
        sa.Column('resource', sa.String(length=255), nullable=True),
        sa.Column('severity', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('message', sa.String(length=1000), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('labels', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('annotations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('occurrence_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_duplicate', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('priority', sa.String(length=50), nullable=False, server_default='MEDIUM'),
        sa.Column('is_storm', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['raw_alert_id'], ['raw_alerts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_canonical_alerts_id'), 'canonical_alerts', ['id'], unique=False)
    op.create_index(op.f('ix_canonical_alerts_raw_alert_id'), 'canonical_alerts', ['raw_alert_id'], unique=False)
    op.create_index(op.f('ix_canonical_alerts_incident_id'), 'canonical_alerts', ['incident_id'], unique=False)
    op.create_index(op.f('ix_canonical_alerts_fingerprint'), 'canonical_alerts', ['fingerprint'], unique=False)
    op.create_index('ix_canonical_alerts_fingerprint_last_seen', 'canonical_alerts', ['fingerprint', sa.text('last_seen DESC')])
    op.create_index(op.f('ix_canonical_alerts_service'), 'canonical_alerts', ['service'], unique=False)
    op.create_index(op.f('ix_canonical_alerts_severity'), 'canonical_alerts', ['severity'], unique=False)
    op.create_index(op.f('ix_canonical_alerts_status'), 'canonical_alerts', ['status'], unique=False)
    op.create_index(op.f('ix_canonical_alerts_is_duplicate'), 'canonical_alerts', ['is_duplicate'], unique=False)
    op.create_index(op.f('ix_canonical_alerts_priority'), 'canonical_alerts', ['priority'], unique=False)
    op.create_index(op.f('ix_canonical_alerts_is_storm'), 'canonical_alerts', ['is_storm'], unique=False)
    op.create_index(op.f('ix_canonical_alerts_timestamp'), 'canonical_alerts', ['timestamp'], unique=False)
    op.create_index(op.f('ix_canonical_alerts_last_seen'), 'canonical_alerts', ['last_seen'], unique=False)


def downgrade() -> None:
    op.drop_table('canonical_alerts')
    op.drop_table('incidents')
