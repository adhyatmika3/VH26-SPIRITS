import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.decision_record import DecisionRecord
from app.schemas.decision import DecisionResponse, DecisionListResponse

router = APIRouter(prefix="/decisions", tags=["Decisions"])


@router.get(
    "",
    response_model=DecisionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List decision records",
    description="Retrieve historical decision evaluations with filtering by decision type, incident, or alert."
)
def list_decisions(
    decision: Optional[str] = Query(None, description="Filter by decision type (NOTIFY, SUPPRESS, ESCALATE)"),
    incident_id: Optional[uuid.UUID] = Query(None, description="Filter by incident UUID"),
    canonical_alert_id: Optional[uuid.UUID] = Query(None, description="Filter by canonical alert UUID"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Page limit"),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    stmt = select(DecisionRecord)

    if decision:
        stmt = stmt.where(DecisionRecord.decision == decision.upper())
    if incident_id:
        stmt = stmt.where(DecisionRecord.incident_id == incident_id)
    if canonical_alert_id:
        stmt = stmt.where(DecisionRecord.canonical_alert_id == canonical_alert_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0

    items_stmt = stmt.order_by(DecisionRecord.created_at.desc()).offset(offset).limit(limit)
    items = db.execute(items_stmt).scalars().all()

    return DecisionListResponse(
        total=total,
        page=page,
        limit=limit,
        items=items
    )


@router.get(
    "/{decision_id}",
    response_model=DecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get decision record detail",
    description="Retrieve details of a single decision record with structured reason codes."
)
def get_decision_by_id(
    decision_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    stmt = select(DecisionRecord).where(DecisionRecord.id == decision_id)
    record = db.execute(stmt).scalar_one_or_none()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision record {decision_id} not found"
        )
    return record
