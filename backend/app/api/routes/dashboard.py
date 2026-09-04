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
    IncidentTimelineResponse,
    DecisionIntelligenceResponse
)
from app.services.dashboard_service import (
    calculate_dashboard_summary,
    explain_decision,
    explain_canonical_alert,
    explain_correlated_group,
    assemble_incident_timeline,
    calculate_decision_intelligence
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
    "/decision-intelligence",
    response_model=DecisionIntelligenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Phase 7: Decision Intelligence Metrics",
    description="Retrieve decision breakdown, top reasons, decision explorer, processing performance, and outcome metrics from real PostgreSQL data."
)
def get_decision_intelligence_endpoint(db: Session = Depends(get_db)):
    return calculate_decision_intelligence(db)


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
    description="Retrieve plain-English decision breakdown and deterministic evidence associated with an alert."
)
def explain_alert_decision_endpoint(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    alert_stmt = select(CanonicalAlert).where(CanonicalAlert.id == alert_id)
    alert = db.execute(alert_stmt).scalar_one_or_none()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found"
        )
    return explain_canonical_alert(alert, db)


@router.get(
    "/explain/group/{incident_id}",
    response_model=DecisionExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Explain correlation rationale for an incident group",
    description="Retrieve deterministic correlation evidence explaining why alarms were grouped into this incident cluster."
)
def explain_group_endpoint(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    stmt = select(Incident).where(Incident.id == incident_id)
    incident = db.execute(stmt).scalar_one_or_none()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident group {incident_id} not found"
        )
    return explain_correlated_group(incident, db)


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
