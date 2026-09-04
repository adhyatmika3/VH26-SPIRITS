import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.incident import Incident
from datetime import datetime, timezone
from app.schemas.incident import (
    IncidentResponse,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentAcknowledgeRequest,
    IncidentResolveRequest
)
from app.schemas.notification import NotificationSendRequest, NotificationResponse
from app.models.decision_record import DecisionRecord
from app.services.notification_service import dispatch_notification
from app.core.metrics import record_acknowledgement_metric, record_resolution_metric

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get(
    "",
    response_model=IncidentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List incidents",
    description="Retrieve correlated incidents with filtering by status, priority, and service."
)
def list_incidents(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (OPEN, ACKNOWLEDGED, RESOLVED)"),
    priority: Optional[str] = Query(None, description="Filter by priority (LOW, MEDIUM, HIGH, CRITICAL)"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    is_storm: Optional[bool] = Query(None, description="Filter by storm flag"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Page limit"),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    stmt = select(Incident)

    if status_filter:
        stmt = stmt.where(Incident.status == status_filter.upper())
    if priority:
        stmt = stmt.where(Incident.priority == priority.upper())
    if service:
        stmt = stmt.where(Incident.service == service.lower())
    if is_storm is not None:
        stmt = stmt.where(Incident.is_storm == is_storm)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0

    items_stmt = stmt.order_by(Incident.last_seen.desc()).offset(offset).limit(limit)
    items = db.execute(items_stmt).scalars().all()

    return IncidentListResponse(
        total=total,
        page=page,
        limit=limit,
        items=items
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get incident details",
    description="Retrieve incident details including all correlated canonical alerts."
)
def get_incident_by_id(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    stmt = select(Incident).where(Incident.id == incident_id)
    incident = db.execute(stmt).scalar_one_or_none()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    return incident


@router.post(
    "/{incident_id}/acknowledge",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Acknowledge incident",
    description="Acknowledge an incident and assign operator attribution."
)
def acknowledge_incident(
    incident_id: uuid.UUID,
    req: IncidentAcknowledgeRequest = IncidentAcknowledgeRequest(),
    db: Session = Depends(get_db)
):
    stmt = select(Incident).where(Incident.id == incident_id)
    incident = db.execute(stmt).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {incident_id} not found")

    incident.status = "ACKNOWLEDGED"
    incident.acknowledged_at = datetime.now(timezone.utc)
    incident.acknowledged_by = req.actor or "sre-operator"
    db.add(incident)
    db.commit()
    db.refresh(incident)

    record_acknowledgement_metric(service=incident.service)
    return incident


@router.post(
    "/{incident_id}/resolve",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve incident",
    description="Resolve an incident and mark all attached alerts resolved."
)
def resolve_incident(
    incident_id: uuid.UUID,
    req: IncidentResolveRequest = IncidentResolveRequest(),
    db: Session = Depends(get_db)
):
    stmt = select(Incident).where(Incident.id == incident_id)
    incident = db.execute(stmt).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {incident_id} not found")

    now = datetime.now(timezone.utc)
    incident.status = "RESOLVED"
    incident.resolved_at = now
    incident.resolved_by = req.actor or "sre-operator"

    # Mark all canonical alerts on this incident as RESOLVED
    for alert in incident.alerts:
        alert.status = "RESOLVED"
        db.add(alert)

    # Create DecisionRecord for resolution
    dec_record = DecisionRecord(
        incident_id=incident.id,
        decision="NOTIFY",
        reason_codes=["INCIDENT_MANUALLY_RESOLVED"],
        reason=f"Incident [{incident.incident_number}] was manually resolved by {incident.resolved_by}.",
        context_snapshot={"service": incident.service, "priority": incident.priority, "status": "RESOLVED"},
        created_at=now
    )
    db.add(dec_record)
    db.flush()

    # Dispatch resolution Slack notification if previously notified
    if incident.last_notified_at is not None:
        dispatch_notification(
            db=db,
            decision_record=dec_record,
            incident=incident,
            notification_type="RESOLUTION",
            channel="slack"
        )

    db.commit()
    db.refresh(incident)

    record_resolution_metric(service=incident.service)
    return incident


@router.post(
    "/{incident_id}/notify",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger manual notification",
    description="Manually dispatch a notification for an incident."
)
def manual_incident_notification(
    incident_id: uuid.UUID,
    req: NotificationSendRequest = NotificationSendRequest(),
    db: Session = Depends(get_db)
):
    stmt = select(Incident).where(Incident.id == incident_id)
    incident = db.execute(stmt).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {incident_id} not found")

    now = datetime.now(timezone.utc)
    dec_record = DecisionRecord(
        incident_id=incident.id,
        decision="NOTIFY",
        reason_codes=["MANUAL_OPERATOR_DISPATCH"],
        reason=f"Operator manually triggered notification for incident [{incident.incident_number}].",
        context_snapshot={"service": incident.service, "priority": incident.priority, "manual": True},
        created_at=now
    )
    db.add(dec_record)
    db.flush()

    notif_record = dispatch_notification(
        db=db,
        decision_record=dec_record,
        incident=incident,
        notification_type="MANUAL",
        channel=req.channel or "slack"
    )
    db.commit()
    db.refresh(notif_record)
    return notif_record

