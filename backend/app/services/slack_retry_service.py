import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import (
    record_slack_metric,
    SLACK_NOTIFICATION_PENDING
)
from app.models.notification_record import NotificationRecord
import app.services.slack_notifier as slack_notifier
import app.services.slack_service as slack_service


def calculate_backoff_delay(attempt_count: int, retry_after: Optional[int] = None) -> int:
    """
    Computes retry backoff delay:
    - If retry_after is provided by Slack API (HTTP 429 Retry-After), respect it directly.
    - Otherwise, compute exponential backoff:
        attempt 1: 5s
        attempt 2: 15s
        attempt 3: 45s
        attempt 4: 120s
        attempt 5+: capped at 300s (5 min)
    """
    if retry_after is not None and retry_after > 0:
        return min(retry_after, 300)

    base = getattr(settings, "SLACK_RETRY_BASE_SECONDS", 5)
    # Scaled backoff: 5, 15, 45, 120, 300
    backoff_multipliers = [1, 3, 9, 24, 60]
    idx = min(max(0, attempt_count - 1), len(backoff_multipliers) - 1)
    delay = base * backoff_multipliers[idx]
    return min(delay, 300)


def schedule_next_retry(
    record: NotificationRecord,
    is_transient: bool,
    retry_after: Optional[int] = None
) -> None:
    """
    Evaluates error category and retry limits to transition notification state:
    - Transient + attempt_count < SLACK_MAX_RETRIES => RETRYING, next_retry_at set
    - Permanent or attempt_count >= SLACK_MAX_RETRIES => FAILED, next_retry_at cleared
    """
    max_retries = getattr(settings, "SLACK_MAX_RETRIES", 5)
    record.is_transient = is_transient

    if is_transient and record.attempt_count < max_retries:
        record.status = "RETRYING"
        delay = calculate_backoff_delay(record.attempt_count, retry_after)
        record.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        logger.info(
            f"Scheduled Slack retry #{record.attempt_count} for notification [{record.id}] "
            f"in {delay}s at {record.next_retry_at.isoformat()}"
        )
    else:
        record.status = "FAILED"
        record.next_retry_at = None
        logger.warning(
            f"Slack notification [{record.id}] marked permanent FAILED "
            f"(transient={is_transient}, attempt_count={record.attempt_count}/{max_retries})"
        )


def process_pending_slack_retries(db: Session, max_records: int = 50) -> Dict[str, Any]:
    """
    Worker function to process queued/retrying Slack notifications.
    Adheres to:
    1. Only retries transient failures where next_retry_at <= now
    2. Bounded maximum retries
    3. Duplicate retry protection (Section 10): skips already delivered records
    4. Updates Prometheus observability metrics
    """
    now = datetime.now(timezone.utc)

    # 1. Query pending/retrying notifications ready for dispatch
    stmt = (
        select(NotificationRecord)
        .where(
            and_(
                NotificationRecord.channel == "slack",
                NotificationRecord.status.in_(["RETRYING", "PENDING"]),
                or_(
                    NotificationRecord.next_retry_at <= now,
                    NotificationRecord.next_retry_at.is_(None)
                ),
                NotificationRecord.attempt_count < settings.SLACK_MAX_RETRIES
            )
        )
        .order_by(NotificationRecord.created_at.asc())
        .limit(max_records)
    )

    records = db.execute(stmt).scalars().all()

    # 2. Count total pending in system for Gauge metric
    count_pending_stmt = (
        select(NotificationRecord)
        .where(
            and_(
                NotificationRecord.channel == "slack",
                NotificationRecord.status.in_(["RETRYING", "PENDING"])
            )
        )
    )
    total_pending = len(db.execute(count_pending_stmt).scalars().all())
    SLACK_NOTIFICATION_PENDING.set(total_pending)

    delivered_count = 0
    failed_count = 0
    retrying_count = 0
    skipped_duplicate_count = 0

    for record in records:
        # Duplicate Protection Check (Section 10)
        # If record already has a slack_message_ts or delivered_at, do not re-send
        if record.slack_message_ts or record.delivered_at or record.status in ("DELIVERED", "SENT"):
            record.status = "SENT"
            record.next_retry_at = None
            db.add(record)
            db.commit()
            skipped_duplicate_count += 1
            logger.info(f"Duplicate protection: Notification [{record.id}] already has delivery ts={record.slack_message_ts}. Skipping.")
            continue

        # Mark in progress
        record.status = "SENDING"
        record.attempt_count += 1
        record.last_attempt_at = now
        db.add(record)
        db.commit()

        # Attempt Slack Delivery
        start_ts = time.perf_counter()
        result = slack_notifier.send_slack_notification(payload=record.payload)
        duration = time.perf_counter() - start_ts

        status = result.get("status", "FAILED")
        err = result.get("error")
        ts = result.get("ts")
        is_transient = result.get("is_transient", False)
        retry_after = result.get("retry_after")

        if status in ("SENT", "DELIVERED"):
            record.status = "SENT"
            record.delivered_at = datetime.now(timezone.utc)
            record.slack_message_ts = ts
            record.next_retry_at = None
            record.last_error = None
            record.error_message = None
            db.add(record)
            db.commit()

            delivered_count += 1
            record_slack_metric(status="delivered", duration_sec=duration)
            logger.info(f"Successfully delivered retried Slack notification [{record.id}] (ts={ts})")
        else:
            record.last_error = err
            record.error_message = err
            schedule_next_retry(record, is_transient=is_transient, retry_after=retry_after)
            db.add(record)
            db.commit()

            if record.status == "RETRYING":
                retrying_count += 1
                record_slack_metric(status="retrying", duration_sec=duration)
            else:
                failed_count += 1
                record_slack_metric(status="failed", duration_sec=duration, error_type="transient_exhausted" if is_transient else "permanent")

    # Re-calculate remaining pending gauge
    remaining_pending = len(db.execute(count_pending_stmt).scalars().all())
    SLACK_NOTIFICATION_PENDING.set(remaining_pending)

    return {
        "processed": len(records),
        "delivered": delivered_count,
        "failed": failed_count,
        "retrying": retrying_count,
        "skipped_duplicate": skipped_duplicate_count,
        "remaining_pending": remaining_pending
    }


def get_pending_slack_notifications(db: Session, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Returns list of pending/retrying Slack notification records.
    """
    stmt = (
        select(NotificationRecord)
        .where(
            and_(
                NotificationRecord.channel == "slack",
                NotificationRecord.status.in_(["RETRYING", "PENDING", "SENDING"])
            )
        )
        .order_by(NotificationRecord.created_at.desc())
        .limit(limit)
    )
    records = db.execute(stmt).scalars().all()
    results = []
    for r in records:
        results.append({
            "id": str(r.id),
            "incident_id": str(r.incident_id) if r.incident_id else None,
            "decision_id": str(r.decision_id) if r.decision_id else None,
            "status": r.status,
            "attempt_count": r.attempt_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "last_attempt_at": r.last_attempt_at.isoformat() if r.last_attempt_at else None,
            "next_retry_at": r.next_retry_at.isoformat() if r.next_retry_at else None,
            "last_error": r.last_error or r.error_message,
            "is_transient": r.is_transient
        })
    return results
