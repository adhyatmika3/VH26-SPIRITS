import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.raw_alert import RawAlert
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.schemas.webhook import AlertWebhookPayload, WebhookIngestResponse
from app.schemas.alert import (
    CanonicalAlertResponse,
    AlertListResponse,
    AlertStatsResponse,
    RawAlertResponse,
    RawAlertListResponse,
    AlertSimulateRequest,
    AlertSimulateResponse
)
from app.services.alert_processor import process_alert_pipeline
from app.services.alert_simulator import run_alert_simulation
from app.services.storm_detector import detect_alert_storm
from datetime import datetime, timezone

import asyncio
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/alerts", tags=["Alerts"])

# Bounded pipeline execution concurrency and backpressure controller
MAX_CONCURRENT_PIPELINE = 20
MAX_QUEUE_BACKLOG = 5000
_pipeline_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PIPELINE)
_in_flight_count = 0
_queue_backlog_count = 0


def get_ingestion_backlog_status() -> dict:
    """Returns current real-time ingestion in-flight and backlog telemetry."""
    return {
        "in_flight": _in_flight_count,
        "backlog": _queue_backlog_count,
        "max_concurrent": MAX_CONCURRENT_PIPELINE,
        "max_queue": MAX_QUEUE_BACKLOG
    }


@router.post(
    "/webhook",
    response_model=WebhookIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest and process alert webhook",
    description="Validates, normalizes, deduplicates, correlates, and persists alert webhooks with concurrency control and backpressure."
)
async def receive_alert_webhook(
    payload: AlertWebhookPayload,
    db: Session = Depends(get_db)
):
    global _queue_backlog_count, _in_flight_count

    # Backpressure check
    if _queue_backlog_count >= MAX_QUEUE_BACKLOG:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ingestion backpressure: queue capacity exceeded, retry shortly"
        )

    _queue_backlog_count += 1
    try:
        async with _pipeline_semaphore:
            _queue_backlog_count = max(0, _queue_backlog_count - 1)
            _in_flight_count += 1
            try:
                result = await run_in_threadpool(process_alert_pipeline, db=db, payload=payload)
            finally:
                _in_flight_count = max(0, _in_flight_count - 1)
    except Exception:
        _queue_backlog_count = max(0, _queue_backlog_count - 1)
        raise

    return WebhookIngestResponse(
        accepted=True,
        alert_id=str(result.raw_alert.id),
        status="received",
        canonical_alert_id=str(result.canonical_alert.id),
        incident_id=str(result.incident.id),
        incident_number=result.incident.incident_number,
        fingerprint=result.canonical_alert.fingerprint,
        is_duplicate=result.is_duplicate,
        occurrence_count=result.canonical_alert.occurrence_count,
        priority=result.canonical_alert.priority,
        is_storm=result.is_storm,
        decision=result.decision,
        reason_codes=result.reason_codes,
        reason=result.reason,
        escalation_level=result.escalation_level,
        notification_status=result.notification_record.status if result.notification_record else None
    )



@router.get(
    "",
    response_model=AlertListResponse,
    status_code=status.HTTP_200_OK,
    summary="List canonical alerts",
    description="Retrieve processed canonical alerts with filtering and pagination."
)
def list_alerts(
    service: Optional[str] = Query(None, description="Filter by service name"),
    severity: Optional[str] = Query(None, description="Filter by severity level (INFO, WARNING, ERROR, CRITICAL)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by alert status (FIRING, RESOLVED)"),
    incident_id: Optional[uuid.UUID] = Query(None, description="Filter by parent incident UUID"),
    is_duplicate: Optional[bool] = Query(None, description="Filter by duplicate status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Page limit"),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    stmt = select(CanonicalAlert)

    if service:
        stmt = stmt.where(CanonicalAlert.service == service.lower())
    if severity:
        stmt = stmt.where(CanonicalAlert.severity == severity.upper())
    if status_filter:
        stmt = stmt.where(CanonicalAlert.status == status_filter.upper())
    if incident_id:
        stmt = stmt.where(CanonicalAlert.incident_id == incident_id)
    if is_duplicate is not None:
        stmt = stmt.where(CanonicalAlert.is_duplicate == is_duplicate)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0

    # Paginate
    items_stmt = stmt.order_by(CanonicalAlert.last_seen.desc()).offset(offset).limit(limit)
    items = db.execute(items_stmt).scalars().all()

    return AlertListResponse(
        total=total,
        page=page,
        limit=limit,
        items=items
    )


@router.get(
    "/stats",
    response_model=AlertStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get alert intelligence statistics",
    description="Aggregated statistics including deduplication noise reduction ratio and alert storm status."
)
def get_alert_stats(db: Session = Depends(get_db)):
    total_raw = db.execute(select(func.count(RawAlert.id))).scalar() or 0
    total_canonical = db.execute(select(func.count(CanonicalAlert.id))).scalar() or 0
    
    # Total raw alerts absorbed through deduplication
    total_occurrences = db.execute(select(func.sum(CanonicalAlert.occurrence_count))).scalar() or total_canonical
    duplicates_absorbed = max(0, total_occurrences - total_canonical)

    reduction_percent = 0.0
    if total_raw > 0:
        reduction_percent = round(((total_raw - total_canonical) / total_raw) * 100, 2)

    is_storm = detect_alert_storm(db=db, current_time=datetime.now(timezone.utc))

    active_incidents = db.execute(
        select(func.count(Incident.id)).where(Incident.status.in_(["OPEN", "ACKNOWLEDGED"]))
    ).scalar() or 0

    # Severity breakdown
    sev_query = db.execute(
        select(CanonicalAlert.severity, func.count(CanonicalAlert.id)).group_by(CanonicalAlert.severity)
    ).all()
    severity_breakdown = {sev: count for sev, count in sev_query}

    # Top services
    svc_query = db.execute(
        select(CanonicalAlert.service, func.count(CanonicalAlert.id))
        .group_by(CanonicalAlert.service)
        .order_by(func.count(CanonicalAlert.id).desc())
        .limit(5)
    ).all()
    top_services = {svc: count for svc, count in svc_query}

    return AlertStatsResponse(
        total_raw_alerts=total_raw,
        total_canonical_alerts=total_canonical,
        total_duplicates_absorbed=duplicates_absorbed,
        noise_reduction_ratio_percent=reduction_percent,
        is_storm_active=is_storm,
        active_incidents_count=active_incidents,
        severity_breakdown=severity_breakdown,
        top_services=top_services
    )


@router.post(
    "/simulate",
    response_model=AlertSimulateResponse,
    status_code=status.HTTP_200_OK,
    summary="Simulate real-time alert injection and normalization",
    description="Dispatches requested number of alerts via real HTTP requests to the webhook pipeline, demonstrating 500->1 normalization without deleting raw records."
)
async def simulate_alerts_endpoint(
    request: Request,
    payload: AlertSimulateRequest
):
    report = await run_alert_simulation(
        app=request.app,
        count=payload.count,
        service=payload.service,
        alert_type=payload.alert_type,
        severity=payload.severity,
        environment=payload.environment,
        delay_ms=payload.delay_ms,
        scenario=payload.scenario
    )
    return AlertSimulateResponse(
        requested=report.requested,
        generated=report.generated,
        status=report.status,
        service=report.service,
        alert_type=report.alert_type,
        severity=report.severity,
        environment=report.environment,
        raw_alerts_count=report.raw_alerts_count,
        core_incidents_created=report.core_incidents_created,
        alert_reduction_percent=report.alert_reduction_percent,
        primary_incident_id=report.primary_incident_id,
        primary_incident_number=report.primary_incident_number,
        primary_incident_title=report.primary_incident_title,
        primary_incident_occurrences=report.primary_incident_occurrences,
        primary_fingerprint=report.primary_fingerprint,
        incidents_summary=report.incidents_summary,
        sample_variations=report.sample_variations
    )


@router.get(
    "/raw",
    response_model=RawAlertListResponse,
    status_code=status.HTTP_200_OK,
    summary="List raw ingested alerts",
    description="Retrieve all raw alerts stored in PostgreSQL with filtering and pagination."
)
def list_raw_alerts(
    service: Optional[str] = Query(None, description="Filter by service"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=500, description="Page limit"),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    stmt = select(RawAlert)
    if service:
        stmt = stmt.where(RawAlert.service == service.lower())
    if severity:
        stmt = stmt.where(RawAlert.severity == severity.lower())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0

    items_stmt = stmt.order_by(RawAlert.received_at.desc()).offset(offset).limit(limit)
    items = db.execute(items_stmt).scalars().all()

    return RawAlertListResponse(
        total=total,
        page=page,
        limit=limit,
        items=items
    )


@router.get(
    "/{alert_id}",
    response_model=CanonicalAlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Get canonical alert by ID",
    description="Retrieve details of a canonical alert by UUID."
)
def get_alert_by_id(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    stmt = select(CanonicalAlert).where(CanonicalAlert.id == alert_id)
    alert = db.execute(stmt).scalar_one_or_none()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Canonical alert {alert_id} not found"
        )
    return alert
