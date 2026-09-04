import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationSendRequest(BaseModel):
    channel: str = Field("slack", description="Target notification channel (e.g. slack)")
    message: Optional[str] = Field(None, description="Optional custom notification message override")


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    decision_id: Optional[uuid.UUID] = None
    incident_id: Optional[uuid.UUID] = None
    canonical_alert_id: Optional[uuid.UUID] = None
    channel: str
    destination: str
    notification_type: str
    status: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    sent_at: datetime


class NotificationListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[NotificationResponse]
