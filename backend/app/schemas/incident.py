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


class RunbookPrecheck(BaseModel):
    id: str
    name: str
    status: str  # PASS, FAILING, DEGRADED
    detail: str


class RunbookStep(BaseModel):
    index: int
    title: str
    action_type: str  # DRAIN, SCALE, RECYCLE, VERIFY
    command: str
    expected_duration: str
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED
    output: Optional[str] = None


class RunbookResponse(BaseModel):
    incident_id: uuid.UUID
    incident_number: str
    service: str
    sop_code: str
    title: str
    description: str
    prechecks: List[RunbookPrecheck] = []
    steps: List[RunbookStep] = []
    status: str = "READY"  # READY, IN_PROGRESS, COMPLETED


class RunbookExecuteRequest(BaseModel):
    step_index: Optional[int] = None  # If None, executes all steps
    actor: Optional[str] = "sre-operator"


class RunbookExecuteResponse(BaseModel):
    incident_id: uuid.UUID
    step_index: Optional[int] = None
    status: str  # SUCCESS, FAILED
    logs: List[str] = []
    completed_steps: List[int] = []
    all_completed: bool = False
    message: str


