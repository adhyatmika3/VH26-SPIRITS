"""Phase 7 Slack Failure Fallback & Notification Resilience fields

Revision ID: 006_phase7_slack_resilience
Revises: 005_phase5_ai_resolution
Create Date: 2026-09-05 05:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '006_phase7_slack_resilience'
down_revision: Union[str, None] = '005_phase5_ai_resolution'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        ALTER TABLE notification_records
            ADD COLUMN IF NOT EXISTS attempt_count INTEGER DEFAULT 0 NOT NULL,
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS last_error VARCHAR(1000),
            ADD COLUMN IF NOT EXISTS slack_message_ts VARCHAR(50),
            ADD COLUMN IF NOT EXISTS is_transient BOOLEAN DEFAULT FALSE;

        CREATE INDEX IF NOT EXISTS ix_notification_records_next_retry_at ON notification_records (next_retry_at);
        CREATE INDEX IF NOT EXISTS ix_notification_records_slack_message_ts ON notification_records (slack_message_ts);
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DROP INDEX IF EXISTS ix_notification_records_slack_message_ts;
        DROP INDEX IF EXISTS ix_notification_records_next_retry_at;

        ALTER TABLE notification_records
            DROP COLUMN IF EXISTS is_transient,
            DROP COLUMN IF EXISTS slack_message_ts,
            DROP COLUMN IF EXISTS last_error,
            DROP COLUMN IF EXISTS delivered_at,
            DROP COLUMN IF EXISTS next_retry_at,
            DROP COLUMN IF EXISTS last_attempt_at,
            DROP COLUMN IF EXISTS created_at,
            DROP COLUMN IF EXISTS attempt_count;
    """))
