"""Create decision, notification, and escalation models

Revision ID: 003_phase3_decision_models
Revises: 002_phase2_intelligence_models
Create Date: 2026-09-04 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_phase3_decision_models'
down_revision: Union[str, None] = '002_phase2_intelligence_models'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend incidents table with Phase 3 lifecycle and escalation columns
    op.add_column('incidents', sa.Column('escalation_level', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('incidents', sa.Column('last_notified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('incidents', sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('incidents', sa.Column('acknowledged_by', sa.String(length=255), nullable=True))
    op.add_column('incidents', sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('incidents', sa.Column('resolved_by', sa.String(length=255), nullable=True))

    # 2. Create decision_records table
    op.create_table(
        'decision_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('canonical_alert_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('incident_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('decision', sa.String(length=50), nullable=False),
        sa.Column('reason_codes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('context_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['canonical_alert_id'], ['canonical_alerts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_decision_records_id'), 'decision_records', ['id'], unique=False)
    op.create_index(op.f('ix_decision_records_canonical_alert_id'), 'decision_records', ['canonical_alert_id'], unique=False)
    op.create_index(op.f('ix_decision_records_incident_id'), 'decision_records', ['incident_id'], unique=False)
    op.create_index(op.f('ix_decision_records_decision'), 'decision_records', ['decision'], unique=False)
    op.create_index(op.f('ix_decision_records_created_at'), 'decision_records', ['created_at'], unique=False)

    # 3. Create notification_records table
    op.create_table(
        'notification_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('decision_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('incident_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('canonical_alert_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('destination', sa.String(length=255), nullable=False),
        sa.Column('notification_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error_message', sa.String(length=1000), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['decision_id'], ['decision_records.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['canonical_alert_id'], ['canonical_alerts.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_notification_records_id'), 'notification_records', ['id'], unique=False)
    op.create_index(op.f('ix_notification_records_decision_id'), 'notification_records', ['decision_id'], unique=False)
    op.create_index(op.f('ix_notification_records_incident_id'), 'notification_records', ['incident_id'], unique=False)
    op.create_index(op.f('ix_notification_records_canonical_alert_id'), 'notification_records', ['canonical_alert_id'], unique=False)
    op.create_index(op.f('ix_notification_records_channel'), 'notification_records', ['channel'], unique=False)
    op.create_index(op.f('ix_notification_records_status'), 'notification_records', ['status'], unique=False)
    op.create_index(op.f('ix_notification_records_notification_type'), 'notification_records', ['notification_type'], unique=False)
    op.create_index(op.f('ix_notification_records_sent_at'), 'notification_records', ['sent_at'], unique=False)

    # 4. Create escalation_records table
    op.create_table(
        'escalation_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('incident_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('canonical_alert_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('escalation_level', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('reason_codes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='TRIGGERED'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['canonical_alert_id'], ['canonical_alerts.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('incident_id', 'escalation_level', name='uq_incident_escalation_level')
    )
    op.create_index(op.f('ix_escalation_records_id'), 'escalation_records', ['id'], unique=False)
    op.create_index(op.f('ix_escalation_records_incident_id'), 'escalation_records', ['incident_id'], unique=False)
    op.create_index(op.f('ix_escalation_records_canonical_alert_id'), 'escalation_records', ['canonical_alert_id'], unique=False)
    op.create_index(op.f('ix_escalation_records_status'), 'escalation_records', ['status'], unique=False)
    op.create_index(op.f('ix_escalation_records_created_at'), 'escalation_records', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('escalation_records')
    op.drop_table('notification_records')
    op.drop_table('decision_records')
    op.drop_column('incidents', 'resolved_by')
    op.drop_column('incidents', 'resolved_at')
    op.drop_column('incidents', 'acknowledged_by')
    op.drop_column('incidents', 'acknowledged_at')
    op.drop_column('incidents', 'last_notified_at')
    op.drop_column('incidents', 'escalation_level')
