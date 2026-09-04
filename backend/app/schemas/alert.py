import uuid
from datetime import datetime
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, ConfigDict, Field


class CanonicalAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    raw_alert_id: uuid.UUID
    incident_id: Optional[uuid.UUID] = None
    fingerprint: str
    source: str
    alert_name: str
    service: str
    resource: Optional[str] = None
    severity: str
    status: str
    message: str
    timestamp: datetime
    labels: Dict[str, Any] = Field(default_factory=dict)
    annotations: Dict[str, Any] = Field(default_factory=dict)
    occurrence_count: int
    is_duplicate: bool
    priority: str
    is_storm: bool
    first_seen: datetime
    last_seen: datetime
    created_at: datetime


class AlertListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[CanonicalAlertResponse]


class AlertStatsResponse(BaseModel):
    total_raw_alerts: int
    total_canonical_alerts: int
    total_duplicates_absorbed: int
    noise_reduction_ratio_percent: float
    is_storm_active: bool
    active_incidents_count: int
    severity_breakdown: Dict[str, int]
    top_services: Dict[str, int]
