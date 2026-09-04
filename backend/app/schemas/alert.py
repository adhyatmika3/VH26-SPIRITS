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


class RawAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    alert_name: str
    service: str
    resource: Optional[str] = None
    severity: str
    status: str
    timestamp: datetime
    labels: Dict[str, Any] = Field(default_factory=dict)
    annotations: Dict[str, Any] = Field(default_factory=dict)
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    received_at: datetime


class RawAlertListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[RawAlertResponse]


class AlertSimulateRequest(BaseModel):
    count: int = Field(default=500, ge=1, le=1000, description="Number of alerts to simulate")
    service: str = Field(default="payment-api", description="Service identifier")
    alert_type: str = Field(default="CPU_HIGH", description="Logical alert category (CPU_HIGH, DATABASE_ERROR, etc.)")
    severity: str = Field(default="critical", description="Severity level")
    environment: str = Field(default="production", description="Deployment environment")
    delay_ms: int = Field(default=0, ge=0, le=5000, description="Delay between alert posts in milliseconds")
    scenario: Optional[str] = Field(default=None, description="Optional preset demo scenario (normal, spike, major, multiple)")


class AlertSimulateResponse(BaseModel):
    requested: int
    generated: int
    status: str
    service: str
    alert_type: str
    severity: str
    environment: str
    raw_alerts_count: int
    core_incidents_created: int
    alert_reduction_percent: float
    primary_incident_id: Optional[str] = None
    primary_incident_number: Optional[str] = None
    primary_incident_title: Optional[str] = None
    primary_incident_occurrences: int = 0
    primary_fingerprint: Optional[str] = None
    incidents_summary: List[Dict[str, Any]] = Field(default_factory=list)
    sample_variations: List[str] = Field(default_factory=list)
