"""Add processing_time_ms to decision_records for Phase 4 analytics

Revision ID: 004_phase4_analytics_metadata
Revises: 003_phase3_decision_models
Create Date: 2026-09-04 12:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004_phase4_analytics_metadata'
down_revision: Union[str, None] = '003_phase3_decision_models'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'decision_records',
        sa.Column('processing_time_ms', sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('decision_records', 'processing_time_ms')
