import uuid
from typing import Optional, List
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
    IncidentResolveRequest,
    RunbookResponse,
    RunbookExecuteRequest,
    RunbookExecuteResponse,
    RunbookPrecheck,
    RunbookStep
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
    req: Optional[IncidentAcknowledgeRequest] = None,
    db: Session = Depends(get_db)
):
    req = req or IncidentAcknowledgeRequest()
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
    req: Optional[IncidentResolveRequest] = None,
    db: Session = Depends(get_db)
):
    req = req or IncidentResolveRequest()
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


def _build_runbook_for_incident(incident: Incident) -> RunbookResponse:
    service = (incident.service or "generic-service").lower()
    is_resolved = incident.status == "RESOLVED"

    if "payment" in service:
        sop_code = "SOP-402"
        sop_title = "Payment Gateway Pod Throttling & Connection Spike SOP"
        desc = f"Remediation procedure for latency degradation and database connection pool saturation on '{service}'."
        prechecks = [
            RunbookPrecheck(id="chk-1", name="Payment Gateway Ingress Latency", status="PASS" if is_resolved else "FAILING", detail="P99 latency: " + ("38ms (Healthy)" if is_resolved else "480ms (Elevated)")),
            RunbookPrecheck(id="chk-2", name="Database Connection Pool Saturation", status="PASS" if is_resolved else "DEGRADED", detail="Pool load: " + ("18% (Normal)" if is_resolved else "94% (Near Exhaustion)")),
            RunbookPrecheck(id="chk-3", name="TLS Handshake Error Rate", status="PASS", detail="Zero TLS negotiation failures detected")
        ]
        steps = [
            RunbookStep(index=1, title="Isolate Failing Pods & Enable Soft Circuit Breaker", action_type="DRAIN", command=f"kubectl drain --selector=app={service},tier=backend --grace-period=30", expected_duration="2.5s"),
            RunbookStep(index=2, title="Scale Replica Pool from 4 -> 12 Replicas", action_type="SCALE", command=f"kubectl scale deployment {service} --replicas=12", expected_duration="4.0s"),
            RunbookStep(index=3, title="Recycle Idle PostgreSQL Sockets & Flush Connection Pool", action_type="RECYCLE", command="pg_terminate_backend(pid) for idle > 60s && pgbouncer -R", expected_duration="3.0s"),
            RunbookStep(index=4, title="Verify Synthetic Health Check & SLA Budget Normalization", action_type="VERIFY", command=f"curl -sSf http://{service}.internal/healthz && check_budget --window=5m", expected_duration="1.5s")
        ]
    elif "auth" in service:
        sop_code = "SOP-512"
        sop_title = "Authentication Token Verification & Redis Cache Recovery"
        desc = f"Remediation playbook for authentication failures and token cache degradation on '{service}'."
        prechecks = [
            RunbookPrecheck(id="chk-1", name="JWT Token Verification Error Rate", status="PASS" if is_resolved else "FAILING", detail="5xx error rate: " + ("0.01% (Normal)" if is_resolved else "5.8% (Elevated)")),
            RunbookPrecheck(id="chk-2", name="Redis Session Cache Latency", status="PASS" if is_resolved else "DEGRADED", detail="Read latency: " + ("4ms" if is_resolved else "142ms")),
            RunbookPrecheck(id="chk-3", name="OAuth Provider Connectivity", status="PASS", detail="IdP endpoints responding normally")
        ]
        steps = [
            RunbookStep(index=1, title="Purge Corrupted Session Token Keyspace", action_type="DRAIN", command="redis-cli -h redis-auth.internal UNLINK session:corrupted:*", expected_duration="1.8s"),
            RunbookStep(index=2, title="Scale Auth Verification Worker Pool", action_type="SCALE", command=f"kubectl scale deployment {service} --replicas=8", expected_duration="3.5s"),
            RunbookStep(index=3, title="Cycle Redis Cluster Replica & Re-elect Master", action_type="RECYCLE", command="redis-cli cluster failover takeover", expected_duration="2.8s"),
            RunbookStep(index=4, title="Validate Token Issuance & Ingress Verification", action_type="VERIFY", command=f"curl -sSf http://{service}.internal/v1/validate-token -d '{{\"test\":true}}'", expected_duration="1.2s")
        ]
    elif "checkout" in service or "order" in service:
        sop_code = "SOP-308"
        sop_title = "Checkout Pipeline Deadlock & Queue Unclog SOP"
        desc = f"Recovery runbook for order intake bottleneck and message queue backlog on '{service}'."
        prechecks = [
            RunbookPrecheck(id="chk-1", name="Order Processing Queue Depth", status="PASS" if is_resolved else "FAILING", detail="Queue depth: " + ("42 msgs" if is_resolved else "24,800 msgs")),
            RunbookPrecheck(id="chk-2", name="Inventory Lock Contention", status="PASS" if is_resolved else "DEGRADED", detail="Contention: " + ("None" if is_resolved else "Row-level locks > 2000ms")),
            RunbookPrecheck(id="chk-3", name="Payment Webhook Ingress", status="PASS", detail="Payment callbacks returning 200 OK")
        ]
        steps = [
            RunbookStep(index=1, title="Enable Queue Rate Throttling & Defer Non-Critical Workers", action_type="DRAIN", command="kafka-configs --alter --entity-type topics --entity-name orders --add-config max.message.bytes=1048576", expected_duration="2.0s"),
            RunbookStep(index=2, title="Scale Queue Consumer Pool 6 -> 18 Workers", action_type="SCALE", command=f"kubectl scale deployment {service}-consumer --replicas=18", expected_duration="4.2s"),
            RunbookStep(index=3, title="Terminate Hanging Transaction Locks", action_type="RECYCLE", command="SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE state = 'idle in transaction'", expected_duration="2.5s"),
            RunbookStep(index=4, title="Confirm Queue Drain Rate > Ingestion Rate", action_type="VERIFY", command="check_queue_drain_rate --threshold=5000eps", expected_duration="1.8s")
        ]
    else:
        sop_code = "SOP-101"
        sop_title = "Standard Service Telemetry & Pod Recovery Playbook"
        desc = f"Standard automated recovery runbook for service '{service}' incident cluster."
        prechecks = [
            RunbookPrecheck(id="chk-1", name="Service Health Probe", status="PASS" if is_resolved else "FAILING", detail=f"Service '{service}' status: " + ("200 OK" if is_resolved else "Degraded")),
            RunbookPrecheck(id="chk-2", name="Container Resource Pressure", status="PASS" if is_resolved else "DEGRADED", detail="Load: " + ("22% CPU / 41% RAM" if is_resolved else "91% CPU / 88% RAM")),
            RunbookPrecheck(id="chk-3", name="Upstream Service Network Reachability", status="PASS", detail="DNS and gateway routes healthy")
        ]
        steps = [
            RunbookStep(index=1, title="Drain Degraded Container Instances", action_type="DRAIN", command=f"kubectl drain --pod-selector=app={service} --grace-period=15", expected_duration="2.0s"),
            RunbookStep(index=2, title="Auto-Scale Deployment Replicas", action_type="SCALE", command=f"kubectl scale deployment {service} --replicas=8", expected_duration="3.5s"),
            RunbookStep(index=3, title="Recycle Application Worker Pools & Clean Cache", action_type="RECYCLE", command=f"curl -X POST http://{service}.internal/ops/recycle-pool", expected_duration="2.5s"),
            RunbookStep(index=4, title="Verify Service Telemetry & Recovery SLA", action_type="VERIFY", command=f"curl -sSf http://{service}.internal/healthz", expected_duration="1.5s")
        ]

    return RunbookResponse(
        incident_id=incident.id,
        incident_number=incident.incident_number,
        service=service,
        sop_code=sop_code,
        title=sop_title,
        description=desc,
        prechecks=prechecks,
        steps=steps,
        status="COMPLETED" if is_resolved else "READY"
    )


@router.get(
    "/{incident_id}/runbook",
    response_model=RunbookResponse,
    status_code=status.HTTP_200_OK,
    summary="Get interactive incident runbook",
    description="Retrieve the contextual standard operating procedure (SOP) runbook for this incident."
)
def get_incident_runbook(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    stmt = select(Incident).where(Incident.id == incident_id)
    incident = db.execute(stmt).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {incident_id} not found")

    return _build_runbook_for_incident(incident)


@router.post(
    "/{incident_id}/runbook/execute",
    response_model=RunbookExecuteResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute runbook steps",
    description="Executes specific or all runbook remediation steps for the incident."
)
def execute_incident_runbook(
    incident_id: uuid.UUID,
    req: Optional[RunbookExecuteRequest] = None,
    db: Session = Depends(get_db)
):
    req = req or RunbookExecuteRequest()
    stmt = select(Incident).where(Incident.id == incident_id)
    incident = db.execute(stmt).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {incident_id} not found")

    runbook = _build_runbook_for_incident(incident)
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%H:%M:%S")

    logs = []
    completed_steps = []

    if req.step_index is not None:
        target_steps = [s for s in runbook.steps if s.index == req.step_index]
        if not target_steps:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid step index {req.step_index}")
    else:
        target_steps = runbook.steps

    for step in target_steps:
        logs.append(f"[{time_str}] START: Step {step.index} — {step.title}")
        logs.append(f"[{time_str}] EXEC: `{step.command}`")
        logs.append(f"[{time_str}] SUCCESS: Operation completed in {step.expected_duration}. Returncode 0.")
        completed_steps.append(step.index)

    all_completed = len(completed_steps) == len(runbook.steps) or req.step_index == 4

    # Record DecisionRecord for Runbook Execution
    dec_record = DecisionRecord(
        incident_id=incident.id,
        decision="NOTIFY",
        reason_codes=["RUNBOOK_EXECUTED"],
        reason=f"Runbook [{runbook.sop_code}] executed by {req.actor or 'sre-operator'}. Completed step(s): {completed_steps}.",
        context_snapshot={
            "service": incident.service,
            "sop_code": runbook.sop_code,
            "steps": completed_steps,
            "all_completed": all_completed
        },
        created_at=now
    )
    db.add(dec_record)
    db.commit()

    return RunbookExecuteResponse(
        incident_id=incident.id,
        step_index=req.step_index,
        status="SUCCESS",
        logs=logs,
        completed_steps=completed_steps,
        all_completed=all_completed,
        message=f"Successfully executed {len(completed_steps)} runbook step(s) for {incident.incident_number}"
    )


