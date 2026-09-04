import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import logger
from app.models.incident import Incident
from app.models.canonical_alert import CanonicalAlert

PRIORITY_RANKS = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def correlate_and_assign_incident(
    db: Session,
    service: str,
    alert_name: str,
    status: str,
    priority: str,
    is_storm: bool,
    current_time: datetime,
    labels: Optional[Dict[str, Any]] = None,
    window_seconds: Optional[int] = None
) -> Incident:
    """
    Hierarchical Deterministic Correlation Engine with Lifecycle Resolution:
    1. Tier 1: Matching service + environment + cluster
    2. Tier 2: Matching service + environment
    3. Tier 3: Matching service + host / instance
    4. Fallback: Generate sequential INC-xxxx and create new Incident.
    
    If alert status is RESOLVED:
    - Associates with existing active incident and checks if all member alerts are resolved.
    """
    window = window_seconds or settings.CORRELATION_WINDOW_SECONDS
    cutoff_time = current_time - timedelta(seconds=window)
    labels = labels or {}

    env = str(labels.get("environment") or labels.get("env") or "").strip().lower()
    cluster = str(labels.get("cluster") or "").strip().lower()
    host = str(labels.get("host") or labels.get("instance") or "").strip().lower()

    # Find active (OPEN / ACKNOWLEDGED) incidents for this service within the temporal window
    stmt = (
        select(Incident)
        .where(
            Incident.service == service,
            Incident.status.in_(["OPEN", "ACKNOWLEDGED"]),
            Incident.last_seen >= cutoff_time
        )
        .order_by(Incident.last_seen.desc())
    )
    active_incidents = db.execute(stmt).scalars().all()

    target_alert_type = str(
        labels.get("alert_type") or 
        labels.get("type") or 
        labels.get("category") or ""
    ).strip().upper()

    def is_type_compatible(alt: CanonicalAlert) -> bool:
        if not target_alert_type:
            return True
        alt_type = str(
            alt.labels.get("alert_type") or 
            alt.labels.get("type") or 
            alt.labels.get("category") or ""
        ).strip().upper()
        if not alt_type:
            return True
        return alt_type == target_alert_type

    matched_incident: Optional[Incident] = None

    # Tier 1: Service + Environment + Cluster
    if env and cluster:
        for inc in active_incidents:
            for alt in inc.alerts:
                alt_env = str(alt.labels.get("environment") or alt.labels.get("env") or "").strip().lower()
                alt_cluster = str(alt.labels.get("cluster") or "").strip().lower()
                if alt_env == env and alt_cluster == cluster and is_type_compatible(alt):
                    matched_incident = inc
                    break
            if matched_incident:
                break

    # Tier 2: Service + Environment
    if not matched_incident and env:
        for inc in active_incidents:
            for alt in inc.alerts:
                alt_env = str(alt.labels.get("environment") or alt.labels.get("env") or "").strip().lower()
                if alt_env == env and is_type_compatible(alt):
                    matched_incident = inc
                    break
            if matched_incident:
                break

    # Tier 3: Service + Host / Instance
    if not matched_incident and host:
        for inc in active_incidents:
            for alt in inc.alerts:
                alt_host = str(alt.labels.get("host") or alt.labels.get("instance") or "").strip().lower()
                if alt_host == host and is_type_compatible(alt):
                    matched_incident = inc
                    break
            if matched_incident:
                break

    # If an existing incident was matched
    if matched_incident:
        matched_incident.alert_count += 1
        matched_incident.last_seen = current_time
        if is_storm:
            matched_incident.is_storm = True

        # Escalate incident priority if incoming alert has higher priority
        if PRIORITY_RANKS.get(priority, 1) > PRIORITY_RANKS.get(matched_incident.priority, 1):
            matched_incident.priority = priority

        # Lifecycle resolution check
        if status.upper() == "RESOLVED":
            # Check if all sibling alerts are resolved
            other_firing = any(
                a.status.upper() == "FIRING"
                for a in matched_incident.alerts
            )
            if not other_firing:
                matched_incident.status = "RESOLVED"
                logger.info(f"All alerts resolved for Incident [{matched_incident.incident_number}] -> Status: RESOLVED")

        db.add(matched_incident)
        db.flush()

        logger.info(
            f"Correlated alert [{alert_name}] to Incident [{matched_incident.incident_number}] (service={service}), "
            f"total_alerts={matched_incident.alert_count}"
        )
        return matched_incident

    # Fallback: Create a new Incident
    count_stmt = select(func.count(Incident.id))
    total_incidents = db.execute(count_stmt).scalar() or 0
    inc_number = f"INC-{1001 + total_incidents}"

    if target_alert_type == "CPU_HIGH":
        title = f"{service.replace('-', ' ').title()} — High CPU Utilization"
    elif target_alert_type == "DATABASE_ERROR":
        title = f"{service.replace('-', ' ').title()} — Database Connection Error"
    elif target_alert_type == "MEMORY_HIGH":
        title = f"{service.replace('-', ' ').title()} — High Memory Utilization"
    elif target_alert_type:
        title = f"{service.replace('-', ' ').title()} — {target_alert_type.replace('_', ' ').title()}"
    else:
        title = f"{alert_name} degradation on {service}"
    init_status = "RESOLVED" if status.upper() == "RESOLVED" else "OPEN"

    new_incident = Incident(
        incident_number=inc_number,
        title=title,
        service=service,
        status=init_status,
        priority=priority,
        alert_count=1,
        unique_alerts_count=1,
        is_storm=is_storm,
        first_seen=current_time,
        last_seen=current_time
    )

    db.add(new_incident)
    db.flush()

    logger.info(f"Created new Incident [{new_incident.incident_number}] for service [{service}]")
    return new_incident
