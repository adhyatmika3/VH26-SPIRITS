import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DecisionExplanation(BaseModel):
    decision: str
    reason_codes: List[str]
    reason: str


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_alert_id: Optional[uuid.UUID] = None
    incident_id: Optional[uuid.UUID] = None
    decision: str
    reason_codes: List[str]
    reason: str
    context_snapshot: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DecisionListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[DecisionResponse]
