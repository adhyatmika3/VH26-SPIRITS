from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from app.schemas.webhook import AlertWebhookPayload

SEVERITY_MAP = {
    "info": "INFO",
    "informational": "INFO",
    "low": "INFO",
    "warn": "WARNING",
    "warning": "WARNING",
    "medium": "WARNING",
    "err": "ERROR",
    "error": "ERROR",
    "high": "ERROR",
    "crit": "CRITICAL",
    "critical": "CRITICAL",
    "fatal": "CRITICAL",
    "p0": "CRITICAL",
    "p1": "ERROR",
    "p2": "WARNING",
    "p3": "INFO"
}

STATUS_MAP = {
    "firing": "FIRING",
    "triggered": "FIRING",
    "active": "FIRING",
    "open": "FIRING",
    "resolved": "RESOLVED",
    "cleared": "RESOLVED",
    "closed": "RESOLVED",
    "ok": "RESOLVED"
}


@dataclass
class NormalizedAlertData:
    source: str
    alert_name: str
    service: str
    resource: Optional[str]
    severity: str
    status: str
    message: str
    timestamp: datetime
    labels: Dict[str, Any]
    annotations: Dict[str, Any]


def normalize_alert(payload: AlertWebhookPayload) -> NormalizedAlertData:
    """
    Standardize incoming alert attributes into canonical forms.
    """
    # Normalize severity
    raw_sev = payload.severity.strip().lower()
    normalized_severity = SEVERITY_MAP.get(raw_sev, "WARNING")

    # Normalize status
    raw_status = payload.status.strip().lower()
    normalized_status = STATUS_MAP.get(raw_status, "FIRING")

    # Extract message from annotations or fallback
    annotations = payload.annotations or {}
    message = (
        annotations.get("description") or
        annotations.get("summary") or
        annotations.get("message") or
        annotations.get("details") or
        f"{payload.alert_name} alert triggered on service {payload.service}"
    )

    # Ensure timestamp has timezone
    ts = payload.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    return NormalizedAlertData(
        source=payload.source.strip().lower(),
        alert_name=payload.alert_name.strip(),
        service=payload.service.strip().lower(),
        resource=payload.resource.strip() if payload.resource else None,
        severity=normalized_severity,
        status=normalized_status,
        message=str(message).strip(),
        timestamp=ts,
        labels=payload.labels or {},
        annotations=annotations
    )
