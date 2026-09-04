import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class EscalationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    canonical_alert_id: Optional[uuid.UUID] = None
    escalation_level: int
    reason_codes: List[str]
    reason: str
    status: str
    created_at: datetime


class EscalationListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[EscalationResponse]
