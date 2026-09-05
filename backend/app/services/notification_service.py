import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import (
    record_notification_metric,
    record_notification_duration,
    record_slack_metric
)
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.models.decision_record import DecisionRecord
from app.models.notification_record import NotificationRecord
import app.services.slack_notifier as slack_notifier
import app.services.email_notifier as email_notifier


from app.services.slack_retry_service import calculate_backoff_delay, schedule_next_retry


def dispatch_notification(
    db: Session,
    decision_record: DecisionRecord,
    incident: Incident,
    canonical_alert: Optional[CanonicalAlert] = None,
    notification_type: str = "INITIAL",
    channel: str = "slack"
) -> NotificationRecord:
    """
    Dispatches notification via designated channel ('email' or 'slack'), updates incident.last_notified_at,
    records sanitized NotificationRecord in database, and records Prometheus metrics.
    Enforces incident-level idempotency to prevent duplicate notifications for the same incident.
    Persists delivery states (attempt_count, next_retry_at, delivered_at, last_error).
    Never raises an unhandled exception that could abort the caller's pipeline.
    """
    now = datetime.now(timezone.utc)
    env = (canonical_alert.labels.get("environment") or canonical_alert.labels.get("env") or "production") if canonical_alert and canonical_alert.labels else "production"
    sev = canonical_alert.severity if canonical_alert else incident.priority
    priority = canonical_alert.priority if canonical_alert else incident.priority
    alert_name = canonical_alert.alert_name if canonical_alert else incident.title
    occ_count = canonical_alert.occurrence_count if canonical_alert else incident.alert_count

    snapshot = decision_record.context_snapshot or {}
    probable_cause = snapshot.get("probable_cause")
    resolution_steps = snapshot.get("resolution_steps")
    risk_score = snapshot.get("risk_score")
    risk_level = snapshot.get("risk_level")

    delivered_at = None
    next_retry_at = None
    slack_message_ts = None
    is_transient = False
    attempt_count = 1
    last_attempt_at = now

    # -------------------------------------------------------------------------
    # Channel: EMAIL (Real SMTP Escalation)
    # -------------------------------------------------------------------------
    if channel == "email":
        # Check idempotency: if an email was already successfully SENT/DELIVERED for this incident, prevent duplicate
        existing_sent = (
            db.query(NotificationRecord)
            .filter(
                NotificationRecord.incident_id == incident.id,
                NotificationRecord.channel == "email",
                NotificationRecord.status.in_(["SENT", "DELIVERED"])
            )
            .first()
        )
        if existing_sent:
            logger.info(
                f"Skipping duplicate email notification for incident [{incident.incident_number}]: "
                f"Notification [{existing_sent.id}] was already DELIVERED."
            )
            return existing_sent

        # Format duration string
        def _to_utc(dt: Optional[datetime]) -> datetime:
            if dt is None:
                return now
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        start_ts = _to_utc(incident.first_seen)
        end_ts = _to_utc(incident.last_seen)
        dur_sec = max(0.0, (end_ts - start_ts).total_seconds())
        dur_str = f"{int(dur_sec)}s" if dur_sec < 60 else f"{int(dur_sec // 60)}m {int(dur_sec % 60)}s"

        alert_type = (
            (canonical_alert.labels.get("alert_type") or canonical_alert.labels.get("type"))
            if canonical_alert and canonical_alert.labels
            else alert_name
        )

        start_notif = time.perf_counter()
        try:
            result = email_notifier.send_email_notification(
                incident_number=incident.incident_number,
                incident_id=str(incident.id),
                service=incident.service,
                alert_type=alert_type,
                severity=sev,
                priority=priority,
                environment=env,
                occurrence_count=occ_count,
                risk_score=risk_score,
                risk_level=risk_level,
                first_seen=incident.first_seen,
                last_seen=incident.last_seen,
                duration_str=dur_str,
                reason=decision_record.reason,
                reason_codes=decision_record.reason_codes,
                probable_cause=probable_cause,
                resolution_steps=resolution_steps
            )
        except Exception as exc:
            logger.error(f"Error executing email_notifier: {exc}", exc_info=True)
            result = {"status": "FAILED", "error": str(exc), "destination": settings.ALERT_EMAIL_TO or "unknown", "payload": {}}

        notif_dur = time.perf_counter() - start_notif
        record_notification_duration(channel=channel, duration=notif_dur)

        status = result.get("status", "FAILED")
        err = result.get("error")
        destination = result.get("destination", "unknown")
        clean_payload = result.get("payload", {})
        if status in ("SENT", "DELIVERED"):
            delivered_at = now

    # -------------------------------------------------------------------------
    # Channel: SLACK (Resilient Delivery & Retry Tracking)
    # -------------------------------------------------------------------------
    else:
        # Check idempotency: if a Slack notification was already successfully DELIVERED for this incident, prevent duplicate
        existing_sent = (
            db.query(NotificationRecord)
            .filter(
                NotificationRecord.incident_id == incident.id,
                NotificationRecord.channel == "slack",
                NotificationRecord.status.in_(["SENT", "DELIVERED"])
            )
            .first()
        )
        if existing_sent and notification_type not in ["RESOLUTION", "MANUAL"]:
            record_slack_metric(status="duplicate")
            logger.info(
                f"Slack notification duplicate skipped: incident_id={incident.id}, "
                f"incident_number={incident.incident_number}, previous_notification_id={existing_sent.id}"
            )
            return existing_sent

        target_channel = settings.SLACK_CHANNEL_ID or settings.SLACK_CHANNEL
        logger.info(
            f"Slack notification started: incident_id={incident.id}, "
            f"incident_number={incident.incident_number}, type={notification_type}, destination={target_channel}"
        )

        dedup_val = max(0, incident.alert_count - incident.unique_alerts_count) if incident.alert_count > 0 else 0
        fps_val = incident.unique_alerts_count or 1

        raw_payload = slack_notifier.build_slack_blocks(
            notification_type=notification_type,
            incident_number=incident.incident_number,
            service=incident.service,
            alert_name=alert_name,
            severity=sev,
            priority=priority,
            environment=env,
            occurrence_count=occ_count,
            reason_codes=decision_record.reason_codes,
            reason=decision_record.reason,
            incident_id=str(incident.id),
            decision_id=str(decision_record.id),
            decision=decision_record.decision,
            risk_score=risk_score,
            risk_level=risk_level,
            dedup_count=dedup_val,
            unique_fingerprints=fps_val,
            escalation_level=incident.escalation_level,
            probable_cause=probable_cause,
            resolution_steps=resolution_steps
        )

        start_notif = time.perf_counter()
        try:
            result = slack_notifier.send_slack_notification(payload=raw_payload)
        except Exception as exc:
            logger.error(f"Unexpected exception calling send_slack_notification: {exc}", exc_info=True)
            result = {
                "status": "FAILED",
                "error": str(exc),
                "channel": target_channel,
                "ts": None,
                "is_transient": True,
                "retry_after": None,
                "duration_sec": 0.001
            }

        notif_dur = time.perf_counter() - start_notif
        record_notification_duration(channel=channel, duration=notif_dur)

        raw_status = result.get("status", "FAILED")
        err = result.get("error")
        destination = result.get("channel") or target_channel
        clean_payload = slack_notifier.sanitize_payload(raw_payload)
        slack_message_ts = result.get("ts")
        if slack_message_ts:
            clean_payload["slack_ts"] = slack_message_ts

        is_transient = result.get("is_transient", False)
        retry_after = result.get("retry_after")

        if raw_status in ("SENT", "DELIVERED"):
            status = "SENT"
            delivered_at = now
            record_slack_metric(status="delivered", duration_sec=notif_dur)
            logger.info(f"Slack notification delivered: incident_id={incident.id}, destination={destination}")
        else:
            # Distinguish Transient vs Permanent Failure
            if is_transient and attempt_count < getattr(settings, "SLACK_MAX_RETRIES", 5):
                status = "RETRYING"
                delay = calculate_backoff_delay(attempt_count=attempt_count, retry_after=retry_after)
                next_retry_at = now + timedelta(seconds=delay)
                record_slack_metric(status="retrying", duration_sec=notif_dur)
                logger.warning(
                    f"Slack notification transient failure: incident_id={incident.id}, error={err}. "
                    f"Scheduled retry in {delay}s."
                )
            else:
                status = "FAILED"
                next_retry_at = None
                record_slack_metric(
                    status="failed",
                    duration_sec=notif_dur,
                    error_type="transient_exhausted" if is_transient else "permanent"
                )
                logger.error(
                    f"Slack notification permanent failure: incident_id={incident.id}, error={err}"
                )

    # 3. Update Incident last_notified_at so state engine knows initial notification was triggered
    incident.last_notified_at = now
    db.add(incident)

    # 4. Create NotificationRecord in PostgreSQL
    notif_record = NotificationRecord(
        decision_id=decision_record.id,
        incident_id=incident.id,
        canonical_alert_id=canonical_alert.id if canonical_alert else None,
        channel=channel,
        destination=destination,
        notification_type=notification_type,
        status=status,
        payload=clean_payload,
        error_message=err,
        last_error=err,
        sent_at=now,
        attempt_count=attempt_count,
        created_at=now,
        last_attempt_at=last_attempt_at,
        next_retry_at=next_retry_at,
        delivered_at=delivered_at,
        slack_message_ts=slack_message_ts,
        is_transient=is_transient
    )
    db.add(notif_record)
    db.flush()

    # 5. Record Prometheus metrics
    record_notification_metric(
        channel=channel,
        success=(status in ("SENT", "DELIVERED")),
        priority=priority,
        service=incident.service
    )

    logger.info(
        f"Notification [{notif_record.id}] for incident [{incident.incident_number}] "
        f"dispatched to {channel} [{destination}] with status [{status}]"
    )

    return notif_record
