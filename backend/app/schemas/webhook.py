from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class AlertWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = Field(..., min_length=1, max_length=100, description="Alert origin tool, e.g. prometheus")
    alert_name: str = Field(..., min_length=1, max_length=255, description="Logical name of the alert")
    service: str = Field(..., min_length=1, max_length=255, description="Impacted microservice or component")
    resource: Optional[str] = Field(None, max_length=255, description="Specific pod, host, or resource instance")
    severity: str = Field(..., min_length=1, max_length=50, description="Severity level, e.g. critical, high, warning")
    status: str = Field(..., min_length=1, max_length=50, description="State of the alert, e.g. firing, resolved")
    timestamp: datetime = Field(..., description="Timestamp of the event from alert source")
    labels: Dict[str, Any] = Field(default_factory=dict, description="Key-value labels from monitoring tool")
    annotations: Dict[str, Any] = Field(default_factory=dict, description="Descriptive annotations, summary, runbooks")


class WebhookIngestResponse(BaseModel):
    accepted: bool = True
    alert_id: str
    status: str = "received"
    # Phase 2 enriched processing fields
    canonical_alert_id: Optional[str] = None
    incident_id: Optional[str] = None
    incident_number: Optional[str] = None
    fingerprint: Optional[str] = None
    is_duplicate: bool = False
    occurrence_count: int = 1
    priority: Optional[str] = None
    is_storm: bool = False
    # Phase 3 Decision & Notification fields
    decision: Optional[str] = None
    reason_codes: list[str] = Field(default_factory=list)
    reason: Optional[str] = None
    escalation_level: int = 0
    notification_status: Optional[str] = None

