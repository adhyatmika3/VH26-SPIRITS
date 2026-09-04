"""Add resolution_knowledge table and incidents.resolution_status

Revision ID: 005_phase5_ai_resolution
Revises: 004_phase4_analytics_metadata
Create Date: 2026-09-04 18:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005_phase5_ai_resolution'
down_revision: Union[str, None] = '004_phase4_analytics_metadata'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add resolution_status to incidents if not exists
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS resolution_status VARCHAR(50) DEFAULT 'KNOWN' NOT NULL;"))

    # Create resolution_knowledge table if not exists
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS resolution_knowledge (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            fingerprint VARCHAR(255) NOT NULL UNIQUE,
            alert_type VARCHAR(255) NOT NULL,
            service VARCHAR(255) NOT NULL,
            probable_cause TEXT NOT NULL,
            resolution_steps JSONB NOT NULL,
            confidence FLOAT NOT NULL,
            source VARCHAR(50) NOT NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_resolution_knowledge_fingerprint ON resolution_knowledge (fingerprint);
        CREATE INDEX IF NOT EXISTS ix_resolution_knowledge_alert_type ON resolution_knowledge (alert_type);
        CREATE INDEX IF NOT EXISTS ix_resolution_knowledge_service ON resolution_knowledge (service);
    """))


def downgrade() -> None:
    op.drop_table('resolution_knowledge')
    op.drop_column('incidents', 'resolution_status')
