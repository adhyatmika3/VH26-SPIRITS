import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.notification_record import NotificationRecord
from app.schemas.notification import NotificationResponse, NotificationListResponse

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List notification history",
    description="Retrieve notification dispatch logs with filtering by channel, status, type, and incident."
)
def list_notifications(
    channel: Optional[str] = Query(None, description="Filter by notification channel (e.g. slack)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (SENT, FAILED, SKIPPED)"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type (INITIAL, ESCALATION, RESOLUTION)"),
    incident_id: Optional[uuid.UUID] = Query(None, description="Filter by parent incident UUID"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Page limit"),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    stmt = select(NotificationRecord)

    if channel:
        stmt = stmt.where(NotificationRecord.channel == channel.lower())
    if status_filter:
        stmt = stmt.where(NotificationRecord.status == status_filter.upper())
    if notification_type:
        stmt = stmt.where(NotificationRecord.notification_type == notification_type.upper())
    if incident_id:
        stmt = stmt.where(NotificationRecord.incident_id == incident_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0

    items_stmt = stmt.order_by(NotificationRecord.sent_at.desc()).offset(offset).limit(limit)
    items = db.execute(items_stmt).scalars().all()

    return NotificationListResponse(
        total=total,
        page=page,
        limit=limit,
        items=items
    )
