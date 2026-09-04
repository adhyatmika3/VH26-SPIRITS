import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.escalation_record import EscalationRecord
from app.schemas.escalation import EscalationResponse, EscalationListResponse

router = APIRouter(prefix="/escalations", tags=["Escalations"])


@router.get(
    "",
    response_model=EscalationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List escalation records",
    description="Retrieve all incident escalation events and levels."
)
def list_escalations(
    incident_id: Optional[uuid.UUID] = Query(None, description="Filter by incident UUID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Page limit"),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    stmt = select(EscalationRecord)

    if incident_id:
        stmt = stmt.where(EscalationRecord.incident_id == incident_id)
    if status_filter:
        stmt = stmt.where(EscalationRecord.status == status_filter.upper())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0

    items_stmt = stmt.order_by(EscalationRecord.created_at.desc()).offset(offset).limit(limit)
    items = db.execute(items_stmt).scalars().all()

    return EscalationListResponse(
        total=total,
        page=page,
        limit=limit,
        items=items
    )
