import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.decision_record import DecisionRecord
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.schemas.dashboard import (
    DashboardSummaryResponse,
    DecisionExplanationResponse,
    IncidentTimelineResponse
)
from app.services.dashboard_service import (
    calculate_dashboard_summary,
    explain_decision,
    assemble_incident_timeline
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard Intelligence"])


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get comprehensive dashboard summary",
    description="Retrieve live aggregated metrics including deduplication, suppression, MTTA, MTTR, and Before vs After statistics."
)
def get_dashboard_summary_endpoint(db: Session = Depends(get_db)):
    return calculate_dashboard_summary(db)


@router.get(
    "/explain/{decision_id}",
    response_model=DecisionExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Explain a decision for non-technical judges",
    description="Retrieve plain-English What/Why/Confidence breakdown with expandable technical details for a specific decision record."
)
def explain_decision_endpoint(
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
    return explain_decision(record)


@router.get(
    "/explain/alert/{alert_id}",
    response_model=DecisionExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Explain latest decision for an alert",
    description="Retrieve plain-English decision breakdown associated with a canonical alert."
)
def explain_alert_decision_endpoint(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    # Try finding decision by canonical_alert_id first
    stmt = (
        select(DecisionRecord)
        .where(DecisionRecord.canonical_alert_id == alert_id)
        .order_by(DecisionRecord.created_at.desc())
    )
    record = db.execute(stmt).scalars().first()

    # Fallback to checking if alert is correlated to an incident
    if not record:
        alert_stmt = select(CanonicalAlert).where(CanonicalAlert.id == alert_id)
        alert = db.execute(alert_stmt).scalar_one_or_none()
        if alert and alert.incident_id:
            inc_stmt = (
                select(DecisionRecord)
                .where(DecisionRecord.incident_id == alert.incident_id)
                .order_by(DecisionRecord.created_at.desc())
            )
            record = db.execute(inc_stmt).scalars().first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No decision found for alert {alert_id}"
        )
    return explain_decision(record)


@router.get(
    "/timeline/{incident_id}",
    response_model=IncidentTimelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Get incident chronological lifecycle timeline",
    description="Retrieve chronological milestones (Ingestion -> Deduplication -> Grouping -> Decision -> Notification -> Acknowledged -> Resolved)."
)
def get_incident_timeline_endpoint(
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
    return assemble_incident_timeline(incident)



