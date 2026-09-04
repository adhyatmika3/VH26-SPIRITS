"""Initial raw alerts table

Revision ID: 001_initial_raw_alerts
Revises: 
Create Date: 2026-09-04 11:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_raw_alerts'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'raw_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('alert_name', sa.String(length=255), nullable=False),
        sa.Column('service', sa.String(length=255), nullable=False),
        sa.Column('resource', sa.String(length=255), nullable=True),
        sa.Column('severity', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('labels', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('annotations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_raw_alerts_id'), 'raw_alerts', ['id'], unique=False)
    op.create_index(op.f('ix_raw_alerts_source'), 'raw_alerts', ['source'], unique=False)
    op.create_index(op.f('ix_raw_alerts_alert_name'), 'raw_alerts', ['alert_name'], unique=False)
    op.create_index(op.f('ix_raw_alerts_service'), 'raw_alerts', ['service'], unique=False)
    op.create_index(op.f('ix_raw_alerts_severity'), 'raw_alerts', ['severity'], unique=False)
    op.create_index(op.f('ix_raw_alerts_status'), 'raw_alerts', ['status'], unique=False)
    op.create_index(op.f('ix_raw_alerts_received_at'), 'raw_alerts', ['received_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_raw_alerts_received_at'), table_name='raw_alerts')
    op.drop_index(op.f('ix_raw_alerts_status'), table_name='raw_alerts')
    op.drop_index(op.f('ix_raw_alerts_severity'), table_name='raw_alerts')
    op.drop_index(op.f('ix_raw_alerts_service'), table_name='raw_alerts')
    op.drop_index(op.f('ix_raw_alerts_alert_name'), table_name='raw_alerts')
    op.drop_index(op.f('ix_raw_alerts_source'), table_name='raw_alerts')
    op.drop_index(op.f('ix_raw_alerts_id'), table_name='raw_alerts')
    op.drop_table('raw_alerts')
