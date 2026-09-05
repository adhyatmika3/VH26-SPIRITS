from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.models.raw_alert import RawAlert


@dataclass
class DecisionOutcome:
    decision: str              # NOTIFY, SUPPRESS, ESCALATE
    reason_codes: List[str]    # Structured machine-readable codes
    reason: str                # Human-readable explanation
    escalation_level: int = 0
    is_idempotent_skip: bool = False


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate_alert_decision(
    db: Session,
    raw_alert: RawAlert,
    canonical_alert: CanonicalAlert,
    incident: Incident,
    is_duplicate: bool,
    is_storm: bool,
    current_time: Optional[datetime] = None
) -> DecisionOutcome:
    """
    Deterministic Decision Engine evaluating Phase 2 intelligent alert output in strict order:
    1. New Incident -> Evaluate Initial Notification
    2. Incident-Level Resolution -> Check if entire incident resolved
    3. Severity / Priority Escalation -> Re-notify if priority jumped
    4. Active Cooldown -> Suppress rapid repetitive duplicates
    5. Escalation Threshold -> Escalate unresolved critical incident (Idempotent per level)
    6. Default In-flight Suppression -> Noise reduction
    """
    now = ensure_utc(current_time or datetime.now(timezone.utc))
    env = (canonical_alert.labels.get("environment") or canonical_alert.labels.get("env") or "production").lower()
    is_prod = env in ["prod", "production"]
    priority = canonical_alert.priority.upper()
    severity = canonical_alert.severity.upper()
    status = canonical_alert.status.upper()

    last_notified = ensure_utc(incident.last_notified_at)
    first_seen = ensure_utc(incident.first_seen)

    # -------------------------------------------------------------------------
    # 1. New Incident Evaluation (First occurrence for this incident)
    # -------------------------------------------------------------------------
    has_prior_notif = last_notified is not None or incident.alert_count > 1
    if not has_prior_notif:
        if is_prod or severity in ["CRITICAL", "HIGH", "ERROR"] or priority in ["CRITICAL", "HIGH"]:
            reason_codes = ["NEW_INCIDENT", f"{severity}_SEVERITY"]
            if is_prod:
                reason_codes.append("PRODUCTION_ENVIRONMENT")
            if is_storm:
                reason_codes.append("ALERT_STORM_ACTIVE")

            reason = f"New {priority} incident [{incident.incident_number}] for service '{incident.service}' requiring initial SRE notification."
            return DecisionOutcome(decision="NOTIFY", reason_codes=reason_codes, reason=reason)
        else:
            # Low severity in development/staging
            return DecisionOutcome(
                decision="SUPPRESS",
                reason_codes=["LOW_SEVERITY_NON_PROD"],
                reason=f"Non-production alert with low severity ({severity}) suppressed for fatigue reduction."
            )

    # -------------------------------------------------------------------------
    # 2. Resolution Handling (Incident-Level Resolution Check)
    # -------------------------------------------------------------------------
    if status == "RESOLVED":
        # Check if ALL canonical alerts on this incident are now resolved
        unresolved_alerts_count = (
            db.query(CanonicalAlert)
            .filter(CanonicalAlert.incident_id == incident.id, CanonicalAlert.status != "RESOLVED")
            .count()
        )
        if unresolved_alerts_count == 0:
            incident.status = "RESOLVED"
            incident.resolved_at = now
            return DecisionOutcome(
                decision="NOTIFY",
                reason_codes=["INCIDENT_RESOLVED"],
                reason=f"All correlated alerts on incident [{incident.incident_number}] are now resolved."
            )
        else:
            return DecisionOutcome(
                decision="SUPPRESS",
                reason_codes=["ALERT_RESOLVED_INCIDENT_ACTIVE"],
                reason=f"Individual alert resolved, but {unresolved_alerts_count} alert(s) remain active on incident [{incident.incident_number}]."
            )

    # -------------------------------------------------------------------------
    # 3. Severity / Priority Escalation (Jump to Critical/High from Lower)
    # -------------------------------------------------------------------------
    if priority == "CRITICAL" and incident.priority not in ["CRITICAL"]:
        incident.priority = "CRITICAL"
        return DecisionOutcome(
            decision="NOTIFY",
            reason_codes=["SEVERITY_INCREASED", "CRITICAL_PRIORITY"],
            reason=f"Incident [{incident.incident_number}] escalated to CRITICAL priority due to alert '{canonical_alert.alert_name}'."
        )

    # -------------------------------------------------------------------------
    # 4. Escalation Threshold Check (Unresolved Critical Incidents / Velocity Burst)
    # -------------------------------------------------------------------------
    incident_age_seconds = (now - first_seen).total_seconds() if first_seen else 0.0
    is_unresolved = incident.status in ["OPEN", "ACKNOWLEDGED"]
    is_critical = priority == "CRITICAL" or incident.priority == "CRITICAL"

    effective_occurrence_count = max(incident.alert_count, canonical_alert.occurrence_count)
    has_reached_time_threshold = incident_age_seconds >= settings.ESCALATION_THRESHOLD_SECONDS
    has_reached_count_threshold = effective_occurrence_count >= settings.ESCALATION_OCCURRENCE_THRESHOLD

    if is_unresolved and is_critical and (has_reached_time_threshold or has_reached_count_threshold):
        # Enforce Escalation Idempotency: only escalate if not already escalated to Level 1
        if incident.escalation_level < 1:
            reason_codes = ["UNRESOLVED_CRITICAL"]
            if has_reached_time_threshold:
                reason_codes.append("ESCALATION_THRESHOLD_REACHED")
            if has_reached_count_threshold:
                reason_codes.append("HIGH_VELOCITY_BURST")

            return DecisionOutcome(
                decision="ESCALATE",
                reason_codes=reason_codes,
                reason=f"Critical incident [{incident.incident_number}] has reached escalation threshold (age={int(incident_age_seconds)}s >= {settings.ESCALATION_THRESHOLD_SECONDS}s or occurrences={effective_occurrence_count} >= {settings.ESCALATION_OCCURRENCE_THRESHOLD}). Escalating to Level 1.",
                escalation_level=1
            )

        else:
            # Already escalated to Level 1 -> Idempotently skip duplicate escalation
            return DecisionOutcome(
                decision="SUPPRESS",
                reason_codes=["ALREADY_ESCALATED", "ESCALATION_IDEMPOTENT_SKIP"],
                reason=f"Incident [{incident.incident_number}] is already escalated at Level {incident.escalation_level}. Skipping duplicate escalation.",
                is_idempotent_skip=True
            )

    # -------------------------------------------------------------------------
    # 5. Active Cooldown Window Check
    # -------------------------------------------------------------------------
    seconds_since_notification = (now - last_notified).total_seconds()
    is_cooldown_active = seconds_since_notification < settings.ALERT_COOLDOWN_SECONDS

    if is_cooldown_active:
        reason_codes = ["COOLDOWN_ACTIVE"]
        if is_duplicate:
            reason_codes.insert(0, "DUPLICATE_ALERT")
        else:
            reason_codes.insert(0, "CORRELATED_INCIDENT_ACTIVE")

        return DecisionOutcome(
            decision="SUPPRESS",
            reason_codes=reason_codes,
            reason=f"Alert suppressed under active cooldown ({int(seconds_since_notification)}s / {settings.ALERT_COOLDOWN_SECONDS}s) for incident [{incident.incident_number}]."
        )

    # -------------------------------------------------------------------------
    # 6. Default Fatigue Suppression for Correlated In-Flight Alerts
    # -------------------------------------------------------------------------
    return DecisionOutcome(
        decision="SUPPRESS",
        reason_codes=["CORRELATED_INCIDENT_ACTIVE"],
        reason=f"Alert correlated to existing active incident [{incident.incident_number}] and suppressed to reduce fatigue."
    )
