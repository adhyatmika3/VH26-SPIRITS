import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.alert import CanonicalAlertResponse


class IncidentAcknowledgeRequest(BaseModel):
    actor: Optional[str] = "sre-operator"
    notes: Optional[str] = None


class IncidentResolveRequest(BaseModel):
    actor: Optional[str] = "sre-operator"
    notes: Optional[str] = None


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_number: str
    title: str
    service: str
    status: str
    priority: str
    alert_count: int
    unique_alerts_count: int
    is_storm: bool
    escalation_level: int = 0
    last_notified_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    first_seen: datetime
    last_seen: datetime
    created_at: datetime
    updated_at: datetime


class IncidentDetailResponse(IncidentResponse):
    alerts: List[CanonicalAlertResponse] = []


class IncidentListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[IncidentResponse]

