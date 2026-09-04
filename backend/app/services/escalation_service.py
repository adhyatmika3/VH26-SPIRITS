from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.logging import logger
from app.core.metrics import record_escalation_metric
from app.models.incident import Incident
from app.models.canonical_alert import CanonicalAlert
from app.models.escalation_record import EscalationRecord


def record_incident_escalation(
    db: Session,
    incident: Incident,
    canonical_alert: Optional[CanonicalAlert],
    escalation_level: int,
    reason_codes: List[str],
    reason: str
) -> Optional[EscalationRecord]:
    """
    Records an escalation event for an incident with idempotency protection.
    """
    now = datetime.now(timezone.utc)

    # Check if escalation record at this level already exists (idempotency check)
    existing = (
        db.query(EscalationRecord)
        .filter(
            EscalationRecord.incident_id == incident.id,
            EscalationRecord.escalation_level == escalation_level
        )
        .first()
    )
    if existing:
        logger.info(
            f"Escalation Level {escalation_level} already exists for incident [{incident.incident_number}]. Skipping duplicate record."
        )
        return existing

    # Create EscalationRecord
    escalation = EscalationRecord(
        incident_id=incident.id,
        canonical_alert_id=canonical_alert.id if canonical_alert else None,
        escalation_level=escalation_level,
        reason_codes=reason_codes,
        reason=reason,
        status="TRIGGERED",
        created_at=now
    )
    db.add(escalation)

    # Update Incident escalation level
    incident.escalation_level = escalation_level
    db.add(incident)
    db.flush()

    # Record metric
    record_escalation_metric(severity=incident.priority, service=incident.service)

    logger.warning(
        f"Escalated incident [{incident.incident_number}] to Level {escalation_level} for service '{incident.service}'"
    )

    return escalation
