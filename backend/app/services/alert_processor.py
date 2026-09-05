import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.logging import logger
from app.core.metrics import (
    record_decision_metric,
    record_received_metric,
    record_processed_metric,
    record_processing_failure_metric,
    record_processing_duration,
    ALERTS_IN_PROCESSING
)
from app.models.raw_alert import RawAlert
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.models.decision_record import DecisionRecord
from app.models.notification_record import NotificationRecord
from app.models.escalation_record import EscalationRecord
from app.schemas.webhook import AlertWebhookPayload
from app.services.alert_service import ingest_raw_alert
from app.services.alert_normalizer import normalize_alert
from app.services.fingerprint_service import generate_fingerprint
from app.services.deduplication_service import check_and_deduplicate
from app.services.storm_detector import detect_alert_storm
from app.services.priority_engine import evaluate_priority
from app.services.correlation_service import correlate_and_assign_incident
from app.services.decision_engine import evaluate_alert_decision
from app.services.notification_service import dispatch_notification
from app.services.escalation_service import record_incident_escalation
from app.services.resolution_service import resolve_unknown_alert_sync, ResolutionResult
from app.services.risk_scoring import calculate_risk


@dataclass
class ProcessingResult:
    raw_alert: RawAlert
    canonical_alert: CanonicalAlert
    incident: Incident
    is_duplicate: bool
    is_storm: bool
    decision: str
    reason_codes: List[str]
    reason: str
    escalation_level: int
    decision_record: DecisionRecord
    notification_record: Optional[NotificationRecord] = None
    resolution_result: Optional[ResolutionResult] = None


def process_alert_pipeline(db: Session, payload: AlertWebhookPayload) -> ProcessingResult:
    """
    End-to-End Processing Pipeline across Phases 1, 2, and 3:
    Stage 1: Raw Audit Ingestion (RawAlert)
    Stage 2: Alert Intelligence & Correlation (CanonicalAlert, Incident, Storm, Deduplication)
    Stage 3: Decision Engine, Suppression, Escalation & Slack Dispatch (DecisionRecord, EscalationRecord, NotificationRecord)
    """
    now = datetime.now(timezone.utc)

    # Record received metric & increment active processing gauge
    record_received_metric(
        source=payload.source,
        severity=payload.severity or "medium"
    )
    ALERTS_IN_PROCESSING.inc()
    start_perf = time.perf_counter()

    # ----------------------------------------------------
    # Stage 1: Raw Audit Ingestion (Immutable Audit Trail)
    # ----------------------------------------------------
    raw_alert = ingest_raw_alert(db=db, payload=payload)

    # ----------------------------------------------------
    # Stage 2 & 3: Intelligence & Decision Processing (Atomic Transaction)
    # ----------------------------------------------------
    try:
        # 1. Alert Normalization
        normalized = normalize_alert(payload=payload)

        # 2. Deterministic Fingerprint
        fingerprint = generate_fingerprint(
            alert_name=normalized.alert_name,
            service=normalized.service,
            labels=normalized.labels,
            resource=normalized.resource
        )

        # 3. Alert Storm Detection
        is_storm = detect_alert_storm(db=db, current_time=now)

        # 4. Concurrency-Safe Deduplication Check
        existing_canonical, is_duplicate = check_and_deduplicate(
            db=db,
            fingerprint=fingerprint,
            current_time=now
        )

        occ_count = existing_canonical.occurrence_count if existing_canonical else 1

        # 5. Priority / Severity Evaluation
        priority = evaluate_priority(
            severity=normalized.severity,
            labels=normalized.labels,
            occurrence_count=occ_count,
            is_storm=is_storm
        )

        # 6. Update existing canonical status if resolving before correlation evaluation
        if existing_canonical:
            existing_canonical.status = normalized.status
            existing_canonical.priority = priority
            existing_canonical.is_storm = is_storm
            db.add(existing_canonical)
            db.flush()

        # 7. Hierarchical Alert Correlation & Incident Grouping
        incident = correlate_and_assign_incident(
            db=db,
            service=normalized.service,
            alert_name=normalized.alert_name,
            status=normalized.status,
            priority=priority,
            is_storm=is_storm,
            current_time=now,
            labels=normalized.labels
        )

        # 8. Canonical Alert Association
        if existing_canonical:
            if not existing_canonical.incident_id:
                existing_canonical.incident_id = incident.id
            canonical_alert = existing_canonical
        else:
            canonical_alert = CanonicalAlert(
                raw_alert_id=raw_alert.id,
                incident_id=incident.id,
                fingerprint=fingerprint,
                source=normalized.source,
                alert_name=normalized.alert_name,
                service=normalized.service,
                resource=normalized.resource,
                severity=normalized.severity,
                status=normalized.status,
                message=normalized.message,
                timestamp=normalized.timestamp,
                labels=normalized.labels,
                annotations=normalized.annotations,
                occurrence_count=1,
                is_duplicate=False,
                priority=priority,
                is_storm=is_storm,
                first_seen=now,
                last_seen=now
            )
            db.add(canonical_alert)
            incident.unique_alerts_count += 1
            db.add(incident)

        db.flush()

        # 8b. Concurrency-Safe Resolution Lookup & Intelligent Unknown-Alert Resolution
        resolution_result = resolve_unknown_alert_sync(
            db=db,
            fingerprint=fingerprint,
            alert_type=normalized.alert_name,
            service=normalized.service,
            severity=normalized.severity,
            environment=normalized.labels.get("environment", "production"),
            message=normalized.message,
            labels=normalized.labels,
            occurrence_count=canonical_alert.occurrence_count
        )

        if incident.resolution_status != "RESOLVED":
            incident.resolution_status = resolution_result.status
            db.add(incident)
            db.flush()

        # ----------------------------------------------------
        # Stage 3: Decision Engine, Suppression, Escalation & Notification
        # ----------------------------------------------------
        # 8c. Compute Deterministic Risk Score
        env_val = normalized.labels.get("environment") or normalized.labels.get("env") or "production"
        risk_result = calculate_risk(
            severity=canonical_alert.priority or canonical_alert.severity,
            service=incident.service,
            occurrence_count=incident.alert_count,
            environment=env_val,
            first_seen=incident.first_seen,
            last_seen=incident.last_seen
        )

        decision_outcome = evaluate_alert_decision(
            db=db,
            raw_alert=raw_alert,
            canonical_alert=canonical_alert,
            incident=incident,
            is_duplicate=is_duplicate,
            is_storm=is_storm,
            current_time=now
        )

        # 9. Create DecisionRecord (Audit trail of every decision with latency)
        duration_sec = time.perf_counter() - start_perf
        duration_ms = round(duration_sec * 1000.0, 2)

        decision_record = DecisionRecord(
            canonical_alert_id=canonical_alert.id,
            incident_id=incident.id,
            decision=decision_outcome.decision,
            reason_codes=decision_outcome.reason_codes,
            reason=decision_outcome.reason,
            context_snapshot={
                "service": incident.service,
                "environment": env_val,
                "priority": canonical_alert.priority,
                "severity": canonical_alert.severity,
                "occurrence_count": canonical_alert.occurrence_count,
                "incident_alert_count": incident.alert_count,
                "is_duplicate": is_duplicate,
                "is_storm": is_storm,
                "incident_number": incident.incident_number,
                "incident_status": incident.status,
                "resolution_status": resolution_result.status,
                "resolution_source": resolution_result.source,
                "resolution_confidence": resolution_result.confidence,
                "ai_called": resolution_result.ai_called,
                "probable_cause": resolution_result.probable_cause,
                "resolution_steps": resolution_result.resolution_steps,
                "risk_score": risk_result.score,
                "risk_level": risk_result.level,
                "risk_breakdown": risk_result.to_dict()["breakdown"]
            },
            processing_time_ms=duration_ms,
            created_at=now
        )
        db.add(decision_record)
        db.flush()

        # 10. Record Prometheus Metrics (Decision, Latency, Processed)
        record_processing_duration(stage="pipeline", duration=duration_sec)
        record_processed_metric(
            source=normalized.source,
            severity=canonical_alert.severity,
            decision=decision_outcome.decision
        )

        env_label = normalized.labels.get("environment") or "production"
        record_decision_metric(
            decision=decision_outcome.decision,
            severity=canonical_alert.severity,
            environment=env_label,
            service=incident.service,
            reason_codes=decision_outcome.reason_codes
        )

        notification_record = None

        # 11. Core Incident & Decision Persistence (Independent Transaction Boundary)
        # We commit the incident, canonical alert, and decision record BEFORE dispatching notifications.
        # This guarantees that external notification outages (Slack/Email) NEVER rollback or compromise core incident intelligence.
        if decision_outcome.decision == "ESCALATE":
            record_incident_escalation(
                db=db,
                incident=incident,
                canonical_alert=canonical_alert,
                escalation_level=decision_outcome.escalation_level or 1,
                reason_codes=decision_outcome.reason_codes,
                reason=decision_outcome.reason
            )

        db.commit()
        db.refresh(raw_alert)
        db.refresh(canonical_alert)
        db.refresh(incident)
        db.refresh(decision_record)

        notification_record = None

        # 12. Isolated Notification Layer (Email and Slack execute in independent failure domains)
        if decision_outcome.decision == "ESCALATE":
            is_critical = (
                canonical_alert.priority == "CRITICAL" or
                incident.priority == "CRITICAL" or
                risk_result.level == "CRITICAL"
            )
            if is_critical:
                email_notif = None
                slack_notif = None

                # Email Escalation Attempt (Isolated)
                try:
                    email_notif = dispatch_notification(
                        db=db,
                        decision_record=decision_record,
                        incident=incident,
                        canonical_alert=canonical_alert,
                        notification_type="ESCALATION",
                        channel="email"
                    )
                    db.commit()
                except Exception as e:
                    logger.error(f"Isolated email escalation error for incident [{incident.incident_number}]: {e}", exc_info=True)
                    db.rollback()

                # Slack Escalation Attempt (Isolated - failure will NEVER affect email or incident)
                try:
                    slack_notif = dispatch_notification(
                        db=db,
                        decision_record=decision_record,
                        incident=incident,
                        canonical_alert=canonical_alert,
                        notification_type="ESCALATION",
                        channel="slack"
                    )
                    db.commit()
                except Exception as e:
                    logger.error(f"Isolated Slack escalation error for incident [{incident.incident_number}]: {e}", exc_info=True)
                    db.rollback()

                notification_record = slack_notif or email_notif
            else:
                try:
                    notification_record = dispatch_notification(
                        db=db,
                        decision_record=decision_record,
                        incident=incident,
                        canonical_alert=canonical_alert,
                        notification_type="ESCALATION",
                        channel="slack"
                    )
                    db.commit()
                except Exception as e:
                    logger.error(f"Isolated Slack escalation error for incident [{incident.incident_number}]: {e}", exc_info=True)
                    db.rollback()

        elif decision_outcome.decision == "NOTIFY":
            notif_type = "RESOLUTION" if "INCIDENT_RESOLVED" in decision_outcome.reason_codes else "INITIAL"
            try:
                notification_record = dispatch_notification(
                    db=db,
                    decision_record=decision_record,
                    incident=incident,
                    canonical_alert=canonical_alert,
                    notification_type=notif_type,
                    channel="slack"
                )
                db.commit()
            except Exception as e:
                logger.error(f"Isolated Slack notification error for incident [{incident.incident_number}]: {e}", exc_info=True)
                db.rollback()

        if notification_record:
            try:
                db.refresh(notification_record)
            except Exception:
                pass

        logger.info(
            f"Alert processed: Decision=[{decision_outcome.decision}], "
            f"Reasons={decision_outcome.reason_codes}, Incident=[{incident.incident_number}]"
        )

        return ProcessingResult(
            raw_alert=raw_alert,
            canonical_alert=canonical_alert,
            incident=incident,
            is_duplicate=is_duplicate,
            is_storm=is_storm,
            decision=decision_outcome.decision,
            reason_codes=decision_outcome.reason_codes,
            reason=decision_outcome.reason,
            escalation_level=incident.escalation_level,
            decision_record=decision_record,
            notification_record=notification_record,
            resolution_result=resolution_result
        )

    except Exception as exc:
        record_processing_failure_metric(stage="pipeline")
        db.rollback()
        logger.error(f"Error in Alert Processing Pipeline for raw alert [{raw_alert.id}]: {exc}", exc_info=True)
        raise exc
    finally:
        ALERTS_IN_PROCESSING.dec()
