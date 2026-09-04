import re
from typing import Any, Dict, List, Optional
from datetime import datetime
from app.core.config import settings
from app.core.logging import logger
import app.services.slack_service as slack_service

# Re-export sanitize_payload from slack_service
sanitize_payload = slack_service.sanitize_payload


def build_slack_blocks(
    notification_type: str,
    incident_number: str,
    service: str,
    alert_name: str,
    severity: str,
    priority: str,
    environment: str,
    occurrence_count: int,
    reason_codes: List[str],
    reason: str,
    escalation_level: int = 0,
    probable_cause: Optional[str] = None,
    resolution_steps: Optional[List[str]] = None,
    incident_id: Optional[str] = None,
    decision_id: Optional[str] = None,
    decision: Optional[str] = None,
    risk_score: Optional[int] = None,
    risk_level: Optional[str] = None,
    dedup_count: Optional[int] = None,
    unique_fingerprints: Optional[int] = None
) -> Dict[str, Any]:
    """
    Builds clean, structured Slack Block Kit message payload via slack_service.
    """
    return slack_service.build_incident_blocks(
        notification_type=notification_type,
        incident_number=incident_number,
        service=service,
        alert_name=alert_name,
        severity=severity,
        priority=priority,
        environment=environment,
        occurrence_count=occurrence_count,
        reason_codes=reason_codes,
        reason=reason,
        incident_id=incident_id,
        decision_id=decision_id,
        decision=decision,
        risk_score=risk_score,
        risk_level=risk_level,
        dedup_count=dedup_count,
        unique_fingerprints=unique_fingerprints,
        probable_cause=probable_cause,
        resolution_steps=resolution_steps,
        escalation_level=escalation_level
    )


def send_slack_notification(
    payload: Dict[str, Any],
    webhook_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Dispatches Slack notification via official Slack SDK (slack_service).
    Maintains compatibility with tests monkeypatching send_slack_notification.
    """
    return slack_service.send_incident_notification(payload=payload)

