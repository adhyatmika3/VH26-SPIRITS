import time
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import record_notification_metric, record_notification_duration
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.models.decision_record import DecisionRecord
from app.models.notification_record import NotificationRecord
import app.services.slack_notifier as slack_notifier



def dispatch_notification(
    db: Session,
    decision_record: DecisionRecord,
    incident: Incident,
    canonical_alert: Optional[CanonicalAlert] = None,
    notification_type: str = "INITIAL",
    channel: str = "slack"
) -> NotificationRecord:
    """
    Dispatches notification via designated channel, updates incident.last_notified_at,
    records sanitized NotificationRecord in database, and records Prometheus metrics.
    """
    now = datetime.now(timezone.utc)
    env = (canonical_alert.labels.get("environment") or "production") if canonical_alert else "production"
    sev = canonical_alert.severity if canonical_alert else incident.priority
    priority = canonical_alert.priority if canonical_alert else incident.priority
    alert_name = canonical_alert.alert_name if canonical_alert else incident.title
    occ_count = canonical_alert.occurrence_count if canonical_alert else incident.alert_count

    # 1. Build channel payload
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
        escalation_level=incident.escalation_level
    )

    # 2. Dispatch
    start_notif = time.perf_counter()
    result = slack_notifier.send_slack_notification(payload=raw_payload)
    notif_dur = time.perf_counter() - start_notif
    record_notification_duration(channel=channel, duration=notif_dur)
    status = result["status"]
    err = result.get("error")

    # 3. Update Incident last_notified_at if successfully dispatched/simulated
    if status == "SENT":
        incident.last_notified_at = now
        db.add(incident)

    # 4. Sanitize payload for persistent audit
    clean_payload = slack_notifier.sanitize_payload(raw_payload)


    # 5. Create NotificationRecord
    notif_record = NotificationRecord(
        decision_id=decision_record.id,
        incident_id=incident.id,
        canonical_alert_id=canonical_alert.id if canonical_alert else None,
        channel=channel,
        destination=settings.SLACK_CHANNEL,
        notification_type=notification_type,
        status=status,
        payload=clean_payload,
        error_message=err,
        sent_at=now
    )
    db.add(notif_record)
    db.flush()

    # 6. Record Prometheus metrics
    record_notification_metric(
        channel=channel,
        success=(status == "SENT"),
        priority=priority,
        service=incident.service
    )

    logger.info(
        f"Notification [{notif_record.id}] for incident [{incident.incident_number}] "
        f"dispatched to {channel} with status [{status}]"
    )

    return notif_record
